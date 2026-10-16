#!/usr/bin/env python3
"""Replace Gemini Enterprise Deep Research (Research MCP: deep_research_plan / _run / _check) with our own research subgraph.

  python3 tools/research_subgraph.py            rewrite GOV-B, RES-A and RES-C, en and th (th: only the new texts are translated)
  python3 tools/research_subgraph.py --en       English only (no translation)

Why: the native Deep Research behind the Research MCP is replaced by a workflow we benchmarked against it (16 Oct, judge
gemini-3.1-pro, both passes): ours won GOV-B, RES-C and EXE-B; run time ~11 min, the same as native.

The subgraph (one per research chain):
  plan (no tools) -> plan card (agents that have one) -> loop over sub-questions:
      <p>_web   Google Search only, sees only its own sub-question
      <p>_drive internal documents only (Drive), only where the agent has an internal folder/library
  -> <p>_review (gap review, web follow-ups)
  -> <p>_synth (no tools, numbers the sources as it cites them and writes the source list; a code step for this took 8 min on ~200 findings, 16 Oct) -> <p>_save (plain MCP step: Drive create_file, content from variables: the model never retypes the report)
Contract kept: the start step still returns job_id / started / questions / problems; the result step still returns
status / doc_id / link / references / research_ok / problems. Every later step and condition is unchanged."""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = "gemini-3.8-flash"
DRIVE_STORE = "projects/{{PROJECT_NUMBER}}/locations/{{LOCATION}}/collections/default_collection/dataStores/{{DRIVE_MCP_STORE}}"
DRIVE_SEL = {"dataConnector": {"name": "collections/{{DRIVE_MCP}}/dataConnector", "dataSource": "custom_mcp"}, "enabled": True, "searchToolEnabled": True}
TONE = "Tone: neutral and polite. Never use the gendered polite particles ครับ, ค่ะ, คะ, นะคะ or นะครับ in anything you write (messages, emails, documents, slides)."
DATA_ONLY = "Return data only: never write a message to the user, never ask anything, never wait for an answer; always finish by returning the output fields."
NOT_RUN = "A value that reads like <no value provided for ...> means that step did not run on this path: treat it as empty."

T = {"str": "STRING", "num": "NUMBER", "bool": "BOOLEAN"}


def schema(spec):
    props = {}
    for i, (k, v) in enumerate(spec.items()):
        if isinstance(v, str):
            p = {"description": k.replace("_", " "), "type": T[v]}
        elif isinstance(v, list):
            it = v[0]
            p = {"description": k.replace("_", " "), "type": "ARRAY",
                 "items": ({"description": k.replace("_", " "), "type": "OBJECT", **schema(it)} if isinstance(it, dict) else {"description": k, "type": T[it]})}
        else:
            p = {"description": k.replace("_", " "), "type": "OBJECT", **schema(v)}
        p["additionalProperties"] = {"display_order": i}
        props[k] = p
    return {"properties": props, "required": list(spec)}


def agent(id, name, instruction, out, web=False, drive=False):
    a = {"model": MODEL, "instruction": instruction, "outputDisplayEnabled": True}
    if web:
        a["selectedTools"] = {"tools": [{"name": "googleSearch"}]}
    if drive:
        a["dataStoreSpecs"] = {"specs": [{"dataStore": DRIVE_STORE}]}
        a["connectorToolSelections"] = [dict(DRIVE_SEL)]
    return {"id": id, "displayName": name, "nodeType": "AGENT_NODE", "agentNode": a, "outputSchema": schema(out)}


FINDING = {"id": "str", "claim": "str", "evidence": "str", "source_title": "str", "source_url": "str", "source_type": "str", "published": "str", "confidence": "str"}
SUBQ = {"id": "str", "question": "str", "brief": "str", "why_it_matters": "str", "search_terms": "str", "source_types": "str", "check_internal_docs": "bool"}

