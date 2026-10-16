#!/usr/bin/env python3
"""Add the code-execution rule to every step that calculates (16 Oct: no Analysis MCP; maths by Gemini's own code execution).

  python3 tools/code_rule.py          en and th (the th rule is translated once and reused)

Evidence (mdes-work-log/wf/bench/code_exec/FINDINGS.md): steps hand code to the platform agent file_and_coding_agent through
transfer_to_agent; 8/8 runs exact once the hand-off was named in the instruction. One code run holds about 300 rows of pasted
data and every run starts empty (no files), so this rule is for small inputs; the steps below handle a few dozen numbers."""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARK = "CALCULATIONS:"
RULE = """CALCULATIONS: do every calculation in this step (sums, totals, averages, percentages, ratios, differences, growth rates, unit conversions, date arithmetic) with code, never in your head. You cannot run code yourself: hand it to the platform's code agent with transfer_to_agent, agent_name "file_and_coding_agent", giving it the input numbers copied exactly and saying what to compute; it writes and runs the Python and returns the printed results. Ask it to print each input next to each result. Never write or read files: each code run starts empty. Copy every result exactly as printed; never round or recompute by hand. If the transfer fails or the code errors twice, stop: mark the affected values as not computed (-1) and say so in problems or flags; never estimate. For calculations only, this rule overrides any 'no tools' line in this step."""
STEPS = {
    "government-officer/monthly-operations-report": ["read_and_table", "compare_months"],
    "executive/peer-benchmark-pack": ["write_table", "go_write_table"],
    "researcher/evidence-review": ["build_evidence", "answer_questions"],
    "researcher/funding-calls": ["rate_calls"],
}


def steps(flow):
    for n in flow["nodes"]:
        yield n
        if "forLoopNode" in n:
            yield from steps(n["forLoopNode"]["subAgentFlow"])


def thai_rule():
    sys.path.insert(0, str(ROOT / "tools"))
    import translate as TR
    g = TR.Gemini("navya.agarwal@devxlabs.ai", "thai-gov-poc", "gemini-3.8-flash")
    protect, restore = TR.make_protect({"transfer_to_agent", "agent_name", "file_and_coding_agent"})
    return g.batched("th", TR.TO_TH, [RULE], prep=protect, post=restore)[0]


def add(text, rule):
    if MARK in text or "file_and_coding_agent" in text:
        return text, False
    cut = text.find("\nTools for this step")
    if cut < 0:
        cut = text.find("\nเครื่องมือสำหรับขั้นตอนนี้")
    return (text[:cut] + "\n" + rule + text[cut:] if cut >= 0 else text + "\n" + rule), True


def main():
    th = None
    for key, ids in STEPS.items():
        persona, name = key.split("/")
        for lang in ("en", "th"):
            if lang == "th" and th is None:
                th = thai_rule()
            path = ROOT / "agents" / persona / lang / f"{name}.json"
            t = json.loads(path.read_text())
            done = []
            for n in steps(t["definition"]["agentFlow"]):
                if n["id"] in ids and n.get("agentNode"):
                    n["agentNode"]["instruction"], changed = add(n["agentNode"]["instruction"], RULE if lang == "en" else th)
                    if changed:
                        done.append(n["id"])
            path.write_text(json.dumps(t, ensure_ascii=False, indent=1))
            print(f"{path.relative_to(ROOT)}: rule added to {done or 'nothing new'}; missing: {sorted(set(ids) - {n['id'] for n in steps(t['definition']['agentFlow'])})}")


if __name__ == "__main__":
    main()
