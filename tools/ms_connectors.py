#!/usr/bin/env python3
"""Offer the Microsoft 365 connectors next to the Google ones in every agent step (16 Oct, Navya: wherever Gmail is used,
Outlook must be supported; wherever Docs, Word; and so on).

  python3 tools/ms_connectors.py        en and th templates (the th instruction is translated once and reused)

Mapping (Kenil's Microsoft MCP servers; there is no Word or PowerPoint server: Word and PowerPoint files live in OneDrive):
  Gmail -> Outlook Mail + Outlook Contacts   Calendar -> Outlook Calendar   Drive, Docs -> OneDrive   Sheets -> Excel   Slides -> none
Per environment the connector IDs come from configs/*.json (OUTLOOK_MAIL_MCP, ...); empty IDs are dropped by deploy.py
(drop_missing_connectors), so an environment without the Microsoft connectors still deploys."""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAP = {"GMAIL_MCP": ["OUTLOOK_MAIL_MCP", "OUTLOOK_CONTACTS_MCP"], "CALENDAR_MCP": ["OUTLOOK_CALENDAR_MCP"],
       "DRIVE_MCP": ["ONEDRIVE_MCP"], "DOCS_MCP": ["ONEDRIVE_MCP"], "SHEETS_MCP": ["EXCEL_MCP"]}
MARK = "GOOGLE OR MICROSOFT:"
RULE = """GOOGLE OR MICROSOFT: the user may keep their files, mail and calendar in Google Workspace or in Microsoft 365, and this step is given tools for both. Many tools exist twice with the same name (for example search_files): read each tool's description to tell them apart. The Microsoft ones mention OneDrive, Outlook, Excel or Microsoft; the Google ones mention Drive, Docs, Sheets, Gmail or Google Calendar (Google Drive's search_files takes a structured query such as name contains '...').
Always use the Google tool first. Use the Microsoft tool for the same job (OneDrive for files and Word or PowerPoint documents, Excel for spreadsheets, Outlook for mail and contacts, Outlook Calendar for events) only when what this step needs is in Microsoft 365: a OneDrive or SharePoint link or file, an earlier step that found it there, or the Google tool is not connected for this user.
Never conclude that a file, folder, email or event is missing until you have searched for it with the Google tool and then with the Microsoft tool. Keep each file in the place it came from: never copy a user's file from one to the other."""


def steps(flow):
    for n in flow["nodes"]:
        yield n
        if "forLoopNode" in n:
            yield from steps(n["forLoopNode"]["subAgentFlow"])


def key_of(name):
    return name.split("{{")[1].split("}}")[0] if "{{" in name else None


def add_ms(node):
    a = node.get("agentNode")
    if not a or not a.get("connectorToolSelections"):
        return False
    sel = a["connectorToolSelections"]
    have = {key_of(s["dataConnector"]["name"]) for s in sel}
    added = []
    for s in list(sel):
        for ms in MAP.get(key_of(s["dataConnector"]["name"]), []):
            if ms in have or ms in added:
                if ms in added and s.get("mutateEnabled"):  # a writing Google tool makes its Microsoft counterpart writing too
                    next(x for x in sel if key_of(x["dataConnector"]["name"]) == ms)["mutateEnabled"] = True
                continue
            new = {"dataConnector": {"name": f"collections/{{{{{ms}}}}}/dataConnector", "dataSource": "custom_mcp"}, "enabled": True, "searchToolEnabled": True}
            if s.get("mutateEnabled"):
                new["mutateEnabled"] = True
            sel.append(new)
            a.setdefault("dataStoreSpecs", {"specs": []})["specs"].append(
                {"dataStore": f"projects/{{{{PROJECT_NUMBER}}}}/locations/{{{{LOCATION}}}}/collections/default_collection/dataStores/{{{{{ms}_STORE}}}}"})
            added.append(ms)
    return bool(added)


def add_rule(text, rule):
    if MARK in text or "Microsoft 365" in text:
        return text
    cut = text.find("\nTools for this step")
    if cut < 0:
        cut = text.find("\nเครื่องมือสำหรับขั้นตอนนี้")
    return text[:cut] + "\n" + rule + text[cut:] if cut >= 0 else text + "\n" + rule


def thai_rule():
    sys.path.insert(0, str(ROOT / "tools"))
    import translate as TR
    g = TR.Gemini("navya.agarwal@devxlabs.ai", "thai-gov-poc", "gemini-3.8-flash")
    protect, restore = TR.make_protect(set())
    return g.batched("th", TR.TO_TH, [RULE], prep=protect, post=restore)[0]


def main():
    th = None
    for path in sorted(ROOT.glob("agents/*/*/*.json")):
        if path.name.endswith(".review.json"):
            continue
        t = json.loads(path.read_text())
        lang = t.get("lang", path.parent.name)
        if lang == "th" and th is None:
            th = thai_rule()
        n_steps = 0
        for n in steps(t["definition"]["agentFlow"]):
            if add_ms(n):
                n["agentNode"]["instruction"] = add_rule(n["agentNode"]["instruction"], RULE if lang == "en" else th)
                n_steps += 1
        path.write_text(json.dumps(t, ensure_ascii=False, indent=1))
        print(f"{path.relative_to(ROOT)}: Microsoft connectors added to {n_steps} steps")


if __name__ == "__main__":
    main()