PLAN_RULES = """1. Restate the request as one precise research question, the decision or output it serves and who will read the result.
   Note the country, sector, time window and any constraints the request gives. Assume Thailand when no country is given.
2. Break it into 4 to 7 sub-questions that together answer it fully and do not overlap. Cover, where relevant: current facts and figures; what others (other countries, provinces, peers) did and what worked; causes and drivers; options; costs, risks and constraints (legal, budget, authority); recent developments (last 12 months).
3. Each sub-question will be researched by a separate researcher who sees ONLY that one item: not the request, not the other sub-questions. So make every item self-contained:
   - `question`: one specific, answerable question in Thai naming the country, sector, place and time window explicitly (never "the province", "this", "the above").
   - `brief`: 2 to 4 sentences of context: the overall request in one line, what the answer will be used for, what is out of scope, and the time window.
   - `why_it_matters`: how this answer feeds the final result.
   - `search_terms`: 3 to 6 web search queries, in Thai and in English.
   - `source_types`: the kinds of sources that count most.
   - `check_internal_docs`: {internal_rule}
   - `id`: Q1, Q2, ...
4. Do not answer any question yourself. No tools."""


def planner_instruction(question, context, internal, changes=None):
    internal_rule = ("true if the internal documents described here could hold part of the answer: " + internal) if internal else "always false (this research uses public sources only)"
    ch = f"\nChanges the user asked for on the first plan (apply them exactly): {changes}" if changes else ""
    return f"""You are the lead research strategist. You plan research; you do not do it. {DATA_ONLY}
Research request: "{question}"
{context}{ch}

{PLAN_RULES.replace('{internal_rule}', internal_rule)}
Also return, for the approval card: plan_questions = the sub-questions' `question` texts as a list, in order; plan_text = those questions as a numbered list, one per line, with nothing else (no greeting, no closing, no 'I', no request to reply).
plan_ok = true only if there are 4 to 7 sub-questions; session_id = 'workflow-plan'; problems = what went wrong, or empty.
{TONE}"""


PLANNER_OUT = {"session_id": "str", "plan_text": "str", "plan_questions": ["str"], "plan_ok": "bool", "problems": "str", "sub_questions": [SUBQ]}
START_OUT = {"job_id": "str", "started": "bool", "questions": ["str"], "problems": "str", "sub_questions": [SUBQ]}


def chooser_instruction(first, changed):
    return f"""Pick the research plan the user approved last. {DATA_ONLY} Use no tools. {NOT_RUN}
Changed plan: ok ${{{changed}.plan_ok}}; sub-questions ${{{changed}.sub_questions}}.
First plan: ok ${{{first}.plan_ok}}; sub-questions ${{{first}.sub_questions}}.
Use the changed plan if its ok is true, otherwise the first plan.
sub_questions = that plan's sub-questions copied exactly (every field); questions = their `question` texts in order; started = true only if there is at least one sub-question; job_id = 'workflow-research'; problems = empty, or why no plan was usable.
{TONE}"""


def inline_start_instruction(question, context, internal):
    return planner_instruction(question, context, internal).replace(
        "Also return, for the approval card: plan_questions = the sub-questions' `question` texts as a list, in order; plan_text = those questions as a numbered list, one per line, with nothing else (no greeting, no closing, no 'I', no request to reply).\nplan_ok = true only if there are 4 to 7 sub-questions; session_id = 'workflow-plan'; problems = what went wrong, or empty.",
        "Also return: questions = the sub-questions' `question` texts in order; started = true only if there are 4 to 7 sub-questions; job_id = 'workflow-research'; problems = what went wrong, or empty.")


