#!/usr/bin/env python3
"""Make the Thai template of an agent from its English one (agents/<persona>/en/<x>.json -> agents/<persona>/th/<x>.json).

  python3 tools/translate.py agents/government-officer/en/incoming-letters.json [...]
  python3 tools/translate.py --all            every en template that has no th template yet
  python3 tools/translate.py --check <th.json> meaning check only (English -> Thai -> English, per step)

Translated: step names, step descriptions, agent instructions, approval / question card text, output field descriptions,
the agent description. Never translated (protected as tokens): ${refs}, {{PLACEHOLDERS}}, URLs, emails, long IDs,
snake_case names (tools, fields), every output field name, and quoted English strings (sheet columns, literal values).
Field names stay English, so every reference between steps still works (the platform rejects Thai names in ${...}).

Translator: Gemini on Vertex, temperature 0, as the user in --project (default thai-gov-poc). Results are cached in
tools/.translate_cache.json, so a rerun gives the same Thai. A review file <x>.review.json is written next to the
Thai template: per text, English | Thai | Thai back to English | meaning same? | problems in the Thai."""
import argparse, hashlib, json, pathlib, re, subprocess, sys, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
import os
CACHE = pathlib.Path(os.environ.get("TRANSLATE_CACHE", ROOT / "tools" / ".translate_cache.json"))
THAI = re.compile(r"[฀-๿]")
BASE_KEEP = (r"\$\{[^}]+\}|\{\{\w+\}\}|https?://[^\s\"'<>)\]]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\b[A-Za-z0-9_-]{25,}\b"
             r"|\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b[a-z]+(?=\s*[:=]\s*['\"$\[{0-9])|\"[^\"\n]*[A-Za-z][^\"\n]*\"|\[……\]")
PARTICLES = re.compile(r"ครับ|ค่ะ|คะ(?![฀-๿])|นะครับ|นะคะ")

TO_TH = """You translate the texts of a Gemini Enterprise workflow agent built for Thai government users (Ministry of Digital
Economy and Society, Thailand). Translate each item from English into Thai.
- Clear, formal, natural Thai as a Thai civil servant writes; official Thai (ภาษาราชการ) for letters, memos and notices.
- No gendered particles (ครับ, ค่ะ, คะ, นะครับ, นะคะ).
- Keep every token like ⟦3⟧ exactly once and unchanged.
- Keep unchanged any English word that is a code, status value, option or data value the agent must output or compare
  (for example found, missing, ambiguous, done, running, failed, duplicate, not_a_letter, yes, no, true, false, approved, TEST);
  write "status is done" as "status เป็น done", never translate the value, and tool names, JSON, cron and code.
- Thai words already in the text stay as they are (they are file, folder and column names).
- Keep numbered steps, bullets and line breaks. Do not add, drop, merge or soften any rule, number, date or condition.
Answer JSON only: {"items": ["<thai>", ...]} with exactly %d items in the same order.
ITEMS:
%s"""

TO_EN = """Translate each Thai item into English, faithfully (keep structure, numbers, names; do not improve or summarise).
Also list problems with the Thai itself as a Thai ministry reader would see them (ungrammatical, unnatural, wrong register,
unclear). [] if none. Answer JSON only: {"items": [{"en": "...", "issues": ["..."]}]} with exactly %d items in the same order.
ITEMS:
%s"""

SAME = """Each item pairs the ORIGINAL English instruction of a workflow AI agent step with its BACK-TRANSLATION (English -> Thai ->
English). Ignore wording, order, tone. Thai words in the ORIGINAL (file, folder, column names, fixed Thai phrases) are kept
exactly in the Thai version and only appear translated in the back-translation: never report those. Report only differences that would change what the agent does: a step, condition, number,
date, recipient, file or field name, quoted text, status value, rule or limit added, dropped or changed.
Answer JSON only: {"items": [{"same": true|false, "differences": ["..."]}]} with exactly %d items in the same order.
ITEMS:
%s"""


