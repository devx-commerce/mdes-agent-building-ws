#!/usr/bin/env python3
"""Run an agent end to end through the API and check what it did. Needs an app where cards can be answered through the
API (yash-test EAP, tested 13 Oct 2026); elsewhere a run stops at its first card.

  python3 tests/harness.py tests/cases/<case>.json [...]      run cases (configs/yash-test.json unless --config)
  python3 tests/harness.py --all [--only GOV-A] [--lang th]  every case
  python3 tests/harness.py --dry tests/cases/<case>.json      check the case file only

A case (JSON):
{
 "id": "gov-a-th-full", "agent": "GOV-A", "lang": "th",          # which deployed agent (display name from the template)
 "why": "...",                                                    # what the case proves (use-case line, earlier bug)
 "setup": [{"drive_upload": {...}} | {"drive_trash_name": "<regex>"} | {"drive_touch": "<file id>"}],  # optional, before start
 "start": "<typed request>",                                      # schedule agents: "[scheduled run]" or a typed request
 "cards": [{"when": {"action": "<regex>", "title": "<regex>", "node": "<regex>", "args": "<regex on args JSON>"},
            "do": "approve|reject|cancel|answer", "feedback": "...", "args": {...}}],   # first matching rule wins
 "default_card": "approve",                                       # for cards no rule matches
 "max_cards": 25, "max_minutes": 45,
 "expect": {"status": "succeeded", "final_contains": [..], "final_not_contains": [..], "final_regex": [..],
            "cards_seen": ["<action or title regex>"], "cards_not_seen": [..],
            "files": [{"name": "<regex>", "mime": "document|spreadsheet|presentation|folder|...", "contains": [..], "thai": true}],
            "no_files": ["<regex>"], "thai_final": true, "emails_to": "<regex every recipient must match>"}
}
Safety: a card that would send/draft/invite to an address outside --allow (default navya.agarwal(+tag)@devxlabs.ai) is
cancelled and the case fails. Every turn's raw chunks and a result.json go to tests/results/<stamp>/<case id>/."""
import argparse, datetime, json, pathlib, re, subprocess, sys, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
THAI = re.compile(r"[฀-๿]")
LETTER = re.compile(r"[A-Za-z฀-๿]")
PARTICLES = re.compile(r"(?<![฀-๿])(?:ครับ|ค่ะ|นะคะ|นะครับ)(?![฀-๿])|(?<=[฀-๿ ])(?:ครับ|ค่ะ)(?=[\s.!]|$)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
SENDING = re.compile(r"send|reply|forward|draft|invite|create_event|update_event|share", re.I)


def now():
    return datetime.datetime.now(datetime.timezone.utc)


class Api:
    def __init__(self, cfg):
        self.cfg = cfg
        host = "discoveryengine.googleapis.com" if cfg["location"] == "global" else f"{cfg['location']}-discoveryengine.googleapis.com"
        self.root = f"https://{host}/v1alpha"
        self.engine = f"projects/{cfg['project_number']}/locations/{cfg['location']}/collections/default_collection/engines/{cfg['app']}"
        self._tok, self._t = None, 0

    def token(self):
        if not self._tok or time.time() - self._t > 900:
            self._tok = subprocess.check_output(["gcloud", "auth", "print-access-token", self.cfg["user"]], text=True).strip()
            self._t = time.time()
        return self._tok

    def call(self, method, url, body=None, timeout=120):
        url = url if url.startswith("http") else f"{self.root}/{url}"
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        for i in range(4):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {self.token()}", "X-Goog-User-Project": self.cfg["project"], "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                msg = e.read().decode()[:1500]
                if e.code == 401 and i < 3:  # cached token went stale mid-run (ACCESS_TOKEN_TYPE_UNSUPPORTED, 14 Oct): refresh, retry
                    self._tok = None
                    continue
                if e.code in (429, 500, 502, 503) and i < 3:
                    time.sleep(20 * (i + 1))
                    continue
                raise RuntimeError(f"HTTP {e.code} {method} {url.split('/v1alpha/')[-1][:120]}: {msg}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if i < 3 and method == "GET":
                    time.sleep(10)
                    continue
                raise RuntimeError(f"{type(e).__name__} {method}: {e}")

    def drive(self, path, params=None, method="GET", body=None, raw=False):
        q = ("?" + urllib.parse.urlencode(params)) if params else ""
        req = urllib.request.Request(f"https://www.googleapis.com/drive/v3/{path}{q}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None, headers={
                                         "Authorization": f"Bearer {self.token()}", "X-Goog-User-Project": self.cfg["project"],
                                         "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read()
            return b.decode("utf-8", "replace") if raw else json.loads(b or b"{}")


import urllib.parse  # noqa: E402


def agent_ids(api):
    out = {}
    for a in api.call("GET", f"{api.engine}/assistants/default_assistant/agents?pageSize=200").get("agents", []):
        out[a.get("displayName")] = a["name"].split("/")[-1]
    return out


def template_name(case):
    for p in ROOT.glob(f"agents/*/{case['lang']}/*.json"):
        if p.name.endswith(".review.json"):
            continue
        t = json.loads(p.read_text())
        if t["id"] == case["agent"]:
            return t["display_name"]
    raise SystemExit(f"no template for {case['agent']} {case['lang']}")


def stores(api):
    eng = api.call("GET", api.engine)
    base = api.engine.rsplit("/engines/", 1)[0]
    return [{"dataStore": f"{base}/dataStores/{s}"} for s in eng.get("dataStoreIds", [])]


def parse(chunks):
    """-> dict(session, answer, state, invocations, texts, events)"""
    out = {"session": None, "answer": None, "state": None, "invocations": [], "texts": [], "events": [], "errors": []}
    seen = set()
    for c in chunks:
        out["session"] = c.get("sessionInfo", {}).get("session") or out["session"]
        a = c.get("answer", {})
        out["answer"] = a.get("name") or out["answer"]
        out["state"] = a.get("state") or out["state"]
        for r in a.get("replies", []):
            inv = r.get("actionInvocation")
            if inv and inv.get("invocationId") not in seen:
                seen.add(inv.get("invocationId"))
                out["invocations"].append(inv)
            gc = r.get("groundedContent", {}).get("content", {})
            if gc.get("text") and not gc.get("thought"):
                out["texts"].append(gc["text"])
            w = r.get("workflowAdkEvent") or {}
            for k in ("startEvent", "endEvent", "errorEvent", "pauseEvent", "hitlEvent", "resumeEvent"):
                if k in w:
                    ev = {"node": w.get("nodeId"), "event": k, "time": w.get("eventTime")}
                    if k == "endEvent":
                        ev["out"] = {kk: (v.get("value") if isinstance(v, dict) else v) for kk, v in (w[k].get("outputParameters") or {}).items()}
                    if k == "errorEvent":
                        ev["error"] = w[k]
                        out["errors"].append(w[k])
                    out["events"].append(ev)
        if a.get("assistSkippedReasons"):
            out["errors"].append({"skipped": a["assistSkippedReasons"]})
    return out


def card_info(inv):
    pd = inv.get("parameterDeclaration", {})
    meta = pd.get("additionalProperties", {}) or {}
    return {"action": inv.get("actionName", ""), "title": pd.get("title", ""), "node": meta.get("node_id", ""),
            "kind": meta.get("node_type", "tool"), "args": inv.get("args", {}), "props": list((pd.get("properties") or {}).keys())}


def decide(case, info):
    for rule in case.get("cards", []):
        w = rule.get("when", {})
        if all(re.search(w[k], info[k] if k != "args" else json.dumps(info["args"], ensure_ascii=False), re.I | re.S)
               for k in ("action", "title", "node", "args") if k in w):
            return rule
    return {"do": case.get("default_card", "approve")}


def recipients(args):
    s = json.dumps({k: v for k, v in args.items() if re.search(r"to|cc|bcc|recipient|attendee|email|address|share", k, re.I)},
                   ensure_ascii=False)
    return sorted(set(EMAIL.findall(s)))


class Run:
    def __init__(self, api, case, allow, outdir):
        self.api, self.case, self.allow, self.dir = api, case, re.compile(allow), outdir
        self.cards, self.parsed, self.problems, self.turn = [], [], [], 0
        self.url = f"{api.engine}/assistants/default_assistant:streamAssist"

    def body(self, aid, text, extra=None):
        b = {"query": {"parts": [{"text": text}]}, "agentsSpec": {"agentSpecs": [{"agentId": aid, "version": "draft"}]},
             "toolsSpec": {"vertexAiSearchSpec": {"dataStoreSpecs": self.stores}}, "answerGenerationMode": "AGENT"}
        b.update(extra or {})
        return b

    def stream(self, body):
        self.turn += 1
        t0 = time.time()
        try:
            ch = self.api.call("POST", self.url, body, timeout=60 * 25)
        except RuntimeError as e:
            self.problems.append(f"turn {self.turn}: {e}")
            ch = []
        ch = ch if isinstance(ch, list) else [ch]
        (self.dir / f"turn{self.turn:02d}.json").write_text(json.dumps(ch, ensure_ascii=False, indent=1))
        p = parse(ch)
        p["seconds"] = round(time.time() - t0)
        self.parsed.append(p)
        return p

    def session_state(self, sess):
        s = self.api.call("GET", sess)
        labels = s.get("labels", [])
        status = [l.rsplit("status:", 1)[1] for l in labels if "status:" in l and "summary" not in l]
        return (status[-1] if status else None), s

    def go(self, aid):
        case = self.case
        self.stores = stores(self.api)
        self.start = now()
        deadline = time.time() + 60 * case.get("max_minutes", 45)
        p = self.stream(self.body(aid, case.get("start", " ")))
        sess = p["session"]
        if not sess:
            self.problems.append("no session returned")
            return None
        answered = set()
        while time.time() < deadline:
            invs = [i for i in p["invocations"] if i.get("invocationId") not in answered]
            if not invs:
                st, _ = self.session_state(sess)
                if st in ("interrupted",) and len(self.cards) < case.get("max_cards", 25):
                    # paused at a card the stream did not show: read it from the session's last answer
                    p2 = self.last_answer(sess)
                    invs = [i for i in p2["invocations"] if i.get("invocationId") not in answered] if p2 else []
                    if not invs:
                        break
                elif st in ("running", "in_progress", None) and p["state"] != "SUCCEEDED":
                    time.sleep(30)
                    p2 = self.last_answer(sess)
                    if p2 and p2["invocations"]:
                        p = p2
                    continue
                else:
                    break
            inv = invs[-1]
            answered.add(inv.get("invocationId"))
            info = card_info(inv)
            rule = decide(case, info)
            do = rule.get("do", "approve")
            rec = recipients(info["args"])
            bad = [r for r in rec if not self.allow.match(r)]
            if bad and SENDING.search(info["action"]) and do in ("approve", "answer"):
                self.problems.append(f"card {info['action']} would reach {bad}: cancelled")
                do = "cancel"
            info.update(decision=do, recipients=rec, turn=self.turn)
            self.cards.append(info)
            (self.dir / f"card{len(self.cards):02d}.json").write_text(json.dumps(inv, ensure_ascii=False, indent=1))
            if len(self.cards) > case.get("max_cards", 25):
                self.problems.append("too many cards: stopped")
                break
            if info["kind"] == "approval_node" or "approval_decision" in info["props"]:
                args = {"approval_decision": "rejected" if do in ("reject", "cancel") else "approved",
                        "approval_feedback": rule.get("feedback", "")}
                cancel = False
            elif do == "answer" or info["action"] in ("flow_request_input", "request_input") or info["kind"] == "request_info_node":
                args = dict(info["args"])
                args.update(rule.get("args", {}))
                cancel = do == "cancel"
            else:
                args = dict(info["args"])
                args.update(rule.get("args", {}))
                cancel = do in ("cancel", "reject")
            ans = p["answer"] or self.api.call("GET", sess).get("turns", [{}])[-1].get("assistAnswer", "")
            ans = ans[ans.index("collections/"):] if "collections/" in ans else ans
            params = {"agentName": inv["agentName"], "actionName": inv["actionName"], "assistAnswerName": ans, "args": args,
                      "cancelAction": cancel}
            if inv.get("invocationId"):
                params["actionInvocationId"] = inv["invocationId"]
            p = self.stream(self.body(aid, "Send" if not cancel else "Cancel",
                                      {"session": sess, "assistSkippingMode": "REQUEST_ASSIST", "actionExecutionParams": params}))
            if not p["answer"]:
                p["answer"] = self.api.call("GET", sess).get("turns", [{}])[-1].get("assistAnswer")
        else:
            self.problems.append(f"timed out after {case.get('max_minutes', 45)} min")
        return sess

    def last_answer(self, sess):
        try:
            s = self.api.call("GET", sess)
            name = (s.get("turns") or [{}])[-1].get("assistAnswer")
            if not name:
                return None
            a = self.api.call("GET", name)
            p = parse([{"answer": a, "sessionInfo": {"session": sess}}])
            p["answer"] = name
            return p
        except RuntimeError:
            return None


def drive_files_since(api, since):
    q = f"createdTime > '{since.strftime('%Y-%m-%dT%H:%M:%S')}' and trashed = false"
    out, tok = [], None
    while True:
        params = {"q": q, "pageSize": 200, "fields": "nextPageToken,files(id,name,mimeType,createdTime,webViewLink,parents)",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
        if tok:
            params["pageToken"] = tok
        r = api.drive("files", params)
        out += r.get("files", [])
        tok = r.get("nextPageToken")
        if not tok:
            return out


def file_text(api, f):
    m = f["mimeType"]
    exp = {"document": "text/plain", "spreadsheet": "text/csv", "presentation": "text/plain"}.get(m.split(".")[-1])
    try:
        if exp:
            return api.drive(f"files/{f['id']}/export", {"mimeType": exp}, raw=True)
        if m.startswith("text/"):
            return api.drive(f"files/{f['id']}", {"alt": "media"}, raw=True)
    except Exception as e:  # noqa: BLE001
        return f"<could not read: {e}>"
    return ""


def thai_ok(text):
    text = re.sub(r"https?://\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", " ", text)  # links and addresses are not language
    letters = LETTER.findall(text)
    share = sum(1 for c in letters if THAI.match(c)) / max(1, len(letters))
    parts = PARTICLES.findall(text)
    return share, parts


def grade(api, case, run, sess):
    e, res = case.get("expect", {}), []
    st, s = run.session_state(sess) if sess else (None, {})
    final = "\n".join(t for p in run.parsed for t in p["texts"])

    def check(name, ok, detail=""):
        res.append({"check": name, "ok": bool(ok), "detail": detail})
    if "status" in e:
        check(f"status {e['status']}", st == e["status"], f"got {st}")
    for x in e.get("final_contains", []):
        check(f"final contains {x!r}", x.lower() in final.lower())
    for x in e.get("final_not_contains", []):
        check(f"final lacks {x!r}", x.lower() not in final.lower())
    for x in e.get("final_regex", []):
        check(f"final matches /{x}/", re.search(x, final, re.I | re.S))
    for x in e.get("cards_seen", []):
        check(f"card /{x}/ shown", any(re.search(x, c["action"] + " " + c["title"] + " " + c["node"], re.I) for c in run.cards))
    for x in e.get("cards_not_seen", []):
        check(f"no card /{x}/", not any(re.search(x, c["action"] + " " + c["title"] + " " + c["node"], re.I) for c in run.cards))
    if e.get("thai_final") and final.strip():
        # the platform also streams each data-only step's output as a ```json block: judge only the messages
        shown = re.sub(r"```\s*json.*?```", " ", final, flags=re.S)
        share, parts = thai_ok(shown)
        check("final answer is Thai", share >= 0.5, f"Thai share {share:.0%}")
        check("no gendered particles in final", not parts, str(parts[:3]))
    if e.get("emails_to"):
        for c in run.cards:
            if SENDING.search(c["action"]):
                check(f"recipients of {c['action']}", all(re.match(e["emails_to"], r) for r in c["recipients"]), str(c["recipients"]))
    if e.get("files") or e.get("no_files"):
        files = drive_files_since(api, run.start - datetime.timedelta(seconds=30))
        for want in e.get("files", []):
            hits = [f for f in files if re.search(want["name"], f["name"])
                    and (not want.get("mime") or f["mimeType"].endswith(want["mime"]))]
            check(f"file /{want['name']}/ created", hits, ", ".join(f"{f['name']} {f.get('webViewLink', '')}" for f in hits[:3]))
            if hits and (want.get("contains") or want.get("thai")):
                txt = file_text(api, hits[0])
                for x in want.get("contains", []):
                    check(f"  {hits[0]['name']} contains {x!r}", x in txt)
                if want.get("thai"):
                    share, parts = thai_ok(txt)
                    check(f"  {hits[0]['name']} is Thai", share >= 0.5, f"Thai share {share:.0%}")
                    check(f"  {hits[0]['name']} no gendered particles", not parts, str(parts[:3]))
        for x in e.get("no_files", []):
            hits = [f["name"] for f in files if re.search(x, f["name"])]
            check(f"no file /{x}/", not hits, str(hits[:3]))
    for pr in run.problems:
        check("run problem", False, pr)
    errs = [er for p in run.parsed for er in p["errors"]]
    if errs and not e.get("allow_errors"):
        check("no platform errors", False, json.dumps(errs, ensure_ascii=False)[:400])
    return st, final, res


def run_case(api, ids, path, allow, outroot):
    case = json.loads(pathlib.Path(path).read_text())
    name = case.get("display_name") or template_name(case)
    aid = ids.get(name)
    out = outroot / case["id"]
    out.mkdir(parents=True, exist_ok=True)
    if not aid:
        r = {"id": case["id"], "ok": False, "why": f"agent {name!r} not in app"}
        (out / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"✗ {case['id']}: agent {name!r} not in the app")
        return r
    for step in case.get("setup", []):
        setup(api, step)
    t0 = time.time()
    run = Run(api, case, allow, out)
    sess = run.go(aid)
    st, final, res = grade(api, case, run, sess)
    ok = all(c["ok"] for c in res)
    r = {"id": case["id"], "agent": case["agent"], "lang": case["lang"], "ok": ok, "status": st, "session": sess,
         "minutes": round((time.time() - t0) / 60, 1), "checks": res, "cards": run.cards, "final": final[-6000:],
         "steps": [ev for p in run.parsed for ev in p["events"] if ev["event"] in ("endEvent", "errorEvent")]}
    (out / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(f"{'✓' if ok else '✗'} {case['id']}: status={st} cards={len(run.cards)} {r['minutes']} min  session={(sess or '').split('/')[-1]}")
    for c in res:
        if not c["ok"]:
            print(f"     ✗ {c['check']} {c['detail'][:300]}")
    return r


def setup(api, step):
    """Small fixture actions done as the user through the Drive API."""
    if "drive_trash_name" in step:
        q = f"name contains '{step['drive_trash_name'].get('contains')}' and trashed = false" if isinstance(step["drive_trash_name"], dict) else None
        for f in api.drive("files", {"q": q, "fields": "files(id,name)", "pageSize": 100}).get("files", []) if q else []:
            api.drive(f"files/{f['id']}", method="PATCH", body={"trashed": True})
    if "drive_touch" in step:  # mark a file as edited now (for agents that act on files changed in their time slot)
        api.drive(f"files/{step['drive_touch']}", method="PATCH", body={"modifiedTime": now().strftime("%Y-%m-%dT%H:%M:%S.000Z")})
    if "sleep" in step:
        time.sleep(step["sleep"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", nargs="*")
    ap.add_argument("--config", default="configs/yash-test.json")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--lang", default="")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--allow", default=r"^navya\.agarwal(\+[\w-]+)?@devxlabs\.ai$")
    a = ap.parse_args()
    cfg = json.loads((ROOT / a.config).read_text())
    paths = [pathlib.Path(c) for c in a.cases] or (sorted((ROOT / "tests" / "cases").glob("*.json")) if a.all else [])
    cases = []
    for p in paths:
        c = json.loads(p.read_text())
        if a.only and c["agent"] not in a.only.upper().split(","):
            continue
        if a.lang and c["lang"] != a.lang:
            continue
        cases.append(p)
    if a.dry:
        for p in cases:
            c = json.loads(p.read_text())
            print("ok", c["id"], c["agent"], c["lang"], c.get("display_name") or template_name(c))
        return
    api = Api(cfg)
    ids = agent_ids(api)
    outroot = ROOT / "tests" / "results" / now().strftime("%Y%m%dT%H%M%SZ")
    results = [run_case(api, ids, p, a.allow, outroot) for p in cases]
    (outroot / "summary.json").write_text(json.dumps([{k: r.get(k) for k in ("id", "ok", "status", "session", "minutes")}
                                                      for r in results], ensure_ascii=False, indent=1))
    print(f"\n{sum(1 for r in results if r['ok'])}/{len(results)} passed  -> {outroot.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