def web_instruction(S):
    return f"""You are a research investigator. You work on ONE sub-question, given below, and you know nothing else about the wider project. Do not guess what the wider project is. {DATA_ONLY}

Sub-question ${{{S}.id}}: ${{{S}.question}}
Context: ${{{S}.brief}}
Why it matters: ${{{S}.why_it_matters}}
Suggested searches: ${{{S}.search_terms}}
Preferred sources: ${{{S}.source_types}}

How to work:
1. Search the web with Google Search only: run the suggested searches, then your own follow-up searches as you learn (at least 5 searches, up to 12). Prefer primary and official sources; use news only for recent events. Do not search Drive: internal documents are researched separately.
2. Record each useful fact as a finding: `id` (the sub-question id, "-W" and a running number: e.g. Q2-W1, Q2-W2, ...), `claim` (one sentence), `evidence` (the exact figure, quote or detail that supports it), `source_title` (the page's own title or the publisher plus a short description, not just the site name),
   `source_url`: the link EXACTLY as the search tool gave it for that result, copied character for character. Google Search gives long links that start with https://vertexaisearch.cloud.google.com/grounding-api-redirect/ : copy the whole link. Never shorten a link to a site name and never build a URL yourself. `source_type` (government / academic / international org / industry / news), `published` (date or year, "unknown" if not shown), `confidence` (high = primary or several agreeing sources; medium = one reputable source; low = weak or indirect).
   15 to 25 findings from at least 12 different pages: spread the evidence across sources, and run more searches when a page repeats what you already have. Only facts you actually found in a source. Never invent a source, URL, figure or date. Where sources disagree, record both.
3. `answer`: a direct answer to the sub-question in 3 to 6 sentences, citing findings by their source titles.
4. `open_gaps`: what you could not find or confirm, and why. "none" if nothing.
5. `searches_run`: how many searches you ran.
NO SEARCH, NO FINDINGS: every finding must come from a Google Search result you received in this step. If you have no Google Search tool here, write no findings at all: return findings as an empty list, answer 'WEB SEARCH NOT AVAILABLE', open_gaps 'WEB SEARCH NOT AVAILABLE' and searches_run 0. Never write a finding, title or link from memory. A real Google Search link ends in a long random code, never in readable words.
Read only: never create, change or send anything.
{TONE}"""


def drive_instruction(S, internal):
    return f"""You are a research investigator for internal documents. You work on ONE sub-question, given below, and you know nothing else about the wider project. {DATA_ONLY}

Sub-question ${{{S}.id}}: ${{{S}.question}}
Context: ${{{S}.brief}}
Check internal documents: ${{{S}.check_internal_docs}}
Internal documents you may use: {internal}

If "Check internal documents" is false, or there are no internal documents, do nothing: return `findings` as an empty list, `answer` "not checked" and `open_gaps` "none".
Otherwise:
1. Use only the internal documents above (Drive: search_files limited to them, read_file_content). Never search the web, and never use other files.
2. Read the 1 to 4 most relevant files in full. Ignore files that are clearly unrelated.
3. Record each useful fact as a finding: `id` (the sub-question id, "-D" and a running number: e.g. Q2-D1), `claim`, `evidence` (exact figure or quote), `source_title` (the file name), `source_url` (the file's link: https://drive.google.com/file/d/<file ID>/view), `source_type` "internal", `published` (the date in the document, or "unknown"), `confidence`.
   Only facts that are in the files. Never invent a file, link, figure or date. 0 to 12 findings; an empty list is a valid answer.
4. `answer`: what the internal documents say about the sub-question in 2 to 5 sentences, or "no relevant internal documents".
5. `open_gaps`: what the documents do not cover. "none" if nothing.
Read only: never create, change or send anything.
{TONE}"""


def review_instruction(p, start, has_drive):
    drive_line = f"\nInternal documents per sub-question: ${{{p}_loop.output[*].{p}_drive}}" if has_drive else ""
    return f"""You are the lead research strategist reviewing your team's research before the report is written. {DATA_ONLY}
Sub-questions: ${{{start}.sub_questions}}
Web research per sub-question: ${{{p}_loop.output[*].{p}_web}}{drive_line}

1. Check coverage: for each sub-question, is it answered with sourced findings? Note any sub-question with no or weak evidence, open gaps the investigators reported, and anything the research needs that no sub-question covered.
2. Check quality: claims that rest on one low-confidence source, figures that conflict between sources, findings older than 3 years where newer data likely exists, and claims whose source is missing or does not look real.
   Also compare internal documents with web sources: where they disagree, record it as a conflict and say which side is more current or authoritative.
3. Pick the 3 to 6 most important gaps or conflicts and close them yourself with Google Search (web only). Run at least one search per gap. Follow-up findings must come from search results you received in this step; if you have no Google Search tool, return followup_findings empty and say 'WEB SEARCH NOT AVAILABLE' in conflicts. Never write a finding or link from memory.
4. Return:
   - `gaps`: every gap or conflict you found, with `gap`, `why_it_matters`, `action` (what you searched), `resolved` (true/false), `note`.
   - `followup_findings`: 8 to 20 new findings from your follow-up searches, same fields as the investigators' findings, `id` R-F1, R-F2, ..., each `source_url` copied exactly as the search tool gave it (whole link; never a bare site name). Only facts you actually found; never invent a source, URL, figure or date.
   - `conflicts`: each conflicting figure or claim, the sources on each side, and which is more reliable and why. "none" if none.
   - `weak_claims`: claims that should not be used or should be flagged as uncertain, and why. "none" if none.
Read only: never create, change or send anything.
{TONE}"""