class Gemini:
    def __init__(self, user, project, model, location="global"):
        self.user, self.project, self.model = user, project, model
        self.url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}"
                    f"/publishers/google/models/{model}:generateContent")
        self.cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        self._tok = None

    def token(self):
        if not self._tok:
            self._tok = subprocess.check_output(["gcloud", "auth", "print-access-token", self.user], text=True).strip()
        return self._tok

    def ask(self, prompt, tries=4):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
        for i in range(tries):
            req = urllib.request.Request(self.url, data=json.dumps(body, ensure_ascii=False).encode(), method="POST", headers={
                "Authorization": f"Bearer {self.token()}", "X-Goog-User-Project": self.project, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    d = json.loads(r.read())
                return json.loads("".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought")))
            except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
                if i == tries - 1:
                    raise
                print(f"  translator retry {i + 1}: {str(e)[:200]}", file=sys.stderr)
                self._tok = None

    def batched(self, kind, prompt, texts, prep=lambda t: (t, None), post=lambda g, k: g, size=9000):
        key = lambda t: hashlib.sha1(f"{self.model}|{kind}|{hashlib.sha1(prompt.encode()).hexdigest()[:8]}|{t}".encode()).hexdigest()
        todo = [t for t in dict.fromkeys(texts) if t.strip() and key(t) not in self.cache]
        batch, n = [], 0
        for t in todo + [None]:
            if batch and (t is None or n + len(t) > size):
                self._run(kind, prompt, batch, key, prep, post)
                batch, n = [], 0
            if t is not None:
                batch.append(t)
                n += len(t)
        return [self.cache.get(key(t), t) for t in texts]

    def _run(self, kind, prompt, batch, key, prep, post):
        prepped = [prep(t) for t in batch]
        for attempt in range(3):
            got = self.ask(prompt % (len(batch), json.dumps([p for p, _ in prepped], ensure_ascii=False)))["items"]
            if len(got) != len(batch):
                if len(batch) > 1:  # split and retry smaller
                    h = len(batch) // 2
                    self._run(kind, prompt, batch[:h], key, prep, post)
                    self._run(kind, prompt, batch[h:], key, prep, post)
                    return
                continue
            try:
                out = [post(g, k) for g, (_, k) in zip(got, prepped)]
            except ValueError as e:
                print(f"  {kind}: {e}; retrying", file=sys.stderr)
                if len(batch) > 1:
                    h = len(batch) // 2
                    self._run(kind, prompt, batch[:h], key, prep, post)
                    self._run(kind, prompt, batch[h:], key, prep, post)
                    return
                continue
            self.cache.update({key(s): o for s, o in zip(batch, out)})
            CACHE.write_text(json.dumps(self.cache, ensure_ascii=False))
            return
        raise SystemExit(f"{kind}: translator failed 3 times on a batch starting {batch[0][:120]!r}")


def nodes(flow):
    for n in flow.get("nodes", []):
        yield n
        if "forLoopNode" in n:
            yield from nodes(n["forLoopNode"].get("subAgentFlow", {}))


def field_names(flow):
    acc = set()

    def walk(s):
        for k, p in (s or {}).get("properties", {}).items():
            acc.add(k)
            walk(p)
            walk(p.get("items"))
    for n in nodes(flow):
        walk(n.get("outputSchema"))
    return acc


def schema_texts(schema, acc):
    for p in (schema or {}).get("properties", {}).values():
        if p.get("description"):
            acc.append((p, "description"))
        schema_texts(p, acc)
        if p.get("items"):
            if p["items"].get("description"):
                acc.append((p["items"], "description"))
            schema_texts(p["items"], acc)
    return acc


def slots(t):
    """(dict, key) for every text to translate."""
    flow = t["definition"]["agentFlow"]
    out = [(t, "description")]
    for n in nodes(flow):
        if n.get("displayName"):
            out.append((n, "displayName"))
        if n.get("description"):
            out.append((n, "description"))
        for kind, field in (("agentNode", "instruction"), ("approvalNode", "message"), ("requestInfoNode", "message")):
            if n.get(kind, {}).get(field):
                out.append((n[kind], field))
        schema_texts(n.get("outputSchema"), out)
    return out


def make_protect(names):
    # plain-word field names (to, answer, link) are not protected: protecting them left English inside Thai prose (14 Oct).
    # Assignments (word = / word:) are protected by BASE_KEEP; identifier-like names (snake_case, camelCase) too.
    words = "|".join(sorted((re.escape(w) for w in names if re.match(r"^[A-Za-z]\w*$", w) and ("_" in w or re.search(r"[a-z][A-Z]", w))), key=len, reverse=True))
    keep = re.compile(BASE_KEEP + (rf"|\b(?:{words})\b" if words else ""))

    def protect(text):
        kept = []

        def sub(m):
            kept.append(m.group(0))
            return f"⟦{len(kept) - 1}⟧"
        return keep.sub(sub, text), kept

    def restore(text, kept):
        missing = [kept[i] for i in range(len(kept)) if f"⟦{i}⟧" not in text]
        if missing:
            raise ValueError(f"translation dropped {missing[:3]}")
        return re.sub(r"⟦(\d+)⟧", lambda m: kept[int(m.group(1))], text)
    return protect, restore


THAI_ONLY = [  # the en agents answer bilingually for English-speaking reviewers; the th agents are Thai-native (14 Oct)
    (re.compile(r"Thai first, then the same in English", re.I), "in Thai only (no English)"),
    (re.compile(r"in (short )?Thai,? with (the )?English in brackets", re.I), r"in \1Thai only"),
    (re.compile(r"\bThai with (the )?English in brackets", re.I), "Thai only"),
]
GLOSS = re.compile(r"(?<=[\u0e00-\u0e7f\'’])\s*\(((?:[A-Z][A-Za-z ,'’/&-]{2,80})|(?:[a-z]+(?: [A-Za-z'’/&-]+){1,10}))\)")


def thai_only(text):
    for pat, rep in THAI_ONLY:
        text = pat.sub(rep, text)
    return text


def drop_glosses(text):
    """'แผนการค้นคว้าที่เสนอ (Proposed research plan)' -> 'แผนการค้นคว้าที่เสนอ'; keeps field hints such as (docUrl), (from)."""
    return GLOSS.sub("", text)


def translate(g, en_path):
    t = json.loads(en_path.read_text())
    th = json.loads(json.dumps(t))
    protect, restore = make_protect(field_names(th["definition"]["agentFlow"]))
    sl = slots(th)
    src = [thai_only(d[k]) for d, k in sl]
    out = [drop_glosses(x) for x in g.batched("th", TO_TH, src, prep=protect, post=restore)]
    for (d, k), s in zip(sl, out):
        d[k] = s
    th["lang"] = "th"
    th["display_name"] = t["display_name"] + " (TH)"
    th["_built_from"] = f"tools/translate.py from en/{en_path.name} ({g.model}, field names kept in English). " + t.get("_built_from", "")
    dst = en_path.parent.parent / "th" / en_path.name
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(json.dumps(th, ensure_ascii=False, indent=1))
    left = [s for s in out if s.strip() and not THAI.search(s) and len(s) > 40]
    print(f"wrote {dst.relative_to(ROOT)}: {len(src)} texts; {len(left)} long texts with no Thai")
    return dst


def check(g, th_path):
    th = json.loads(th_path.read_text())
    en = json.loads((th_path.parent.parent / "en" / th_path.name).read_text())
    pairs = [(d[k], thai_only(e[k2])) for (d, k), (e, k2) in zip(slots(th), slots(en))]  # th builds are Thai-only on purpose
    instr = [(h, e) for h, e in pairs if len(e) > 200]  # instructions and cards: the texts that steer behaviour
    back = g.batched("en", TO_EN, [h for h, _ in instr])
    back = [b if isinstance(b, dict) else {"en": str(b), "issues": []} for b in back]
    same = g.batched("same", SAME, [json.dumps({"original": e, "back_translation": b["en"]}, ensure_ascii=False)
                                    for (_, e), b in zip(instr, back)])
    thai_lit = re.compile(r"[\u0e00-\u0e7f][\u0e00-\u0e7f0-9 .]*[\u0e00-\u0e7f]")
    tok = re.compile(BASE_KEEP)
    rows = []
    for (h, e), b, s in zip(instr, back, same):
        lost = [x for x in set(thai_lit.findall(e)) + set(tok.findall(e)) if x not in h] if False else \
               [x for x in set(thai_lit.findall(e)) | set(tok.findall(e)) if x not in h]
        s = s if isinstance(s, dict) else {"same": None, "differences": [str(s)]}
        rows.append({"en": e, "th": h, "back": b["en"], "same": s.get("same"), "differences": s.get("differences", []),
                     "issues": b.get("issues", []), "lost_literals": lost, "particles": PARTICLES.findall(h) if len(PARTICLES.findall(h)) > len(PARTICLES.findall(e)) else []})
    rev = th_path.with_suffix(".review.json")
    rev.write_text(json.dumps({"template": th_path.name, "model": g.model, "items": rows}, ensure_ascii=False, indent=1))
    bad = [r for r in rows if r["same"] is False]
    lost = [r for r in rows if r["lost_literals"]]
    if lost:
        print(f"   ! {len(lost)} texts lost literals:", [r["lost_literals"][:3] for r in lost][:5])
    print(f"{th_path.relative_to(ROOT)}: {len(rows)} instructions/cards checked; meaning changed in {len(bad)}; "
          f"gendered particles in {sum(1 for r in rows if r['particles'])}; review: {rev.relative_to(ROOT)}")
    for r in bad:
        print("   -", "; ".join(r["differences"])[:300])
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", action="store_true", help="files are th templates: meaning check only")
    ap.add_argument("--user", default="navya.agarwal@devxlabs.ai")
    ap.add_argument("--project", default="thai-gov-poc")
    ap.add_argument("--model", default="gemini-3.8-flash")
    a = ap.parse_args()
    g = Gemini(a.user, a.project, a.model)
    files = [pathlib.Path(f).resolve() for f in a.files]
    if a.all:
        files = [p for p in sorted(ROOT.glob("agents/*/en/*.json")) if not (p.parent.parent / "th" / p.name).exists()]
    for f in files:
        if a.check:
            check(g, f)
        else:
            check(g, translate(g, f))


if __name__ == "__main__":
    main()
