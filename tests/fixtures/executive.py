#!/usr/bin/env python3
"""Fixtures for the executive agents (EXE-A, EXE-B, EXE-C), in Navya's Drive, as Navya (gcloud token, full Drive scope).

  python3 tests/fixtures/executive.py setup                 top folder + every agent folder in its base state (idempotent)
  python3 tests/fixtures/executive.py reset a th|en [full|missing]   EXE-A: move run outputs to Archive, write Setup/Bank list
  python3 tests/fixtures/executive.py reset b th|en         EXE-B: outputs to Archive, Agent setup + internal docs rewritten
  python3 tests/fixtures/executive.py reset c th|en         EXE-C: outputs to Archive, Setup, tracker and minutes rewritten
  python3 tests/fixtures/executive.py show                  print the folder tree

The agent folders are the ones pinned in configs/yash-test.json (agents.EXE-x.vars_en / vars_th). `setup` moves them
(IDs unchanged) under ONE top folder "MDES WS4 yash tests – executive" in My Drive; their original parent was
"Excutive Agent" (1Bi6f6IjQ8YqHmpRfwOs65V1OUwyjTlEh). Run outputs are never deleted: `reset` moves them to the top
folder's "Archive" subfolder, renamed with a time stamp. Every address is navya.agarwal+<role>@devxlabs.ai.
No file name or text carries a test marker (agents refuse to copy such markers into outputs)."""
import datetime, io, json, re, subprocess, sys, urllib.error, urllib.parse, urllib.request, zipfile

USER, QUOTA = "navya.agarwal@devxlabs.ai", "yash-test-495112"
TOP_NAME = "MDES WS4 yash tests – executive"
OLD_PARENT = "1Bi6f6IjQ8YqHmpRfwOs65V1OUwyjTlEh"
FOLDERS = {  # configs/yash-test.json
    ("a", "en"): "1ukwfXVW_YTMd2dEqU6TwuEdG3MrpNsM3", ("a", "th"): "1lTs-lBJ0PeGYMCyHzZ-cRrv4sttdzJg2",
    ("b", "en"): "1MLOROaoMm3GdV6tpupJFBlCqcqqQJxSB", ("b", "th"): "1EDpprFiz3Gc6UD_kgTKSh7SYchY-Ei09",
    ("c", "en"): "1o_dhsjLJCyez0ob9OCbxnRLHvZUI0Dz1", ("c", "th"): "1y0YqDUHgYBBuqZua5PG_OdPZWIeJpLxe",
}
# EXE-A: the two cycle folders that already existed (13 Oct); kept by ID, renamed to Q1 (prior) and Q2 (current).
A_PRIOR = {"en": "1BrGvUJeGobjw0Hphn3H68NRFhqwDH2To", "th": "1nTcYQvEsBH6L2TeL4STVcN9eh8pY33pI"}
A_CUR = {"en": "1l3PPqmNro0fqH6vETlW2h0xkUqCjJoeP", "th": "1-2KQOBN7d6FaNDToYaj7-6-xyXK656bz"}
# The cycle names differ per language because the two builds share one mailbox and read state from sent subjects;
# "Peer Benchmark Q2-2569" is avoided: a "Q2-2569 - board pack" email was already sent on 9 Oct (earlier testing).
A_NAMES = {"en": ("Peer Benchmark Q1-2026", "Peer Benchmark Q2-2026"), "th": ("Peer Benchmark ไตรมาส 1-2569", "Peer Benchmark ไตรมาส 2-2569")}
B_PROJECT = {"en": "1XDIyWvMowfCcxHLXgGnKiSI8GlKxXrZJ", "th": "1V56XC7sj7F-zEyWAlMg2zdayu8gSbImg"}
B_PROJECT_NAME = {"en": "EV Charging Decision", "th": "ธุรกิจสถานีชาร์จรถยนต์ไฟฟ้า"}
C_EXCOM = {"en": "1Llq8a2lfiwYLuEc7LDPvLS5jicZT9igS", "th": "1aqQZC-bXFhWZWxLMERNpQsAbiVN1sjUU"}

_tok = None


def tok():
    global _tok
    _tok = _tok or subprocess.check_output(["gcloud", "auth", "print-access-token", USER], text=True).strip()
    return _tok


def http(url, method="GET", body=None, ctype="application/json", raw=False):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok()}", "X-Goog-User-Project": QUOTA, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            b = r.read()
            return b if raw else json.loads(b or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} {method} {url[:140]}: {e.read().decode()[:600]}")


def drive(path, params=None, method="GET", body=None):
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    return http(f"https://www.googleapis.com/drive/v3/{path}{q}", method, body)


def ls(fid):
    return drive("files", {"q": f"'{fid}' in parents and trashed=false", "pageSize": 200,
                           "fields": "files(id,name,mimeType,modifiedTime)"})["files"]


def child(parent, name, mime=None):
    for f in ls(parent):
        if f["name"] == name and (not mime or f["mimeType"].endswith(mime)):
            return f
    return None


def folder(parent, name):
    f = child(parent, name, "folder")
    return f["id"] if f else drive("files", method="POST", body={"name": name, "parents": [parent],
                                                                  "mimeType": "application/vnd.google-apps.folder"})["id"]


KIND = {"doc": ("application/vnd.google-apps.document", "text/plain"), "sheet": ("application/vnd.google-apps.spreadsheet", "text/csv")}


def put(parent, name, kind, text):
    """Create or overwrite (same file ID) a Google Doc from plain text or a Google Sheet from CSV."""
    f = child(parent, name, KIND[kind][0].split(".")[-1])
    if f:
        http(f"https://www.googleapis.com/upload/drive/v3/files/{f['id']}?uploadType=media", "PATCH", text.encode(), KIND[kind][1])
        return f["id"]
    b = "BOUNDARYexe7f3a"
    meta = {"name": name, "parents": [parent], "mimeType": KIND[kind][0]}
    body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n--{b}\r\n"
            f"Content-Type: {KIND[kind][1]}; charset=UTF-8\r\n\r\n").encode() + text.encode() + f"\r\n--{b}--".encode()
    return http("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id", "POST", body,
                f"multipart/related; boundary={b}")["id"]