def number_instruction(p, has_drive):
    drive_line = f"\nInternal: ${{{p}_loop.output[*].{p}_drive.findings}}" if has_drive else ""
    return f"""Give every source a number before the report is written. Do this with code, never by hand. {DATA_ONLY}

Evidence (each finding has an id, source_title, published and source_url):
Web: ${{{p}_loop.output[*].{p}_web.findings}}{drive_line}
Follow-up: ${{{p}_review.followup_findings}}

You cannot run code yourself: call transfer_to_agent with agent_name "file_and_coding_agent" and give it the evidence copied exactly (id, source_title, published, source_url only) with this task. Never write or read files; one code run.
Task (Python): give each distinct source_url a number 1, 2, 3, ... in the order the findings appear. Print exactly two lines:
line 1: a JSON object mapping every finding id to its number, e.g. {{"Q1-W1": 1, "Q1-W2": 1, "Q2-D1": 2}}
line 2: the count of findings and the count of distinct sources.
Then print the source list, one line per number: "[n] <source_title> (<published>) - <source_url>".
Return `id_map` = line 1 exactly, `sources_md` = the source list exactly as printed, `n_sources` = the number of distinct sources.
If the code agent fails, return `id_map` "{{}}", `sources_md` "NUMBERING FAILED: <reason>" and `n_sources` 0.
{TONE}"""


def synth_instruction(p, start, context, has_drive):
    drive_line = f"\nInternal documents per sub-question: ${{{p}_loop.output[*].{p}_drive}}" if has_drive else ""
    return f"""You are the lead research strategist writing the final research report. You have NO tools. Use ONLY the evidence below; add no facts, figures, sources or dates from your own knowledge. If the evidence does not support a point, leave it out or say it is not known. {DATA_ONLY}
{context}
Sub-questions: ${{{start}.sub_questions}}
Web research per sub-question: ${{{p}_loop.output[*].{p}_web}}{drive_line}
Reviewer's follow-up findings: ${{{p}_review.followup_findings}}
Reviewer's gaps: ${{{p}_review.gaps}}
Conflicts: ${{{p}_review.conflicts}}
Claims to drop or flag: ${{{p}_review.weak_claims}}

If the web research above says WEB SEARCH NOT AVAILABLE, or there are no web findings at all, write no report: report_md = 'NO RESEARCH: web search was not available in this run', n_sources = 0.
Otherwise write `report_md` in Thai, in Markdown:
# <title>
## บทสรุปสำหรับผู้บริหาร  (5 to 8 bullets: the answer, the key numbers, the recommendation)
## ข้อค้นพบสำคัญ  (one sub-section per theme, not per investigator; say when a point comes from internal documents)
## การวิเคราะห์และนัยต่อการตัดสินใจ  (what the evidence means; compare options where relevant)
## ข้อเสนอแนะ  (numbered, concrete, each tied to evidence; say who would act and the first step)
## ความเสี่ยง ความไม่แน่นอน และข้อมูลที่ขัดแย้งกัน  (every conflict from the review, both sides cited)
## ช่องว่างและข้อจำกัดของการค้นคว้า  (what is still unknown and how to close it)
Citations: number the sources in the order you first cite them: one number per distinct source_url (findings that share a link share a number). Right after each sentence, cite the numbers of the findings it rests on, e.g. [3] or [3, 12]. Every factual sentence carries at least one number. Write no URLs inside the text.
End the report with "## แหล่งอ้างอิง": one line per number, in order: "[n] <source_title> (<published>) - <source_url>", with the source_url copied EXACTLY from the finding, character for character (never shortened, never rebuilt). List only sources you cited; every number you cited must be listed.
Use the evidence broadly: cite every relevant finding not listed under "claims to drop", so the report rests on all the distinct sources the team found. When the evidence has 60 or more distinct links, the source list normally has 60 or more entries; never leave out a relevant source to keep the list short. Keep the text to roughly 2,500 to 4,000 words.
Never write ข้อมูลทดสอบ, TEST, 'TEST DATA' or 'not real' anywhere, even if a source contains it.
Also return `n_sources` (how many numbered sources the list has) and `confidence` (high / medium / low for the overall answer, with one sentence why).
{TONE}"""


