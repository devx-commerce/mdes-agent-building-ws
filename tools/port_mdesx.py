#!/usr/bin/env python3
"""One-off port (14 Oct 2026) of every template to Kenil's newer MCP connectors (mdesx-*), which mirror the native
connectors more closely. Renames from Kenil (Slack, 14 Oct 11:55):
  send_email -> send_message, read_file_text -> read_file_content, create_file_if_absent -> search_files then create_file,
  Docs insert_sheets_chart removed, Slides create_presentation_from_outline has no folder option yet (deck lands in My
  Drive; we move it with Drive update_file).
Idempotent: running it twice changes nothing."""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TXT = {
    "absent": {"en": "create_file (only after search_files finds no file with that exact name in that folder)",
               "th": "create_file (เฉพาะเมื่อ search_files ไม่พบไฟล์ชื่อเดียวกันทุกตัวอักษรในโฟลเดอร์นั้น)"},
    "move": {"en": "\nThe Slides tool has no folder option: the deck is created in My Drive. Right after it returns the new deck's ID, "
                   "call Drive update_file ONCE with fileId = that ID and parentId = {folder}, so the deck sits in that folder. "
                   "Never pass parentId to create_presentation_from_outline.",
             "th": "\nเครื่องมือ Slides ไม่มีตัวเลือกโฟลเดอร์ งานนำเสนอจะถูกสร้างใน My Drive เมื่อได้รับ ID ของงานนำเสนอใหม่แล้ว "
                   "ให้เรียก Drive update_file หนึ่งครั้งทันที โดยกำหนด fileId = ID นั้น และ parentId = {folder} เพื่อย้ายงานนำเสนอไปไว้ในโฟลเดอร์ดังกล่าว "
                   "ห้ามส่ง parentId ให้ create_presentation_from_outline"},
    "folder": {"en": "the folder this step names for the deck", "th": "โฟลเดอร์ที่ขั้นตอนนี้กำหนดไว้สำหรับงานนำเสนอ"},
    "chart": {"en": ("If ${chart.made} is false, call no tool and set inserted = false. Otherwise call Docs append_to_doc ONCE on document "
                     "${chapter_ref.doc_id} with one line: 'แผนภูมิประกอบหัวข้อ 4.2 (Google Sheets): ' followed by the link "
                     "https://docs.google.com/spreadsheets/d/<spreadsheet ID>/edit, where the spreadsheet ID is ${chart_sheet.sheet_id}. "
                     "The chart stays in that spreadsheet: the Docs tools cannot embed a chart. inserted = true only if confirmed.\n\n"
                     "Tools for this step (their inputs are described by the tools themselves): Docs MCP: append_to_doc."),
              "th": ("หาก ${chart.made} เป็น false ห้ามเรียกเครื่องมือใด และกำหนด inserted = false มิฉะนั้นให้เรียก Docs append_to_doc หนึ่งครั้งกับเอกสาร "
                     "${chapter_ref.doc_id} โดยเพิ่มหนึ่งบรรทัด: 'แผนภูมิประกอบหัวข้อ 4.2 (Google Sheets): ' ตามด้วยลิงก์ "
                     "https://docs.google.com/spreadsheets/d/<ID สเปรดชีต>/edit โดย ID สเปรดชีตคือ ${chart_sheet.sheet_id} "
                     "แผนภูมิจะอยู่ในสเปรดชีตนั้น เนื่องจากเครื่องมือ Docs ไม่สามารถฝังแผนภูมิได้ inserted = true เฉพาะเมื่อได้รับการยืนยัน\n\n"
                     "เครื่องมือสำหรับขั้นตอนนี้ (รายละเอียดอินพุตอธิบายไว้ในเครื่องมือ): Docs MCP: append_to_doc")},
}
TAIL = {"en": "\nNever write a message to the user and never ask for confirmation in text: call the tool directly (the platform shows its own confirmation card).",
        "th": "\nห้ามเขียนข้อความถึงผู้ใช้และห้ามขอการยืนยันเป็นข้อความ ให้เรียกเครื่องมือทันที (ระบบจะแสดงการ์ดยืนยันเอง)"}


def nodes(flow):
    for n in flow.get("nodes", []):
        yield n
        if "forLoopNode" in n:
            yield from nodes(n["forLoopNode"].get("subAgentFlow", {}))


def drive_rw(a):
    """Make sure the step can use the Drive connector with writes."""
    store = "projects/{{PROJECT_NUMBER}}/locations/{{LOCATION}}/collections/default_collection/dataStores/{{DRIVE_MCP_STORE}}"
    specs = a.setdefault("dataStoreSpecs", {"specs": []})["specs"]
    if not any(s.get("dataStore") == store for s in specs):
        specs.append({"dataStore": store})
    sels = a.setdefault("connectorToolSelections", [])
    for s in sels:
        if s["dataConnector"]["name"] == "collections/{{DRIVE_MCP}}/dataConnector":
            s["mutateEnabled"] = True
            return
    sels.append({"dataConnector": {"name": "collections/{{DRIVE_MCP}}/dataConnector", "dataSource": "custom_mcp"},
                 "enabled": True, "searchToolEnabled": True, "mutateEnabled": True})


def port_text(s, lang):
    s = re.sub(r"\bsend_email\b", "send_message", s)
    s = re.sub(r"\bread_file_text\b", "read_file_content", s)
    s = re.sub(r"\bcreate_file_if_absent\b", TXT["absent"][lang], s)
    s = re.sub(r"send_message, or send_message", "send_message", s)
    s = re.sub(r"read_file_content, read_file_content", "read_file_content", s)
    return s


def port(path):
    t = json.loads(path.read_text())
    lang, before = t["lang"], json.dumps(t, ensure_ascii=False)
    for n in nodes(t["definition"]["agentFlow"]):
        a = n.get("agentNode")
        if not a:
            continue
        ins = port_text(a["instruction"], lang)
        if n["id"] == "insert_chart" and "insert_sheets_chart" in ins:
            ins = TXT["chart"][lang] + TAIL[lang]
        if "create_presentation_from_outline" in ins and "update_file" not in ins:
            m = re.search(r"parentId\s*\$\{([^}]+)\}", ins)
            folder = "${" + m.group(1) + "}" if m else TXT["folder"][lang]
            ins = re.sub(r",?\s*parentId\s*\$\{[^}]+\}", "", ins)
            ins += TXT["move"][lang].format(folder=folder)
            ins = re.sub(r"(Slides MCP: create_presentation_from_outline)(?!, )", r"\1 | Drive MCP: update_file", ins, count=1)
            drive_rw(a)
        a["instruction"] = ins
    for k in ("description",):
        t[k] = port_text(t[k], lang)
    after = json.dumps(t, ensure_ascii=False)
    if after != before:
        path.write_text(json.dumps(t, ensure_ascii=False, indent=1))
    left = [w for w in ("send_email", "read_file_text", "create_file_if_absent", "insert_sheets_chart") if re.search(rf"\b{w}\b", after)]
    print(f"{path.relative_to(ROOT)}: {'ported' if after != before else 'unchanged'}{'  LEFT: ' + str(left) if left else ''}")


if __name__ == "__main__":
    for p in sorted(ROOT.glob("agents/*/*/*.json")):
        if not p.name.endswith(".review.json"):
            port(p)
    for p in sorted(ROOT.glob("tests/cases/*.json")):
        s = p.read_text()
        s2 = s.replace('"send_email"', '"send_(email|message)"').replace("insert_sheets_chart", "append_to_doc")
        if s2 != s:
            p.write_text(s2)