def top():
    q = f"name = '{TOP_NAME}' and 'root' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
    hits = drive("files", {"q": q, "fields": "files(id)"})["files"]
    tid = hits[0]["id"] if hits else drive("files", method="POST", body={"name": TOP_NAME, "parents": ["root"],
                                                                          "mimeType": "application/vnd.google-apps.folder"})["id"]
    return tid, folder(tid, "Archive")


def archive(fid, name):
    _, arch = top()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    meta = drive(f"files/{fid}", {"fields": "parents"})
    drive(f"files/{fid}", {"addParents": arch, "removeParents": ",".join(meta["parents"])}, "PATCH",
          {"name": f"{stamp} {name}"})
    print("  archived:", name)


def archive_except(parent, keep):
    for f in ls(parent):
        if f["name"] not in keep:
            archive(f["id"], f["name"])


def setup():
    tid, arch = top()
    for (agent, lang), fid in FOLDERS.items():
        meta = drive(f"files/{fid}", {"fields": "id,name,parents"})
        if tid not in meta["parents"]:
            drive(f"files/{fid}", {"addParents": tid, "removeParents": ",".join(meta["parents"])}, "PATCH", {})
            print("moved", meta["name"], "into", TOP_NAME)
    print("top folder", f"https://drive.google.com/drive/folders/{tid}", "archive", arch)
    for lang in ("th", "en"):
        reset_a(lang, "full")
        reset_b(lang)
        reset_c(lang)


# ---------------------------------------------------------------- EXE-A
A_PRIOR_VALUES = {"KBANK": (2.79, 3.40, 39.30, 1.10), "SCB": (3.00, 3.65, 41.00, 0.90)}
A_EMAILS = {"head": "navya.agarwal+head@devxlabs.ai", "analyst": "navya.agarwal+analyst@devxlabs.ai",
            "secretary": "navya.agarwal+secretary@devxlabs.ai"}


def a_setup_text(lang, cycle, board, qend, bank_list, defs):
    if lang == "th":
        return (f"{cycle} - การตั้งค่า (Setup)\n"
                f"วันประชุมคณะกรรมการ: {board}\nวันสิ้นไตรมาส: {qend}\n"
                f"อีเมลหัวหน้าฝ่ายกลยุทธ์ (คุณวิชัย): {A_EMAILS['head']}\n"
                f"อีเมลนักวิเคราะห์ (คุณพลอย): {A_EMAILS['analyst']}\n"
                f"อีเมลเลขานุการบริษัท (คุณนิภา): {A_EMAILS['secretary']}\n"
                f"รายชื่อธนาคาร (Bank list): https://docs.google.com/spreadsheets/d/{bank_list}/edit\n"
                f"คำนิยามตัวชี้วัด (Metric definitions): https://docs.google.com/document/d/{defs}/edit\n")
    return (f"{cycle} - Setup\nBoard meeting date: {board}\nQuarter-end date: {qend}\n"
            f"Head of Strategy email (Khun Wichai): {A_EMAILS['head']}\n"
            f"Analyst emails (Khun Ploy): {A_EMAILS['analyst']}\n"
            f"Company Secretary email (Khun Nipa): {A_EMAILS['secretary']}\n"
            f"Bank list: https://docs.google.com/spreadsheets/d/{bank_list}/edit\n"
            f"Metric definitions: https://docs.google.com/document/d/{defs}/edit\n")


def a_prior_report(lang, cycle):
    k, s = A_PRIOR_VALUES["KBANK"], A_PRIOR_VALUES["SCB"]
    if lang == "th":
        return f"""รายงานเปรียบเทียบผลการดำเนินงานกลุ่มธนาคาร - ไตรมาส 1/2569
วันประชุมคณะกรรมการ: 15 กรกฎาคม 2569

สิ่งที่เปลี่ยนแปลงจากไตรมาสก่อน
- KBANK: NIM {k[0]:.2f}% (-0.03), NPL {k[1]:.2f}% (+0.10), ค่าใช้จ่ายต่อรายได้ {k[2]:.2f}% (-0.80), สินเชื่อเติบโตตั้งแต่ต้นปี {k[3]:.2f}%
- SCB: NIM {s[0]:.2f}% (-0.02), NPL {s[1]:.2f}% (+0.05), ค่าใช้จ่ายต่อรายได้ {s[2]:.2f}% (+0.80), สินเชื่อเติบโตตั้งแต่ต้นปี {s[3]:.2f}%

บทสรุปผู้บริหาร
ธนาคารขนาดใหญ่สองแห่ง (KBANK และ SCB) มีอัตรากำไรสุทธิลดลงเล็กน้อย คุณภาพสินทรัพย์อ่อนตัวลง และสินเชื่อเริ่มฟื้นตัวในไตรมาสแรกของปี KBANK มีประสิทธิภาพด้านต้นทุนดีกว่า ขณะที่ SCB มี NIM สูงกว่า

การจัดอันดับ (อันดับ 1 ดีที่สุด)
ธนาคาร | กลุ่มขนาด | NIM | NPL | ค่าใช้จ่ายต่อรายได้ | สินเชื่อเติบโต
KBANK | ใหญ่ | {k[0]:.2f}% (2) | {k[1]:.2f}% (1) | {k[2]:.2f}% (1) | {k[3]:.2f}% (1)
SCB | ใหญ่ | {s[0]:.2f}% (1) | {s[1]:.2f}% (2) | {s[2]:.2f}% (2) | {s[3]:.2f}% (2)

ความเคลื่อนไหวที่สำคัญ
- SCB ค่าใช้จ่ายต่อรายได้เพิ่มขึ้น 0.80 จุด จากการลงทุนด้านเทคโนโลยี
- KBANK ค่าใช้จ่ายต่อรายได้ลดลง 0.80 จุด

ประเด็นเชิงกลยุทธ์จากคำอธิบายและการวิเคราะห์ของฝ่ายจัดการ
- สินเชื่อดิจิทัล: ทั้งสองธนาคารขยายการปล่อยสินเชื่อผ่านช่องทางดิจิทัล
- ธนาคารไร้สาขา (virtual bank): อยู่ระหว่างศึกษา ยังไม่มีข้อผูกพัน
- แนวโน้มความเสี่ยงด้านเครดิต: ตั้งสำรองอย่างระมัดระวัง
- ESG: สินเชื่อที่เชื่อมโยงกับความยั่งยืนเพิ่มขึ้น

ประเด็นเพื่อพิจารณา
- แนวโน้ม NPL มีผลต่อระดับความเสี่ยงที่ยอมรับได้ของเราอย่างไร

ภาคผนวก: แหล่งที่มา หมายเหตุ และการแก้ไขโดยนักวิเคราะห์
- ตัวเลขทั้งหมดมาจากงบการเงินรวมและหมายเหตุประกอบงบการเงินไตรมาส 1/2569 ของแต่ละธนาคาร
- nim: ตัวแทน (proxy) ทุกแถว
"""
    return f"""Peer Benchmark Report - Q1/2026
Board meeting date: 15 July 2026

What changed since last quarter
- KBANK: NIM {k[0]:.2f}% (-0.03 pts), NPL {k[1]:.2f}% (+0.10 pts), cost-to-income {k[2]:.2f}% (-0.80 pts), loan growth YTD {k[3]:.2f}%.
- SCB: NIM {s[0]:.2f}% (-0.02 pts), NPL {s[1]:.2f}% (+0.05 pts), cost-to-income {s[2]:.2f}% (+0.80 pts), loan growth YTD {s[3]:.2f}%.

Executive summary
Both Large banks (KBANK and SCB) saw slight margin compression, softer asset quality and an early recovery in lending in the first quarter. KBANK leads on cost efficiency; SCB leads on NIM.

Rankings (1 = best)
Bank | Size group | NIM | NPL | Cost-to-income | Loan growth YTD
KBANK | Large | {k[0]:.2f}% (2) | {k[1]:.2f}% (1) | {k[2]:.2f}% (1) | {k[3]:.2f}% (1)
SCB | Large | {s[0]:.2f}% (1) | {s[1]:.2f}% (2) | {s[2]:.2f}% (2) | {s[3]:.2f}% (2)

Notable moves
- SCB cost-to-income rose 0.80 pts on technology investment.
- KBANK cost-to-income improved 0.80 pts.

Themes from management discussion
- Digital lending: both banks are growing digital origination.
- Virtual bank: under evaluation, no commitment.
- Credit risk outlook: cautious provisioning.
- ESG: sustainability-linked lending is growing.

For discussion
- What the NPL trend means for our risk appetite.

Appendix: sources, flags and analyst overrides
- All numbers from each bank's Q1/2026 consolidated statements and notes.
- nim: proxy on every row.
"""