def save_node(p, title, folder):
    return {"id": f"{p}_save", "displayName": "Save the research report", "nodeType": "MCP_NODE",
            "mcpNode": {"dataConnector": {"name": "projects/{{PROJECT_NUMBER}}/locations/{{LOCATION}}/collections/{{DRIVE_MCP}}/dataConnector", "dataSource": "custom_mcp"},
                        "tool": {"name": "create_file"},
                        "inputParameters": {"title": title, "contentMimeType": "text/markdown", "parentId": folder,
                                            "textContent": f"${{{p}_synth.report_md}}"}},
            "outputSchema": {"properties": {"output": {"type": "STRING", "description": "the created file (JSON with id and viewUrl)"}}, "required": []}}


def result_instruction(p):
    return f"""Report what the research produced. {DATA_ONLY} Use no tools. {NOT_RUN}
Saved report (the Drive tool's answer): ${{{p}_save.output}}
Numbered sources: ${{{p}_synth.n_sources}}
Source list of the report: ${{{p}_synth.report_md}}
Research is NOT usable when: the number of sources is 0; the report starts with 'NO RESEARCH'; or most links in its source list look invented (a Google Search link 'grounding-api-redirect/' followed by readable words instead of a long random code). Then research_ok = false and problems = 'web search was not available, so no research was done' (or the reason).
doc_id = the saved file's id; link = its viewUrl (or https://docs.google.com/document/d/<id>/edit); references = the number of sources; status = 'done' if there is a file id, otherwise 'failed';
research_ok = true only if there is a file id and the research is usable; problems = empty, or what went wrong (for example the save was cancelled).
{TONE}"""


RESULT_OUT = {"status": "str", "doc_id": "str", "link": "str", "references": "num", "research_ok": "bool", "problems": "str"}


def chain_nodes(p, start, internal, title, folder, context):
    S = f"{p}_loop_start.sq"
    inner = [{"id": f"{p}_loop_start", "displayName": "Each sub-question", "nodeType": "PRIVATE_TRIGGER", "privateTrigger": {}, "outputSchema": schema({"sq": SUBQ})},
             agent(f"{p}_web", "Research one sub-question on the web", web_instruction(S),
                   {"sub_question_id": "str", "answer": "str", "findings": [FINDING], "open_gaps": "str", "searches_run": "num"}, web=True)]
    if internal:
        inner.append(agent(f"{p}_drive", "Check internal documents for one sub-question", drive_instruction(S, internal),
                           {"sub_question_id": "str", "answer": "str", "findings": [FINDING], "open_gaps": "str"}, drive=True))
    edges = [{"sourceNodeId": a["id"], "targetNodeId": b["id"]} for a, b in zip(inner, inner[1:])]
    loop = {"id": f"{p}_loop", "displayName": "Research each sub-question", "nodeType": "FOR_LOOP_NODE",
            "forLoopNode": {"itemsListVariable": f"{start}.sub_questions", "currentItemVariable": "sq", "subAgentFlow": {"nodes": inner, "edges": edges}}}
    review = agent(f"{p}_review", "Review gaps and follow up", review_instruction(p, start, bool(internal)),
                   {"gaps": [{"gap": "str", "why_it_matters": "str", "action": "str", "resolved": "bool", "note": "str"}],
                    "followup_findings": [FINDING], "conflicts": "str", "weak_claims": "str"}, web=True)
    synth = agent(f"{p}_synth", "Write the research report", synth_instruction(p, start, context, bool(internal)), {"report_md": "str", "n_sources": "num", "confidence": "str"})
    save = save_node(p, title, folder)
    seq = [loop, review, synth, save]
    return seq, [{"sourceNodeId": a["id"], "targetNodeId": b["id"]} for a, b in zip(seq, seq[1:])]


