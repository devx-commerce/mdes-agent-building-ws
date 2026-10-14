#!/usr/bin/env python3
"""Researcher persona fixtures (RES-A Evidence Review, RES-B Survey Analysis, RES-C Funding Calls) in Navya's Drive.

  python3 tests/fixtures/researcher.py build              create or refresh every fixture (idempotent; reuses by name)
  python3 tests/fixtures/researcher.py prep <case-id>     put the fixtures in the state a case needs (slot times, goal text)
  python3 tests/fixtures/researcher.py run <case.json>..  prep each case, then run it with tests/harness.py
  python3 tests/fixtures/researcher.py ids                print the fixture ids

All data is synthetic (numbers from mdes-agent/test-data/make_res_test_data.py, ANSWER-KEY.md) but carries no test
marker, because the agents refuse to copy such markers into outputs. Everything lives under ONE top folder
'MDES WS4 yash tests – researcher'. Ids are cached in tests/fixtures/researcher.ids.json.

Time slots (read from the templates, 14 Oct 2026):
  RES-A  acts when the Setup Doc was modified in [current hour - 1 h, current hour:00)   (07:00 run: from 18:00 yesterday)
  RES-B  acts when the newest data file or the plan was modified in [half hour - 30 min, half hour)
  RES-C  records results when the calls log was modified in [yesterday 07:00, today 07:00); weekly search only on Mondays
'prep' sets Drive modifiedTime explicitly into the slot of a run that starts right after it."""
import datetime as dt
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
IDS = pathlib.Path(__file__).with_name("researcher.ids.json")
USER, QUOTA = "navya.agarwal@devxlabs.ai", "yash-test-495112"
TOP = "MDES WS4 yash tests – researcher"
VISHAL = pathlib.Path.home() / "Desktop/codebase/mdes-work-log/mdes-agent/test-data/res"
BKK = dt.timezone(dt.timedelta(hours=7))
FOLDER = "application/vnd.google-apps.folder"
DOC, SHEET = "application/vnd.google-apps.document", "application/vnd.google-apps.spreadsheet"
_tok = None


def token():
    global _tok
    if not _tok:
        _tok = subprocess.check_output(["gcloud", "auth", "print-access-token", USER], text=True).strip()
    return _tok


def req(method, url, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token(), "X-Goog-User-Project": QUOTA, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(r, timeout=120) as f:
            b = f.read()
            return json.loads(b) if b and b[:1] in (b"{", b"[") else b.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} {method} {url[:120]}: {e.read().decode()[:600]}")


D = "https://www.googleapis.com/drive/v3/files"
U = "https://www.googleapis.com/upload/drive/v3/files"
FIELDS = "id,name,mimeType,modifiedTime,webViewLink,parents"


def find(name, parent=None, mime=None):
    q = [f"name = '{name}'", "trashed = false"] + ([f"'{parent}' in parents"] if parent else []) + ([f"mimeType = '{mime}'"] if mime else [])
    r = req("GET", D + "?" + urllib.parse.urlencode({"q": " and ".join(q), "fields": f"files({FIELDS})", "pageSize": 10}))
    return r.get("files", [])


def folder(name, parent=None):
    hit = find(name, parent, FOLDER)
    if hit:
        return hit[0]
    meta = {"name": name, "mimeType": FOLDER} | ({"parents": [parent]} if parent else {})
    return req("POST", D + "?fields=" + FIELDS, meta)


def upsert(name, parent, content, src, target=None):
    """Create or replace a file by exact name in parent. src = upload type (text/html, text/csv); target = Google type or None."""
    b = "RESFIX7f3a"
    hit = find(name, parent)
    meta = {} if hit else {"name": name, "parents": [parent]} | ({"mimeType": target} if target else {})
    body = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n--{b}\r\n"
            f"Content-Type: {src}; charset=UTF-8\r\n\r\n").encode() + content.encode() + f"\r\n--{b}--".encode()
    if hit:
        return req("PATCH", f"{U}/{hit[0]['id']}?uploadType=multipart&fields={FIELDS}", raw=body, ctype=f"multipart/related; boundary={b}")
    return req("POST", f"{U}?uploadType=multipart&fields={FIELDS}", raw=body, ctype=f"multipart/related; boundary={b}")