def a_prior_deck(lang):
    k, s = A_PRIOR_VALUES["KBANK"], A_PRIOR_VALUES["SCB"]
    th = lang == "th"
    q = "ไตรมาส 1/2569" if th else "Q1/2026"
    rows = lambda i, ck, cs: [["ธนาคาร" if th else "Bank", "ค่า (%)" if th else "Value (%)", "อันดับ" if th else "Rank",
                               "เปลี่ยนแปลงจากไตรมาสก่อน" if th else "Change vs prior quarter"],
                              ["KBANK", f"{k[i]:.2f}", "2" if i == 0 else "1", ck], ["SCB", f"{s[i]:.2f}", "1" if i == 0 else "2", cs]]
    return {
        "p1": [f"Peer Benchmark {q}", "คณะกรรมการบริษัท - หัวหน้าฝ่ายกลยุทธ์" if th else "Board of Directors - Head of Strategy"],
        "p2": ["สิ่งที่เปลี่ยนแปลงจากไตรมาสก่อน" if th else "What changed since last quarter",
               f"KBANK: NIM {k[0]:.2f}%, NPL {k[1]:.2f}%, {'ค่าใช้จ่ายต่อรายได้' if th else 'cost-to-income'} {k[2]:.2f}%\n"
               f"SCB: NIM {s[0]:.2f}%, NPL {s[1]:.2f}%, {'ค่าใช้จ่ายต่อรายได้' if th else 'cost-to-income'} {s[2]:.2f}%\n"
               + ("เทียบกับไตรมาส 4/2568" if th else "Compared with Q4/2025")],
        "p3": ["บทสรุปผู้บริหาร" if th else "Executive summary",
               ("KBANK นำด้านค่าใช้จ่ายต่อรายได้และการเติบโตของสินเชื่อ\nSCB นำด้าน NIM\nNPL อยู่ระหว่าง 3.40% ถึง 3.65%" if th else
                "KBANK leads cost-to-income and loan growth\nSCB leads NIM\nNPL ratios between 3.40% and 3.65%")],
        "p4": ["NIM: อันดับ" if th else "NIM: ranking", rows(0, "-0.03", "-0.02")],
        "p5": ["NPL: อันดับ" if th else "NPL ratio: ranking", rows(1, "+0.10", "+0.05")],
        "p6": ["ค่าใช้จ่ายต่อรายได้: อันดับ" if th else "Cost-to-income: ranking", rows(2, "-0.80", "+0.80")],
        "p7": ["สินเชื่อเติบโตตั้งแต่ต้นปี: อันดับ" if th else "Loan growth (YTD): ranking", rows(3, "n/a", "n/a")],
        "p8": ["ความเคลื่อนไหวที่สำคัญ" if th else "Notable moves",
               ("ค่าใช้จ่ายต่อรายได้ของ SCB เพิ่มขึ้น 0.80 จุด และของ KBANK ลดลง 0.80 จุด" if th else
                "SCB's cost-to-income rose 0.80 pts and KBANK's improved 0.80 pts.")],
        "p9": ["ประเด็นจากคำอธิบายของฝ่ายจัดการ" if th else "Themes from management discussion",
               ("สินเชื่อดิจิทัลเติบโต\nธนาคารไร้สาขาอยู่ระหว่างศึกษา\nความเสี่ยงด้านเครดิต: ตั้งสำรองอย่างระมัดระวัง\nESG: สินเชื่อเพื่อความยั่งยืน" if th else
                "Digital lending growth\nVirtual bank plans under evaluation\nCredit risk: cautious provisioning\nESG: sustainability-linked lending")],
        "p10": ["ประเด็นเพื่อพิจารณา" if th else "For discussion",
                ("แนวโน้ม NPL กับระดับความเสี่ยงที่ยอมรับได้" if th else "What the NPL trend means for our risk appetite")],
    }