# ---------- per agent ----------
C_GOVB = "Context: a briefing for the head of a Thai provincial office, prepared by its policy and planning analyst. Use public sources (prefer official Thai government sources). Where sources give different numbers for the same thing, show them side by side with each source. Cover what the province can do within its own authority."
C_RESA = "Context: a policy paper for a government client by a university policy research institute. Cover official targets and measures, investment approvals vs what was built, official statistics year by year, company announcements vs delivery, and anything else the goal needs. Prefer official Thai sources (government agencies, BOI, Department of Land Transport, committees) and reputable reporting. Where numbers differ, keep each source's number, date and what exactly it measures."
C_WATCH = "Context: the weekly evidence watch of a university policy research institute: only what is new since the last check, each item with what changed, the number with its date and what it measures."
C_RESC = "Context: a weekly scan for research funding calls for a Thai university researcher: each call with its title, funder, announcement link, exact deadline, budget ceiling, duration, eligibility and required documents."

AGENTS = {
    "government-officer/policy-briefing-memo": {
        "planners": [("propose_plan", "${get_ready.request}", C_GOVB, None), ("replan", "${get_ready.request}", C_GOVB, "${check_changes.changes}")],
        "internal_for_plan": "the documents directly in the Drive folder ${get_ready.internal_folder_id} (if that is empty, there are none)",
        "chains": [dict(p="r", start="deep_research", wait="wait_research", result="research_result", chooser=("propose_plan", "replan"),
                        internal="only the files directly in the Drive folder ${get_ready.internal_folder_id} (if that is empty, there are none)",
                        title="รายงานการค้นคว้าฉบับเต็ม – ${get_ready.topic_title}", folder="${get_ready.save_folder_id}", context=C_GOVB)],
    },
    "researcher/evidence-review": {
        "planners": [("propose_plan", "${find_state.goal}", C_RESA, None), ("replan", "${find_state.goal}", C_RESA, "${check_changes.changes}")],
        "internal_for_plan": "the researcher's library files: ${get_library.library_files}",
        "chains": [dict(p="r", start="deep_research", wait="r_wait", result="r_result", chooser=("propose_plan", "replan"),
                        internal="only these library files: ${get_library.library_files} (if empty, there are none)",
                        title="รายงานการค้นคว้า – ${get_library.topic_title}", folder="${find_state.setup_folder_id}", context=C_RESA),
                   dict(p="w", start="watch_research", wait="w_wait", result="w_result",
                        question="What is new since ${w_read.last_check} about ${find_state.topic}: new official statistics (e.g. monthly registrations), new government measures, company announcements (new plants, postponements), new research. For each item: what changed, the number with its date and what it measures, and the source URL. Compare with these current claims: ${w_read.table_rows}",
                        internal=None, title="การติดตามหลักฐาน – ${find_state.topic} – ${find_state.today}", folder="${find_state.setup_folder_id}", context=C_WATCH)],
    },
    "researcher/funding-calls": {
        "planners": [],
        "chains": [dict(p="s", start="search_calls", wait="wait_research", result="research_result",
                        question="Calls for research proposals (ประกาศรับข้อเสนอโครงการ) announced since ${find_setup.last_check} that are still open today (${find_setup.today}; the deadline must be after this date), from these funders: ${find_setup.funders}, and the wider web (Thai PMUs บพข. บพท. บพค., วช., ministries, foundations, international funders), on these topics: ${find_setup.profile}. For each call: title, funder, announcement URL, deadline (exact date), budget ceiling, duration, eligibility (e.g. private-sector co-funding, area-based), required documents.",
                        internal=None, title="ประกาศทุนใหม่ – ${find_setup.today}", folder="${find_setup.output_folder_id}", context=C_RESC)],
    },
}

CARD_NOTE = re.compile(r"\n\nหลังกด Approve จะมีการ์ด Send.*?(?=\n\nถ้าออกจากหน้านี้|$)", re.S)