def set_modified(fid, when):
    return req("PATCH", f"{D}/{fid}?fields=id,name,modifiedTime", {"modifiedTime": when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")})


def rename(fid, name):
    return req("PATCH", f"{D}/{fid}?fields=id,name", {"name": name})


def html(title, blocks):
    out = [f"<h2>{title}</h2>"]
    for x in blocks:
        if isinstance(x, tuple):
            head, rows = x
            out.append("<table border='1'><tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>" +
                       "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
        else:
            out.append(f"<p>{x}</p>")
    return "<html><meta charset='utf-8'><body>" + "".join(out) + "</body></html>"


# ---------------- content ----------------
LIBRARY = {
    "01 BOI – สรุปการส่งเสริมการลงทุน EV 2568": html("สรุปการอนุมัติส่งเสริมการลงทุนอุตสาหกรรมยานยนต์ไฟฟ้า ปี 2568", [
        "แหล่งที่มา: สำนักงานคณะกรรมการส่งเสริมการลงทุน (BOI) – ข้อมูล ณ 31 ธันวาคม 2568",
        (("ตัวชี้วัด", "ค่า", "หน่วย", "หมายเหตุ"),
         [("กำลังการผลิต BEV ที่ได้รับอนุมัติ (สะสม)", "359,000", "คัน/ปี", "เป็นกำลังการผลิตตามแผน ไม่ใช่การผลิตจริง"),
          ("จำนวนโครงการ BEV ที่ได้รับอนุมัติ", "24", "โครงการ", "สะสมถึงสิ้นปี 2568"),
          ("มูลค่าเงินลงทุนที่อนุมัติ", "39,500", "ล้านบาท", "")]),
        "หมายเหตุ: กำลังการผลิตที่ได้รับอนุมัติวัดจากแผนการลงทุนของผู้ประกอบการ ซึ่งอาจยังไม่ได้เริ่มผลิตจริง"]),
    "02 คณะกรรมการนโยบาย EV – เป้าหมาย 30@30 และมาตรการ EV 3.5": html("ประกาศคณะกรรมการนโยบายยานยนต์ไฟฟ้าแห่งชาติ", [
        "เป้าหมาย 30@30: ผลิตยานยนต์ปล่อยมลพิษเป็นศูนย์ (ZEV) ร้อยละ 30 ของการผลิตยานยนต์ทั้งหมดภายในปี 2573 (ค.ศ. 2030)",
        "คิดจากฐานกำลังการผลิตรวม 2.5 ล้านคัน/ปี เท่ากับ ZEV ประมาณ 725,000 คัน/ปี ในปี 2573",
        "มาตรการ EV 3.5 (ปี 2567–2570): เงินอุดหนุนสูงสุด 100,000 บาท/คัน สำหรับ BEV แบตเตอรี่ ≥ 50 kWh "
        "ผู้รับสิทธิ์ต้องผลิตชดเชยในประเทศ อัตรา 1:2 ภายในปี 2569 และ 1:3 ภายในปี 2570"]),
    "03 กรมการขนส่งทางบก – สถิติจดทะเบียน BEV ใหม่": html("สถิติการจดทะเบียนรถยนต์ไฟฟ้า (BEV) ใหม่", [
        "แหล่งที่มา: กรมการขนส่งทางบก กลุ่มสถิติการขนส่ง",
        (("ปี", "จดทะเบียน BEV ใหม่ (คัน)"), [("2565", "9,678"), ("2566", "76,314"), ("2567", "70,137"), ("2568", "64,250")]),
        "สถานีอัดประจุไฟฟ้าที่ให้บริการ (ข้อมูลประกอบ): 3,850 สถานี ณ สิ้นปี 2568"]),
    "04 สมาคมยานยนต์ไฟฟ้าไทย – รายงานอุตสาหกรรม 2568": html("รายงานภาพรวมอุตสาหกรรมยานยนต์ไฟฟ้าไทย ปี 2568", [
        "แหล่งที่มา: สมาคมยานยนต์ไฟฟ้าไทย ฝ่ายข้อมูลอุตสาหกรรม",
        (("ตัวชี้วัด", "ค่า", "หมายเหตุ"),
         [("การผลิต BEV จริงในประเทศ ปี 2568", "41,800 คัน", "นับเฉพาะรถที่ผลิตเสร็จ"),
          ("ยอดขาย BEV ปี 2567", "66,700 คัน", "ยอดขาย ไม่ใช่ยอดจดทะเบียน"),
          ("หัวจ่ายอัดประจุสาธารณะ", "11,500 หัวจ่าย", "นับเป็นหัวจ่าย ไม่ใช่สถานี"),
          ("เงินอุดหนุนสูงสุดต่อคัน", "150,000 บาท", "อ้างอิงมาตรการ EV 3.0 เดิม")]),
        "ผู้ผลิตรายใหญ่รายหนึ่งประกาศเลื่อนการเปิดโรงงานแห่งที่สองจากปี 2569 เป็นปี 2570"]),
    "05 บทความวิชาการ – การเปลี่ยนผ่านสู่ EV ของไทย": html("การเปลี่ยนผ่านสู่ยานยนต์ไฟฟ้าของประเทศไทย: ช่องว่างระหว่างนโยบายกับตลาด", [
        "วารสารนโยบายสาธารณะและการพัฒนา ปีที่ 12 ฉบับที่ 2 (2568)",
        "ผลการศึกษาพบว่า การผลิตยานยนต์ไฟฟ้าในปี 2568 มีประมาณ 78,000 คัน (รวม BEV และ PHEV)",
        "ยอดจดทะเบียนรถยนต์ไฟฟ้าใหม่ปี 2567 อยู่ที่ประมาณ 73,000 คัน",
        "เป้าหมาย 30@30 คิดเป็นการผลิต ZEV ประมาณ 750,000 คันในปี 2573"]),
}
GOAL_TH = ("เปรียบเทียบเป้าหมายยานยนต์ไฟฟ้าของรัฐบาลไทยกับประกาศของบริษัทและรายงานที่น่าเชื่อถือ "
           "ระบุจุดที่ตัวเลขขัดแย้งกันและเหตุผล และจัดทำบทสรุปพร้อมแหล่งอ้างอิง")
GOAL_EN = ("Compare Thai government EV targets with company announcements and credible reporting. "
           "Identify where estimates conflict and why, and produce a sourced briefing.")
GOAL_TH_SHORT = "สรุปสถานการณ์สถานีอัดประจุไฟฟ้าสาธารณะในประเทศไทย ปี 2566–2568"
GOAL_EN_SHORT = "Summarise the public EV charging network in Thailand, 2023-2025."

CODEBOOK = html("คู่มือลงรหัสข้อมูล (Codebook) – แบบสอบถามความตั้งใจซื้อรถยนต์ไฟฟ้า", [
    (("คอลัมน์", "ความหมาย", "ค่าที่ถูกต้อง"),
     [("resp_id", "รหัสผู้ตอบ (ไม่มีชื่อ/เบอร์โทร)", "R0001–R1200"),
      ("region", "ภูมิภาค", "ภาคเหนือ / ภาคตะวันออกเฉียงเหนือ / ภาคกลาง / ภาคใต้ (ภาษาไทยเท่านั้น)"),
      ("gender", "เพศ", "ชาย / หญิง"), ("age_group", "กลุ่มอายุ", "1–5"),
      ("income", "รายได้ต่อเดือน (กลุ่ม)", "1–5"),
      ("q1–q12", "ข้อคำถามมาตรวัดลิเคิร์ต", "1–5 เท่านั้น"),
      ("charge_avail", "การรับรู้ความพร้อมของสถานีอัดประจุ", "1–5"),
      ("price_concern", "ความกังวลด้านราคา", "1–5"),
      ("purchase_intent", "ความตั้งใจซื้อรถยนต์ไฟฟ้าภายใน 2 ปี", "1–5")])])
PLAN_LINES = [
    "1. ตารางสรุป: ค่าร้อยละของ gender, region และค่าเฉลี่ยของ purchase_intent",
    "2. H1: การรับรู้ความพร้อมของสถานีอัดประจุ (charge_avail) มีความสัมพันธ์เชิงบวกกับความตั้งใจซื้อ (purchase_intent) – Pearson correlation",
    "3. H2: ความกังวลด้านราคา (price_concern) มีความสัมพันธ์เชิงลบกับความตั้งใจซื้อ – Pearson correlation",
    "4. H3: ความตั้งใจซื้อแตกต่างกันตามภูมิภาค – One-way ANOVA",
    "5. แผนภูมิ: ค่าเฉลี่ยความตั้งใจซื้อตามภูมิภาค (bar chart)"]
PLAN_H4 = "6. H4: ความตั้งใจซื้อแตกต่างกันตามกลุ่มรายได้ (income) – One-way ANOVA"
DATA_NAME = "แบบสอบถาม EV 2569 – n1200.csv"

PROFILE = html("ประวัตินักวิจัย – ดร.ปิยะ วงศ์สวัสดิ์", [
    "หัวข้อวิจัยและคำสำคัญ: นโยบายยานยนต์ไฟฟ้า, โครงสร้างพื้นฐานสถานีอัดประจุ, พฤติกรรมผู้บริโภค EV, การเปลี่ยนผ่านพลังงานในภาคขนส่ง",
    "สังกัด: สถาบันวิจัยนโยบายสาธารณะ มหาวิทยาลัย",
    "ผลงานตีพิมพ์: 1) ปัจจัยที่มีผลต่อความตั้งใจซื้อ EV ในภาคกลาง (TCI กลุ่ม 1, 2566) "
    "2) การกระจายตัวของสถานีอัดประจุในเมืองรอง (TCI กลุ่ม 2, 2567)",
    "ข้อจำกัดปัจจุบัน: ยังไม่มีภาคเอกชนร่วมทุนสำหรับหัวข้อแบตเตอรี่",
    "กฎภายในมหาวิทยาลัย: ต้องส่งข้อเสนอโครงการให้สำนักงานบริหารการวิจัยก่อนกำหนดส่งของแหล่งทุน 7 วัน"])
FUNDERS = html("รายชื่อแหล่งทุนที่ต้องติดตาม", [
    (("แหล่งทุน", "เว็บไซต์"),
     [("สำนักงานการวิจัยแห่งชาติ (วช.)", "https://www.nrct.go.th"),
      ("ระบบข้อมูลสารสนเทศวิจัยและนวัตกรรมแห่งชาติ (NRIIS)", "https://nriis.go.th"),
      ("บพข. (หน่วยบริหารและจัดการทุนด้านการเพิ่มความสามารถในการแข่งขันของประเทศ)", "https://www.pmuc.or.th"),
      ("บพท. (หน่วยบริหารและจัดการทุนด้านการพัฒนาระดับพื้นที่)", "https://www.pmua.or.th"),
      ("บพค. (หน่วยบริหารและจัดการทุนด้านการพัฒนากำลังคน)", "https://www.pmu-hr.or.th")])])
PAST = {
    "ข้อเสนอโครงการเดิม – ได้รับทุน 2567": html("ข้อเสนอโครงการที่ได้รับทุน ปี 2567", [
        "ชื่อโครงการ: แผนที่ความต้องการสถานีอัดประจุในเมืองรอง", "แหล่งทุน: บพท.",
        "จุดแข็งตามความเห็นผู้ทรงคุณวุฒิ: ระเบียบวิธีชัดเจน ใช้ข้อมูลเชิงพื้นที่ มีผลลัพธ์นำไปใช้ได้จริง"]),
    "ข้อเสนอโครงการเดิม – ไม่ได้รับทุน 2568": html("ข้อเสนอโครงการที่ไม่ได้รับทุน ปี 2568", [
        "ชื่อโครงการ: ต้นแบบธุรกิจรีไซเคิลแบตเตอรี่ EV", "แหล่งทุน: บพข.",
        "จุดอ่อนตามความเห็นผู้ทรงคุณวุฒิ: ไม่มีภาคเอกชนร่วมทุน, งบประมาณไม่สอดคล้องกับกิจกรรม, ตัวชี้วัดผลลัพธ์ไม่ชัด"]),
}
LOG_HEAD = "วันที่พบ,ชื่อประกาศ,แหล่งทุน,ลิงก์,กำหนดส่งแหล่งทุน,กำหนดส่งภายใน,ระดับความเหมาะสม,สถานะ,ชุดเริ่มต้น,โฟลเดอร์ข้อเสนอ,ความเห็นผู้ทรงคุณวุฒิ"
LOG_ROWS = [
    '2026-07-06,การเปลี่ยนผ่านสู่ยานยนต์ไฟฟ้าของไทย: ความพร้อมของสถานีอัดประจุในเมืองรอง,บพข.,https://www.pmuc.or.th,2026-08-14,2026-08-07,strong,ได้รับทุน,-,-,"ระเบียบวิธีชัดเจน แต่ควรเพิ่มภาคเอกชนร่วมทุน"',
    '2026-07-06,ทุนวิจัยพฤติกรรมผู้บริโภคยานยนต์ไฟฟ้า ปี 2570,วช.,https://www.nrct.go.th,2026-08-31,2026-08-24,possible,skip,-,-,',
]
LOG_ROW_EN = ('2026-07-13,ต้นแบบนโยบายแบตเตอรี่ใช้แล้วจากยานยนต์ไฟฟ้า,บพข.,https://www.pmuc.or.th,2026-08-21,2026-08-14,possible,ไม่ได้รับทุน,-,-,'
              '"ขาดภาคเอกชนร่วมทุน และตัวชี้วัดผลลัพธ์ยังไม่ชัดเจน"')


def build():
    ids = load()
    top = folder(TOP)
    ids["top"] = top["id"]
    # RES-A
    a = folder("RES-A ทบทวนหลักฐาน", top["id"])
    lib = folder("คลังเอกสาร EV", a["id"])
    ids |= {"res_a_folder": a["id"], "res_a_library": lib["id"]}
    for n, h in LIBRARY.items():
        ids.setdefault("library", {})[n] = upsert(n, lib["id"], h, "text/html", DOC)["id"]
    save(ids)
    ids["res_a_setup"] = upsert("ตั้งค่า – ทบทวนหลักฐาน", a["id"], setup_html(GOAL_TH, "th"), "text/html", DOC)["id"]
    # RES-B
    b = folder("RES-B วิจัยความตั้งใจซื้อรถยนต์ไฟฟ้า", top["id"])
    data = folder("ข้อมูลแบบสอบถาม EV", b["id"])
    ids |= {"res_b_folder": b["id"], "res_b_data_folder": data["id"]}
    csv = (VISHAL / "survey" / "survey_v2_1200 (TEST).csv").read_text(encoding="utf-8")
    if not find(DATA_NAME, data["id"]):
        ids["res_b_data"] = upsert(DATA_NAME, data["id"], csv, "text/csv")["id"]
    else:
        ids["res_b_data"] = find(DATA_NAME, data["id"])[0]["id"]
    ids["res_b_codebook"] = upsert("คู่มือลงรหัสข้อมูล – แบบสอบถาม EV", b["id"], CODEBOOK, "text/html", DOC)["id"]
    ids["res_b_plan"] = upsert("แผนการวิเคราะห์ข้อมูล – แบบสอบถาม EV", b["id"], html("แผนการวิเคราะห์ข้อมูล (Analysis plan)", PLAN_LINES), "text/html", DOC)["id"]
    # RES-C
    c = folder("RES-C ประกาศทุน", top["id"])
    ids["res_c_folder"] = c["id"]
    ids["res_c_profile"] = upsert("ประวัตินักวิจัย – ดร.ปิยะ", c["id"], PROFILE, "text/html", DOC)["id"]
    ids["res_c_funders"] = upsert("รายชื่อแหล่งทุนที่ต้องติดตาม", c["id"], FUNDERS, "text/html", DOC)["id"]
    for n, h in PAST.items():
        ids.setdefault("past", {})[n] = upsert(n, c["id"], h, "text/html", DOC)["id"]
    ids["res_c_log"] = upsert("บันทึกประกาศทุน", c["id"], "\n".join([LOG_HEAD] + LOG_ROWS) + "\n", "text/csv", SHEET)["id"]
    save(ids)
    print(json.dumps(ids, ensure_ascii=False, indent=1))


def setup_html(goal, lang, library=True, extra=""):
    ids = load()
    lib = f"https://drive.google.com/drive/folders/{ids['res_a_library']}" if library is True else library
    if lang == "th":
        lines = [f"เป้าหมาย: {goal}"] + ([f"คลังเอกสาร: {lib}"] if lib else []) + ([extra] if extra else [])
    else:
        lines = [f"Goal: {goal}"] + ([f"Library: {lib}"] if lib else []) + ([extra] if extra else [])
    return "<html><meta charset='utf-8'><body>" + "".join(f"<p>{x}</p>" for x in lines) + "</body></html>"


def load():
    return json.loads(IDS.read_text()) if IDS.exists() else {}


def save(ids):
    IDS.write_text(json.dumps(ids, ensure_ascii=False, indent=1))


def slot_time(minutes):
    """A time inside the slot that a run starting now reads: [floor(now) - minutes, floor(now)); unique per call."""
    now = dt.datetime.now(BKK)
    floor = now.replace(minute=(now.minute // minutes) * minutes, second=0, microsecond=0)
    return floor - dt.timedelta(minutes=minutes) + (now - floor)


def prep(case_id):
    ids = load()
    print(f"prep {case_id} at {dt.datetime.now(BKK):%H:%M:%S} Bangkok")
    a_setup = ids["res_a_setup"]
    if case_id.startswith("res-a-"):
        lang = case_id.split("-")[2]
        goal = {"th": GOAL_TH, "en": GOAL_EN}[lang]
        if "rejected" in case_id:
            goal = {"th": GOAL_TH_SHORT, "en": GOAL_EN_SHORT}[lang]
        lib = True
        if "no-library" in case_id:
            lib = "คลังเอกสาร EV ฉบับเก่า" if lang == "th" else "EV library (old)"
        upsert("ตั้งค่า – ทบทวนหลักฐาน", ids["res_a_folder"], setup_html(goal, lang, lib), "text/html", DOC)
        if "idle" in case_id:  # edited well before this hour's slot
            r = set_modified(a_setup, dt.datetime.now(BKK) - dt.timedelta(hours=3))
        else:
            r = set_modified(a_setup, slot_time(60))
        print("  setup doc", r)
    elif case_id.startswith("res-b-"):
        if "plan-changed" in case_id or case_id.startswith("res-b-en-full"):
            upsert("แผนการวิเคราะห์ข้อมูล – แบบสอบถาม EV", ids["res_b_folder"],
                   html("แผนการวิเคราะห์ข้อมูล (Analysis plan)", PLAN_LINES + [PLAN_H4]), "text/html", DOC)
            print("  plan", set_modified(ids["res_b_plan"], slot_time(30)))
        elif "nothing-new" in case_id:
            # nothing saved in this run's half hour: data and plan last saved 2 h ago
            print("  data", set_modified(ids["res_b_data"], dt.datetime.now(BKK) - dt.timedelta(hours=2)))
            print("  plan", set_modified(ids["res_b_plan"], dt.datetime.now(BKK) - dt.timedelta(hours=2, minutes=5)))
        elif "missing" in case_id:
            rename(ids["res_b_codebook"], "(old) คู่มือลงรหัสข้อมูล – แบบสอบถาม EV")
            print("  codebook renamed away")
        else:
            print("  data", set_modified(ids["res_b_data"], slot_time(30)))
    elif case_id.startswith("res-c-"):
        if "missing" in case_id:
            rename(ids["res_c_profile"], "(old) ประวัตินักวิจัย – ดร.ปิยะ")
            print("  profile renamed away")
        elif "nothing" in case_id or "quiet" in case_id or "weekly" in case_id:
            print("  log", set_modified(ids["res_c_log"], dt.datetime.now(BKK) - dt.timedelta(days=3)))
        else:
            # results path: profile without results; log with result rows, modified inside [yesterday 07:00, today 07:00)
            upsert("ประวัตินักวิจัย – ดร.ปิยะ", ids["res_c_folder"], PROFILE, "text/html", DOC)
            rows = LOG_ROWS + ([LOG_ROW_EN] if "-en-" in case_id else [])
            upsert("บันทึกประกาศทุน", ids["res_c_folder"], "\n".join([LOG_HEAD] + rows) + "\n", "text/csv", SHEET)
            now = dt.datetime.now(BKK)
            seven = now.replace(hour=7, minute=0, second=0, microsecond=0)
            when = now - dt.timedelta(minutes=1) if now < seven else seven - dt.timedelta(minutes=10)
            print("  profile reset; log rewritten", set_modified(ids["res_c_log"], when))


def restore(case_id):
    ids = load()
    if case_id.startswith("res-b-") and "missing" in case_id:
        rename(ids["res_b_codebook"], "คู่มือลงรหัสข้อมูล – แบบสอบถาม EV")
    if case_id.startswith("res-c-") and "missing" in case_id:
        rename(ids["res_c_profile"], "ประวัตินักวิจัย – ดร.ปิยะ")


def run(paths):
    for p in paths:
        case = json.loads(pathlib.Path(p).read_text())
        prep(case["id"])
        try:
            subprocess.run([sys.executable, str(ROOT / "tests/harness.py"), str(p)], cwd=ROOT)
        finally:
            restore(case["id"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ids"
    if cmd == "build":
        build()
    elif cmd == "prep":
        prep(sys.argv[2])
    elif cmd == "restore":
        restore(sys.argv[2])
    elif cmd == "run":
        run(sys.argv[2:])
    else:
        print(json.dumps(load(), ensure_ascii=False, indent=1))