def slides_set(pid, content):
    """Overwrite every text box and table cell of the prior deck (same layout, new text). Idempotent."""
    p = http(f"https://slides.googleapis.com/v1/presentations/{pid}")
    reqs = []
    for sl in p["slides"]:
        want = content.get(sl["objectId"])
        if not want:
            continue
        shapes = [e for e in sl.get("pageElements", []) if "shape" in e and e["shape"].get("text")]
        tables = [e for e in sl.get("pageElements", []) if "table" in e]
        for e, txt in zip(shapes, [w for w in want if isinstance(w, str)]):
            reqs += [{"deleteText": {"objectId": e["objectId"], "textRange": {"type": "ALL"}}},
                     {"insertText": {"objectId": e["objectId"], "text": txt, "insertionIndex": 0}}]
        grid = [w for w in want if isinstance(w, list)]
        for e, g in zip(tables, grid):
            for r, row in enumerate(g):
                for c, val in enumerate(row):
                    cell = e["table"]["tableRows"][r]["tableCells"][c]
                    loc = {"rowIndex": r, "columnIndex": c}
                    if cell.get("text", {}).get("textElements"):
                        reqs.append({"deleteText": {"objectId": e["objectId"], "cellLocation": loc, "textRange": {"type": "ALL"}}})
                    reqs.append({"insertText": {"objectId": e["objectId"], "cellLocation": loc, "text": val, "insertionIndex": 0}})
    http(f"https://slides.googleapis.com/v1/presentations/{pid}:batchUpdate", "POST", {"requests": reqs})