def rewrite(t, spec):
    flow = t["definition"]["agentFlow"]
    N = {n["id"]: n for n in flow["nodes"]}
    new_texts = []  # (dict, key) of every text written here, for translation

    def set_agent(nid, instruction, out, name=None):
        n = N[nid]
        a = n["agentNode"]
        a["instruction"] = instruction
        a["model"] = MODEL
        for k in ("dataStoreSpecs", "connectorToolSelections", "selectedTools"):
            a.pop(k, None)
        n["outputSchema"] = schema(out)
        if name:
            n["displayName"] = name
        new_texts.append((a, "instruction"))
        if name:
            new_texts.append((n, "displayName"))

    for nid, q, ctx, changes in spec["planners"]:
        set_agent(nid, planner_instruction(q, ctx, spec.get("internal_for_plan"), changes), PLANNER_OUT, "Plan the research")
    for c in spec["chains"]:
        p = c["p"]
        if c.get("chooser"):
            set_agent(c["start"], chooser_instruction(*c["chooser"]), START_OUT, "Use the approved plan")
        else:
            set_agent(c["start"], inline_start_instruction(c["question"], c["context"], c["internal"]), START_OUT, "Plan the research")
        seq, inner_edges = chain_nodes(p, c["start"], c["internal"], c["title"], c["folder"], c["context"])
        # the wait step goes; whatever led to it now leads to the loop; the saved report leads to the result step
        flow["nodes"] = [n for n in flow["nodes"] if n["id"] != c["wait"]]
        for e in flow["edges"]:
            if e["targetNodeId"] == c["wait"]:
                e["targetNodeId"] = seq[0]["id"]
        flow["edges"] = [e for e in flow["edges"] if e["sourceNodeId"] != c["wait"]] + inner_edges + [{"sourceNodeId": seq[-1]["id"], "targetNodeId": c["result"]}]
        idx = [n["id"] for n in flow["nodes"]].index(c["result"])
        flow["nodes"][idx:idx] = seq
        set_agent(c["result"], result_instruction(p), RESULT_OUT, "Check the saved report")
        for n in seq:
            for sub in ([n] + n.get("forLoopNode", {}).get("subAgentFlow", {}).get("nodes", [])):
                if sub.get("agentNode"):
                    new_texts.append((sub["agentNode"], "instruction"))
                if sub.get("displayName"):
                    new_texts.append((sub, "displayName"))
        N = {n["id"]: n for n in flow["nodes"]}
    # the plan card no longer needs the Deep Research 'Send' card note
    for n in flow["nodes"]:
        m = n.get("approvalNode", {}).get("message", "")
        if "deep_research" not in m and ("การ์ด Send" in m or "Send card" in m):
            n["approvalNode"]["message"] = CARD_NOTE.sub("", m)
    # nothing may still reference the Research MCP
    left = [n["id"] for n in flow["nodes"] if "RESEARCH_MCP" in json.dumps(n) or "deep_research_" in json.dumps(n)]
    return new_texts, left


def translate_new(texts, flow):
    sys.path.insert(0, str(ROOT / "tools"))
    import translate as TR
    g = TR.Gemini("navya.agarwal@devxlabs.ai", "thai-gov-poc", "gemini-3.8-flash")
    protect, restore = TR.make_protect(TR.field_names(flow))
    src = [TR.thai_only(d[k]) for d, k in texts]
    out = [TR.drop_glosses(x) for x in g.batched("th", TR.TO_TH, src, prep=protect, post=restore)]
    for (d, k), s in zip(texts, out):
        d[k] = s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", action="store_true", help="English templates only")
    ap.add_argument("--th", action="store_true", help="Thai templates only")
    a = ap.parse_args()
    for key, spec in AGENTS.items():
        persona, name = key.split("/")
        for lang in (["en"] if a.en else ["th"] if a.th else ["en", "th"]):
            path = ROOT / "agents" / persona / lang / f"{name}.json"
            t = json.loads(path.read_text())
            texts, left = rewrite(t, spec)
            if lang == "th":
                translate_new(texts, t["definition"]["agentFlow"])
            t["_built_from"] = "tools/research_subgraph.py (16 Oct: Deep Research MCP replaced by our research subgraph). " + t.get("_built_from", "")
            path.write_text(json.dumps(t, ensure_ascii=False, indent=1))
            print(f"{path.relative_to(ROOT)}: {len(texts)} texts rewritten; still mentioning the Research MCP: {left or 'none'}")


if __name__ == "__main__":
    main()
