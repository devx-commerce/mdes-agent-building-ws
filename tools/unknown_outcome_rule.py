#!/usr/bin/env python3
"""Add the 'outcome unknown' rule to every write step (16 Oct: GOV-A failed when the Drive MCP answered OUTCOME_UNKNOWN,
"Google Drive didn't confirm whether this went through. Check your Google Drive before trying again", and the step gave up).

  python3 tools/unknown_outcome_rule.py      en and th (write steps are found in en by their 'How writes work here' rule;
                                             the same step ids get the translated rule in th)"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MARK = "OUTCOME_UNKNOWN"
RULE = """If a tool answers that the result is unknown (OUTCOME_UNKNOWN, 'didn't confirm whether this went through'), do not stop and do not report a failure yet: first check whether it happened (search for the file by its exact name in that folder, or the sent email or event), and only if it is not there call the same tool once more with exactly the same values."""


def steps(flow):
    for n in flow["nodes"]:
        yield n
        if "forLoopNode" in n:
            yield from steps(n["forLoopNode"]["subAgentFlow"])


def thai_rule():
    sys.path.insert(0, str(ROOT / "tools"))
    import translate as TR
    g = TR.Gemini("navya.agarwal@devxlabs.ai", "thai-gov-poc", "gemini-3.8-flash")
    protect, restore = TR.make_protect({"OUTCOME_UNKNOWN"})
    return g.batched("th", TR.TO_TH, [RULE], prep=protect, post=restore)[0]


def main():
    th = thai_rule()
    for en in sorted(ROOT.glob("agents/*/en/*.json")):
        t_en = json.loads(en.read_text())
        ids = {n["id"] for n in steps(t_en["definition"]["agentFlow"]) if "How writes work here" in n.get("agentNode", {}).get("instruction", "")}
        for path, rule in ((en, RULE), (en.parent.parent / "th" / en.name, th)):
            t = json.loads(path.read_text())
            done = 0
            for n in steps(t["definition"]["agentFlow"]):
                a = n.get("agentNode")
                if n["id"] in ids and a and MARK not in a["instruction"]:
                    a["instruction"] = a["instruction"].rstrip() + "\n" + rule
                    done += 1
            path.write_text(json.dumps(t, ensure_ascii=False, indent=1))
            print(f"{path.relative_to(ROOT)}: rule added to {done} write steps")


if __name__ == "__main__":
    main()