def fix_docx(fid):
    """Remove the 'Sample document for testing' line from an uploaded .docx (same file ID)."""
    b = http(f"https://www.googleapis.com/drive/v3/files/{fid}?alt=media", raw=True)
    zin = zipfile.ZipFile(io.BytesIO(b))
    xml = zin.read("word/document.xml").decode()
    new = re.sub(r"<w:p\b(?:(?!<w:p\b).)*?Sample document for testing.*?</w:p>", "", xml, flags=re.S)
    if new == xml:
        return
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in zin.namelist():
            z.writestr(n, new if n == "word/document.xml" else zin.read(n))
    http(f"https://www.googleapis.com/upload/drive/v3/files/{fid}?uploadType=media", "PATCH", out.getvalue(),
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    print("  cleaned", fid)


A_OUT = {"en": {k: k for k in ("Comparison table", "Board report", "Board deck", "Work note")},
         "th": {"Comparison table": "ตารางเปรียบเทียบ", "Board report": "รายงานต่อคณะกรรมการ",
                "Board deck": "สไลด์นำเสนอคณะกรรมการ", "Work note": "บันทึกการทำงาน"}}
A_DEFS_TH = """คำนิยามตัวชี้วัด
การเทียบเคียงผลการดำเนินงานกลุ่มธนาคาร: เอเจนต์ปฏิบัติตามเอกสารนี้
หลักเกณฑ์ทั่วไป
* ใช้งบการเงินรวมเสมอ หากมีเฉพาะงบเฉพาะธนาคาร ให้ใช้และติดหมายเหตุ "ขอบเขต: เฉพาะธนาคาร"
* หน่วย: งบการเงินแสดงเป็นพันบาท รายงานอัตราส่วนเป็นร้อยละ ทศนิยม 2 ตำแหน่ง ห้ามใช้หน่วยปนกัน
* รายการรายได้และค่าใช้จ่าย: ใช้ตัวเลขงวดสามเดือน (ไตรมาส) รายการในงบแสดงฐานะการเงิน: ณ วันสิ้นไตรมาส เทียบกับ ณ วันสิ้นปีก่อน (31 ธันวาคม)
* ตัวเลขทุกตัวต้องระบุแหล่งที่มา: ชื่อไฟล์ พร้อมชื่อชีตและชื่อรายการ (สเปรดชีต) หรือเลขหมายเหตุ / หัวข้อ (เอกสาร) ระบุเลขหน้าเฉพาะไฟล์ PDF
* ห้ามคาดเดา หากหารายการใดไม่พบ ให้ค่าเป็น null และระบุเหตุผลในหมายเหตุ
* หากธนาคารใดใช้นิยามต่างจากเอกสารนี้: ปรับให้เทียบกันได้หากทำได้และระบุวิธีปรับ มิฉะนั้นติดหมายเหตุ "เทียบกันโดยตรงไม่ได้" พร้อมเหตุผล
รายการข้อมูลดิบที่ต้องดึง (ต่อธนาคาร จากไฟล์งบการเงินและไฟล์หมายเหตุประกอบงบการเงิน)
1. total_assets - สินทรัพย์รวม ณ วันสิ้นไตรมาส
2. total_assets_prior_ye - สินทรัพย์รวม ณ วันสิ้นปีก่อน
3. net_loans - เงินให้สินเชื่อแก่ลูกหนี้และดอกเบี้ยค้างรับสุทธิ ณ วันสิ้นไตรมาส
4. net_loans_prior_ye - รายการเดียวกัน ณ วันสิ้นปีก่อน
5. net_interest_income_q - รายได้ดอกเบี้ยสุทธิ งวดสามเดือน
6. total_operating_income_q - รายได้จากการดำเนินงานรวม งวดสามเดือน
7. operating_expenses_q - ค่าใช้จ่ายจากการดำเนินงานอื่น ๆ รวม งวดสามเดือน (ไม่รวมผลขาดทุนด้านเครดิตที่คาดว่าจะเกิดขึ้น)
8. stage3_loans - เงินให้สินเชื่อที่มีการด้อยค่าด้านเครดิต (ชั้นที่ 3) ยอดก่อนหักค่าเผื่อ จากหมายเหตุการจัดชั้นสินเชื่อ
9. gross_loans - เงินให้สินเชื่อแก่ลูกหนี้ก่อนหักค่าเผื่อ จากหมายเหตุเดียวกัน
ตัวชี้วัด (คำนวณจากข้อมูลดิบ แสดงข้อมูลนำเข้าและวิธีคำนวณ)
* nim_proxy = (net_interest_income_q x 4) / ค่าเฉลี่ยของ (total_assets, total_assets_prior_ye) x 100 เป็นค่าตัวแทน (ใช้สินทรัพย์รวมเฉลี่ย ไม่ใช่สินทรัพย์ที่ก่อให้เกิดรายได้) ติดหมายเหตุ "nim: ตัวแทน (proxy)" ทุกครั้ง
* npl = stage3_loans / gross_loans x 100 หากไม่มีรายการใดรายการหนึ่ง: null และติดหมายเหตุ "npl: ไม่พบในหมายเหตุประกอบงบการเงิน"
* cost_to_income = operating_expenses_q / total_operating_income_q x 100
* loan_growth_ytd = (net_loans / net_loans_prior_ye - 1) x 100
หมายเหตุที่ต้องติด
* ขอบเขตที่ไม่ใช่งบการเงินรวม ค่าตัวแทนทุกตัว รายการที่หาไม่พบ แหล่งข้อมูลสองแหล่งขัดแย้งกัน หน่วยไม่ชัดเจน การอ่านค่าที่ไม่มั่นใจ
ประเด็นเชิงคุณภาพ (เฉพาะเมื่อมีไฟล์ MD&A หรือคำอธิบายของฝ่ายจัดการในโฟลเดอร์ธนาคาร)
* กลยุทธ์ดิจิทัล / แผนธนาคารไร้สาขา แนวโน้มความเสี่ยงด้านเครดิต ESG ธนาคารละหนึ่งบรรทัดสั้น ๆ พร้อมแหล่งที่มา หากไม่มีไฟล์คำอธิบาย ให้เขียนว่า "ไม่มีเอกสาร MD&A"
การจัดอันดับ
* จัดอันดับแต่ละตัวชี้วัดในกลุ่มธนาคารทั้งหมด และภายในกลุ่มขนาดเดียวกัน (จาก Bank list) ค่าสูงดีกว่าสำหรับ nim_proxy และ loan_growth_ytd ค่าต่ำดีกว่าสำหรับ npl และ cost_to_income
ความเคลื่อนไหวที่สำคัญ
* เปรียบเทียบกับตารางของไตรมาสก่อน เน้นการเปลี่ยนแปลงเกิน 0.25 จุดร้อยละ หรือตัวชี้วัดที่เปลี่ยนในทิศทางเดียวกันสามไตรมาสติดต่อกันหากมีตารางย้อนหลังสามไตรมาส
"""


def reset_a(lang, mode="full"):
    root = FOLDERS[("a", lang)]
    prior, cur = A_PRIOR[lang], A_CUR[lang]
    pname, cname = A_NAMES[lang]
    drive(f"files/{prior}", method="PATCH", body={"name": pname})
    drive(f"files/{cur}", method="PATCH", body={"name": cname})
    for f in ls(root):
        if f["id"] not in (prior, cur):
            archive(f["id"], f["name"])
    # prior cycle (Q1): Setup, table, report, deck (its layout is the template for the new deck).
    # Output names follow the build's language (the TH template looks for Thai names, 14 Oct fix).
    out = A_OUT[lang]
    for en_name, th_name in A_OUT["th"].items():  # rename 13 Oct English-named files in the TH folder
        f = child(prior, en_name) if lang == "th" else None
        if f and not child(prior, th_name):
            drive(f"files/{f['id']}", method="PATCH", body={"name": th_name})
    put(prior, "Setup", "doc", a_setup_text(lang, pname, "2026-07-15", "2026-03-31", "", "").split("\n" + ("รายชื่อ" if lang == "th" else "Bank list"))[0] + "\n")
    flag = "nim: ตัวแทน (proxy)" if lang == "th" else "nim: proxy"
    rows = "\n".join(f"{b},{v[0]:.2f},{v[1]:.2f},{v[2]:.2f},{v[3]:.2f},{flag}," for b, v in A_PRIOR_VALUES.items())
    put(prior, out["Comparison table"], "sheet", "bank,nim_proxy,npl,cost_to_income,loan_growth_ytd,flags,basis\n" + rows + "\n")
    put(prior, out["Board report"], "doc", a_prior_report(lang, pname))
    put(prior, out["Work note"], "doc", ("บันทึกการทำงาน " + pname + "\n- นักวิเคราะห์ตรวจสอบตัวเลขแล้ว ไม่มีการแก้ไข\n- หัวหน้าฝ่ายกลยุทธ์อนุมัติแล้ว\n")
        if lang == "th" else ("Work note " + pname + "\n- Analysts checked the numbers; no corrections.\n- Head of Strategy approved.\n"))
    deck = child(prior, out["Board deck"], "presentation")
    slides_set(deck["id"], a_prior_deck(lang))
    # current cycle (Q2): keep the bank folders, Bank list, Metric definitions; archive outputs
    keep = {"Bank list", "Metric definitions", "Setup", "KBANK", "SCB"} | ({"BBL"} if mode == "missing" else set())
    archive_except(cur, keep)
    sz = "ใหญ่" if lang == "th" else "Large"
    banks = f"Bank,Size group,Folder\nKBANK,{sz},KBANK\nSCB,{sz},SCB\n" + (f"BBL,{sz},BBL\n" if mode == "missing" else "")
    bl = put(cur, "Bank list", "sheet", banks)
    defs = put(cur, "Metric definitions", "doc", A_DEFS_TH) if lang == "th" else child(cur, "Metric definitions", "document")["id"]
    if mode == "missing":
        bbl = folder(cur, "BBL")
        for f in ls(bbl):
            archive(f["id"], "BBL " + f["name"])
    board = (datetime.date.today() + datetime.timedelta(days=5)).isoformat() if mode == "missing" else "2026-10-28"
    put(cur, "Setup", "doc", a_setup_text(lang, cname, board, "2026-06-30", bl, defs))
    for bank in ("KBANK", "SCB"):
        bf = child(cur, bank, "folder")["id"]
        for f in ls(bf):
            if f["name"].upper().startswith("MDA"):
                fix_docx(f["id"])
    print(f"EXE-A {lang} reset ({mode}): cycle {cname}, board {board}")


# ---------------------------------------------------------------- EXE-B
B_DOCS = {
    "en": {
        "Feasibility study - EV charging (April 2026)": """EV CHARGING STATION BUSINESS - FEASIBILITY STUDY
Prepared by: Strategy team, April 2026 | Company: mid-sized energy services company, Eastern Economic Corridor (EEC)

1. Market (as of April 2026)
- EV registrations in EEC provinces (Chonburi, Rayong, Chachoengsao): about 4,200 per month, growing about 3% month on month.
- Public chargers in EEC: about 900 connectors, mostly DC fast chargers along highways.

2. Rules (as of April 2026)
- Charging stations need an electricity business licence exemption below a stated capacity; tariff rules for charging stations are under review by the regulator.

3. Competitors
- PTT EV Station PluZ, EA Anywhere, PEA VOLTA, MEA EV. Combined network growth about 60 stations per quarter in EEC.

4. Returns (indicative)
- Industrial estates: payback 5-6 years. Highways: 6-8 years. Condominiums: 7-9 years.

5. Main risks
- Tariff structure change; slower EV adoption; competitor price cuts; landowner lease terms.

6. Recommendation at the time
- Wait and prepare; revisit in six months.
""",
        "Financial model summary - EV charging": """EV CHARGING - FINANCIAL MODEL SUMMARY (Strategy team, April 2026)
Capex per DC fast charger site (4 connectors): THB 8.5 million
Opex per site per year: THB 1.1 million
Base case utilisation: 14% (year 1) rising to 22% (year 5)
Base case tariff to customers: THB 7.5 per kWh; electricity cost THB 4.2 per kWh
Base case payback: 6.4 years | IRR: 11%
Sensitivity: utilisation 10% -> payback 9.8 years; tariff -1 THB -> payback 8.9 years
""",
        "Board minutes extract - 26 March 2026": """BOARD MEETING MINUTES (extract) - 26 March 2026
Item 5: EV charging business (for decision).
The CEO presented the feasibility study. The board asked management to keep the question under review and to bring a decision brief when evidence on tariff rules and competitor expansion is clearer. The board asked to see which developments would change the recommendation.
Resolution: Management to prepare a decision brief for the next suitable board meeting.
""",
    },
    "th": {
        "การศึกษาความเป็นไปได้ - สถานีชาร์จรถยนต์ไฟฟ้า (เมษายน 2569)": """การศึกษาความเป็นไปได้ของธุรกิจสถานีชาร์จรถยนต์ไฟฟ้า
จัดทำโดย: ฝ่ายกลยุทธ์ เมษายน 2569 | บริษัท: บริษัทบริการพลังงานขนาดกลาง ในเขตพัฒนาพิเศษภาคตะวันออก (EEC)

1. ตลาด (ณ เมษายน 2569)
- การจดทะเบียนรถยนต์ไฟฟ้าใหม่ในจังหวัด EEC (ชลบุรี ระยอง ฉะเชิงเทรา): ประมาณ 4,200 คันต่อเดือน เติบโตประมาณร้อยละ 3 ต่อเดือน
- หัวชาร์จสาธารณะใน EEC: ประมาณ 900 หัวชาร์จ ส่วนใหญ่เป็นเครื่องชาร์จเร็ว DC ตามทางหลวง

2. กฎเกณฑ์ (ณ เมษายน 2569)
- สถานีชาร์จได้รับยกเว้นใบอนุญาตประกอบกิจการไฟฟ้าหากมีกำลังการผลิตต่ำกว่าเกณฑ์ที่กำหนด อัตราค่าไฟฟ้าสำหรับสถานีชาร์จอยู่ระหว่างการทบทวนของหน่วยงานกำกับดูแล

3. คู่แข่ง
- PTT EV Station PluZ, EA Anywhere, PEA VOLTA, MEA EV เครือข่ายรวมใน EEC เพิ่มขึ้นประมาณ 60 สถานีต่อไตรมาส

4. ผลตอบแทน (โดยประมาณ)
- นิคมอุตสาหกรรม: คืนทุน 5-6 ปี ทางหลวง: 6-8 ปี คอนโดมิเนียม: 7-9 ปี

5. ความเสี่ยงหลัก
- การเปลี่ยนแปลงโครงสร้างอัตราค่าไฟฟ้า การใช้รถยนต์ไฟฟ้าเติบโตช้ากว่าคาด คู่แข่งลดราคา เงื่อนไขการเช่าที่ดิน

6. ข้อเสนอแนะในขณะนั้น
- รอและเตรียมความพร้อม ทบทวนอีกครั้งในหกเดือน
""",
        "สรุปแบบจำลองทางการเงิน - สถานีชาร์จรถยนต์ไฟฟ้า": """สรุปแบบจำลองทางการเงิน สถานีชาร์จรถยนต์ไฟฟ้า (ฝ่ายกลยุทธ์ เมษายน 2569)
เงินลงทุนต่อสถานีชาร์จเร็ว DC (4 หัวชาร์จ): 8.5 ล้านบาท
ค่าใช้จ่ายดำเนินงานต่อสถานีต่อปี: 1.1 ล้านบาท
อัตราการใช้งานกรณีฐาน: ร้อยละ 14 (ปีที่ 1) เพิ่มเป็นร้อยละ 22 (ปีที่ 5)
อัตราค่าบริการกรณีฐาน: 7.5 บาทต่อหน่วย ต้นทุนค่าไฟฟ้า 4.2 บาทต่อหน่วย
ระยะเวลาคืนทุนกรณีฐาน: 6.4 ปี | IRR: ร้อยละ 11
การวิเคราะห์ความอ่อนไหว: อัตราการใช้งานร้อยละ 10 -> คืนทุน 9.8 ปี; ค่าบริการลดลง 1 บาท -> คืนทุน 8.9 ปี
""",
        "สารสกัดรายงานการประชุมคณะกรรมการ - 26 มีนาคม 2569": """รายงานการประชุมคณะกรรมการบริษัท (สารสกัด) - 26 มีนาคม 2569
วาระที่ 5: ธุรกิจสถานีชาร์จรถยนต์ไฟฟ้า (เพื่อพิจารณา)
ประธานเจ้าหน้าที่บริหารนำเสนอผลการศึกษาความเป็นไปได้ คณะกรรมการขอให้ฝ่ายจัดการติดตามประเด็นนี้ต่อไป และนำเสนอบันทึกประกอบการตัดสินใจเมื่อมีข้อมูลที่ชัดเจนขึ้นเกี่ยวกับอัตราค่าไฟฟ้าและการขยายตัวของคู่แข่ง คณะกรรมการต้องการทราบว่าพัฒนาการใดจะทำให้ข้อเสนอแนะเปลี่ยนไป
มติ: ให้ฝ่ายจัดการจัดทำบันทึกประกอบการตัดสินใจเพื่อเสนอในการประชุมคณะกรรมการครั้งถัดไปที่เหมาะสม
""",
    },
}


def reset_b(lang):
    root, proj = FOLDERS[("b", lang)], B_PROJECT[lang]
    drive(f"files/{proj}", method="PATCH", body={"name": B_PROJECT_NAME[lang]})
    for f in ls(root):
        if f["id"] != proj and f["name"] != "Agent setup":
            archive(f["id"], f["name"])
    archive_except(proj, set(B_DOCS[lang]))
    for name, text in B_DOCS[lang].items():
        put(proj, name, "doc", text)
    if lang == "th":
        setup_txt = ("Decision Brief Tracker - การตั้งค่าเอเจนต์ (Agent setup)\nโฟลเดอร์โครงการที่ติดตาม (บรรทัดละหนึ่งโฟลเดอร์):\n"
                     f"https://drive.google.com/drive/folders/{proj}\nชื่อประธานเจ้าหน้าที่บริหาร: คุณสุดา\n"
                     "อีเมลประธานเจ้าหน้าที่บริหาร: navya.agarwal+ceo@devxlabs.ai\n"
                     "อีเมลผู้จัดการฝ่ายกลยุทธ์ (คุณต้น): navya.agarwal+strategy@devxlabs.ai\nภาษา: ไทย\n")
    else:
        setup_txt = ("Decision Brief Tracker - Agent setup\nProject folders to watch (one per line):\n"
                     f"https://drive.google.com/drive/folders/{proj}\nCEO name: Khun Suda\nCEO email: navya.agarwal+ceo@devxlabs.ai\n"
                     "Strategy manager email (Khun Ton): navya.agarwal+strategy@devxlabs.ai\nLanguage: English\n")
    put(root, "Agent setup", "doc", setup_txt)
    print(f"EXE-B {lang} reset: project {B_PROJECT_NAME[lang]}")


# ---------------------------------------------------------------- EXE-C
C_PEOPLE = {"cfo": "navya.agarwal+cfo@devxlabs.ai", "coo": "navya.agarwal+coo@devxlabs.ai",
            "strategy": "navya.agarwal+strategy@devxlabs.ai", "sales": "navya.agarwal+sales@devxlabs.ai"}


def c_minutes(lang, which):
    p = C_PEOPLE
    if lang == "th":
        att = (f"ผู้เข้าประชุม: คุณสุดา (ประธานเจ้าหน้าที่บริหาร), คุณอนันต์ (ผู้อำนวยการฝ่ายการเงิน, {p['cfo']}), "
               f"คุณปรีชา (ผู้อำนวยการฝ่ายปฏิบัติการ, {p['coo']}), คุณวิชัย (หัวหน้าฝ่ายกลยุทธ์, {p['strategy']}), "
               f"คุณมาลี (หัวหน้าฝ่ายขาย, {p['sales']})")
        if which == "0924":
            return ("รายงานการประชุมคณะกรรมการบริหาร (ExCom) - 24 กันยายน 2569\n" + att + "\nมติที่ประชุม:\n"
                    "1. อนุมัติกรอบงบลงทุนไตรมาส 4 จำนวน 120 ล้านบาท\n2. เลื่อนการเป็นพันธมิตรกับเจ้าของที่ดินรายหนึ่งจนกว่าการตรวจสอบทางกฎหมายจะแล้วเสร็จ\n"
                    "รายการที่ต้องดำเนินการ:\n- ผู้อำนวยการฝ่ายการเงินเวียนงบประมาณไตรมาส 4 ฉบับปรับปรุง ภายใน 2 ตุลาคม 2569\n"
                    "- หัวหน้าฝ่ายกลยุทธ์จัดทำบันทึกประกอบการตัดสินใจเรื่องสถานีชาร์จรถยนต์ไฟฟ้า ภายใน 15 ตุลาคม 2569\n")
        return ("รายงานการประชุมคณะกรรมการบริหาร (ExCom) - 12 ตุลาคม 2569\n" + att + "\nมติที่ประชุม:\n"
                "1. อนุมัติงบ 18 ล้านบาทสำหรับโครงการนำร่องสถานีชาร์จที่คลังสินค้าระยอง\n"
                "2. เลื่อนการตัดสินใจต่อสัญญาเช่าสำนักงานไปเดือนพฤศจิกายน\n"
                "รายการที่ต้องดำเนินการ:\n"
                "- ผู้อำนวยการฝ่ายการเงินส่งประมาณการกระแสเงินสดฉบับปรับปรุง ภายใน 20 ตุลาคม 2569\n"
                "- หัวหน้าฝ่ายขายนำเสนอการทบทวนยอดขายที่คาดการณ์ไตรมาส 4 ภายใน 22 ตุลาคม 2569\n"
                "- ผู้อำนวยการฝ่ายปฏิบัติการรายงานผลการตรวจความปลอดภัยของคลังสินค้า ภายใน 27 ตุลาคม 2569\n"
                "- ให้มีผู้ดูแลเรื่องงานค้างในการขึ้นทะเบียนผู้ขายรายใหม่ (ยังไม่ได้กำหนดผู้รับผิดชอบและวันที่)\n")
    att = (f"Attendees: Khun Suda (CEO), Khun Anan (CFO, {p['cfo']}), Khun Preecha (COO, {p['coo']}), "
           f"Khun Wichai (Head of Strategy, {p['strategy']}), Khun Mali (Head of Sales, {p['sales']})")
    if which == "0924":
        return ("EXECUTIVE COMMITTEE (ExCom) MEETING MINUTES - 24 September 2026\n" + att + "\nDecisions:\n"
                "1. Approved the Q4 capex envelope of THB 120 million.\n2. Deferred the partnership with a landowner until legal review completes.\n"
                "Action items:\n- CFO to circulate the revised Q4 budget by 2026-10-02.\n"
                "- Head of Strategy to prepare the EV charging decision brief by 2026-10-15.\n")
    return ("EXECUTIVE COMMITTEE (ExCom) MEETING MINUTES - 13 October 2026\n" + att + "\nDecisions:\n"
            "1. Approved THB 18 million for the Rayong depot charging pilot.\n2. Deferred the office lease renewal decision to November.\n"
            "Action items:\n- CFO to send the revised cash-flow forecast by 2026-10-20.\n"
            "- Head of Sales to present the Q4 pipeline review by 2026-10-22.\n"
            "- COO to report on the depot safety audit by 2026-10-27.\n"
            "- Someone to look into the vendor onboarding backlog (owner and date not agreed).\n")


def reset_c(lang):
    root, ex = FOLDERS[("c", lang)], C_EXCOM[lang]
    m1_name = "ExCom minutes 2026-09-24" if lang == "en" else "รายงานการประชุม ExCom 2026-09-24"
    # TH minutes are dated 12 Oct so its action IDs (and calendar invites "[2026-10-12-excom-N]") differ from EN's:
    # both builds write to Navya's one calendar, and the invite step skips an action whose ID is already there.
    m2_name = "ExCom minutes 2026-10-13" if lang == "en" else "รายงานการประชุม ExCom 2026-10-12"
    for f in ls(root):
        if f["id"] != ex and f["name"] != "Setup":
            archive(f["id"], f["name"])
    archive_except(ex, {m1_name, m2_name, "Action tracker"} - ({"รายงานการประชุม ExCom 2026-10-13"} if lang == "th" else set()))
    m1 = put(ex, m1_name, "doc", c_minutes(lang, "0924"))
    put(ex, m2_name, "doc", c_minutes(lang, "1013"))
    if lang == "th":
        a1, a2 = "ผู้อำนวยการฝ่ายการเงินเวียนงบประมาณไตรมาส 4 ฉบับปรับปรุง", "หัวหน้าฝ่ายกลยุทธ์จัดทำบันทึกประกอบการตัดสินใจเรื่องสถานีชาร์จรถยนต์ไฟฟ้า"
    else:
        a1, a2 = "CFO to circulate the revised Q4 budget", "Head of Strategy to prepare the EV charging decision brief"
    # TH tracker values are Thai, matching the TH template (14 Oct): done/open/sent/yes -> Thai words
    v = {"done": "เสร็จสิ้น", "open": "ยังไม่เสร็จ", "sent": "ส่งแล้ว", "yes": "แจ้งแล้ว"} if lang == "th" else {k: k for k in ("done", "open", "sent", "yes")}
    tracker = ("action_id,meeting,minutes_id,action,owner_email,deadline,status,stage,notified,thread_subject,notes\n"
               f"2026-09-24-excom-1,ExCom,{m1},{a1},{C_PEOPLE['cfo']},2026-10-02,{v['done']},{v['sent']},{v['yes']},,\n"
               f"2026-09-24-excom-2,ExCom,{m1},{a2},{C_PEOPLE['strategy']},2026-10-15,{v['open']},{v['sent']},{v['yes']},,\n")
    put(ex, "Action tracker", "sheet", tracker)
    if lang == "th":
        setup_txt = ("Meeting Prep & Actions - การตั้งค่า (Setup)\nชื่อประธานเจ้าหน้าที่บริหาร: คุณสุดา\n"
                     "อีเมลประธานเจ้าหน้าที่บริหาร: navya.agarwal+ceo@devxlabs.ai\nรหัสปฏิทินของประธานเจ้าหน้าที่บริหาร: navya.agarwal@devxlabs.ai\n"
                     "ผู้ช่วยผู้บริหาร (เจ้าของเอเจนต์): คุณนก navya.agarwal+assistant@devxlabs.ai\n"
                     "การประชุมที่มีความอ่อนไหว (ประธานเจ้าหน้าที่บริหารอนุมัติรายการที่ต้องดำเนินการเอง): Board\n"
                     "โฟลเดอร์การประชุม: หนึ่งโฟลเดอร์ย่อยต่อการประชุมประจำ (ExCom)\n")
    else:
        setup_txt = ("Meeting Prep & Actions - Setup\nCEO name: Khun Suda\nCEO email: navya.agarwal+ceo@devxlabs.ai\n"
                     "CEO calendar ID: navya.agarwal@devxlabs.ai\nExecutive assistant (agent owner): Khun Nok navya.agarwal+assistant@devxlabs.ai\n"
                     "Sensitive meetings (the CEO approves their action lists herself): Board\n"
                     "Meeting folders: one sub-folder per recurring meeting (ExCom)\n")
    put(root, "Setup", "doc", setup_txt)
    print(f"EXE-C {lang} reset: new minutes {m2_name}")


def show():
    tid, _ = top()
    def tree(fid, ind=""):
        for f in sorted(ls(fid), key=lambda x: x["name"]):
            print(f"{ind}{f['name']}  [{f['mimeType'].split('.')[-1]}] {f['id']}")
            if f["mimeType"].endswith("folder") and f["name"] != "Archive":
                tree(f["id"], ind + "  ")
    print(TOP_NAME, tid)
    tree(tid, "  ")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "show":
        show()
    elif a[0] == "setup":
        setup()
    elif a[0] == "reset":
        {"a": lambda: reset_a(a[2], a[3] if len(a) > 3 else "full"), "b": lambda: reset_b(a[2]), "c": lambda: reset_c(a[2])}[a[1]]()
    else:
        sys.exit(__doc__)
