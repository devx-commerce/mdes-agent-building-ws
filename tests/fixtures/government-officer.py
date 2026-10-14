#!/usr/bin/env python3
"""Fixtures for the government-officer agents (GOV-A, GOV-B, GOV-C) in Navya's Drive. Idempotent.

  python3 tests/fixtures/government-officer.py base                 build / repair everything, print the IDs
  python3 tests/fixtures/government-officer.py gov-a <state>        put GOV-A's Drive into a state before a run
        full      all 3 districts have sent; no outputs for ก.ย. 69 (drafts, deck, work note are trashed)
        remind-1  อำเภอพาน has not sent (its file is moved out); outputs trashed
        remind-2  อำเภอเชียงแสน has not sent (for the second language: a reminder to พาน was already sent today)
        remind-3  อำเภอแม่สาย has not sent (re-run after a template fix on the same day)
        keep      change nothing (for 'draft waiting' / 'already done' after another case)
  python3 tests/fixtures/government-officer.py gov-c <state>
        letter-1  one new scanned letter in หนังสือเข้า (flood data request, ด่วนมาก)
        letter-2  adds a second new scanned letter (budget follow-up, ปกติ)
        table-empty / table-ok   empty the routing table (header + Section Head row without email) / restore it
  python3 tests/fixtures/government-officer.py ids                  print the IDs and links

Everything lives under ONE top folder 'MDES WS4 yash tests – government-officer'. Only files inside it are ever
moved or trashed. Every email address is navya.agarwal+<role>@devxlabs.ai. No test markers in names or contents
(the agents refuse them): the data is realistic and synthetic (Chiang Rai province, invented numbers)."""
import json, pathlib, re, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

USER, QUOTA = "navya.agarwal@devxlabs.ai", "yash-test-495112"
TOP = "MDES WS4 yash tests – government-officer"
FOLDER, DOC, SHEET = "application/vnd.google-apps.folder", "application/vnd.google-apps.document", "application/vnd.google-apps.spreadsheet"
_tok = [None, 0]


def token():
    if not _tok[0] or time.time() - _tok[1] > 1800:
        _tok[0] = subprocess.check_output(["gcloud", "auth", "print-access-token", USER], text=True).strip()
        _tok[1] = time.time()
    return _tok[0]


def api(path, params=None, method="GET", body=None, upload=None):
    base = "https://www.googleapis.com/upload/drive/v3/" if upload else "https://www.googleapis.com/drive/v3/"
    q = "?" + urllib.parse.urlencode(params) if params else ""
    headers = {"Authorization": "Bearer " + token(), "X-Goog-User-Project": QUOTA}
    data = None
    if upload:
        b = "BOUNDARYgov7f3a"
        data = (f"--{b}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(body)}\r\n--{b}\r\n"
                f"Content-Type: {upload[1]}\r\n\r\n").encode() + upload[0] + f"\r\n--{b}--".encode()
        headers["Content-Type"] = f"multipart/related; boundary={b}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path + q, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} {method} {path}: {e.read().decode()[:500]}")


F = "id,name,mimeType,parents,webViewLink,createdTime,modifiedTime"


def children(parent):
    out, tok = [], None
    while True:
        p = {"q": f"'{parent}' in parents and trashed = false", "fields": f"nextPageToken,files({F})", "pageSize": 200}
        if tok:
            p["pageToken"] = tok
        r = api("files", p)
        out += r.get("files", [])
        tok = r.get("nextPageToken")
        if not tok:
            return out


def child(parent, name):
    hits = [f for f in children(parent) if f["name"] == name]
    return hits[0] if hits else None


def folder(parent, name):
    f = child(parent, name) if parent else None
    if not parent:
        r = api("files", {"q": f"name = '{name}' and mimeType = '{FOLDER}' and 'root' in parents and trashed = false", "fields": f"files({F})"})
        f = (r.get("files") or [None])[0]
    if f:
        return f
    return api("files", {"fields": F}, "POST", {"name": name, "mimeType": FOLDER, "parents": [parent or "root"]})


def put(parent, name, data, src_mime, as_mime=None, replace=False):
    """Create the file if it is missing (as_mime converts: text/html -> Doc, text/csv -> Sheet). replace=True re-uploads content."""
    f = child(parent, name)
    if f and not replace:
        return f
    data = data.encode() if isinstance(data, str) else data
    if f:
        return api(f"files/{f['id']}", {"uploadType": "multipart", "fields": F}, "PATCH", {}, upload=(data, src_mime))
    meta = {"name": name, "parents": [parent]}
    if as_mime:
        meta["mimeType"] = as_mime
    return api("files", {"uploadType": "multipart", "fields": F}, "POST", meta, upload=(data, src_mime))


def move(fid, old, new):
    api(f"files/{fid}", {"addParents": new, "removeParents": old, "fields": "id"}, "PATCH", {})


def trash_matching(parent, pattern):
    for f in children(parent):
        if re.search(pattern, f["name"]):
            api(f"files/{f['id']}", {"fields": "id"}, "PATCH", {"trashed": True})
            print("  trashed", f["name"])


def soffice(html_or_csv, name, out_ext, filt=None):
    """Convert a local HTML/CSV to pdf/xlsx/png with LibreOffice; return the bytes."""
    d = pathlib.Path(tempfile.mkdtemp())
    src = d / name
    src.write_text(html_or_csv, encoding="utf-8")
    step = "pdf" if out_ext == "png" else (filt or out_ext)
    subprocess.run(["soffice", "--headless", "--convert-to", step, "--outdir", str(d), str(src)], check=True, capture_output=True)
    if out_ext == "png":  # a 'scan': first page rendered to an image (macOS Quick Look, ~145 dpi), no text layer
        subprocess.run(["qlmanage", "-t", "-s", "1700", "-o", str(d), str(d / (src.stem + ".pdf"))], check=True, capture_output=True)
        return (d / (src.stem + ".pdf.png")).read_bytes()
    return (d / (src.stem + "." + out_ext)).read_bytes()


CSS = "<style>body{font-family:'Thonburi','Sukhumvit Set',sans-serif;font-size:14pt} table{border-collapse:collapse} td,th{border:1px solid #000;padding:4px 8px}</style>"
BANNER = "สำนักงานจังหวัดเชียงราย กลุ่มงานยุทธศาสตร์และข้อมูลเพื่อการพัฒนาจังหวัด"
HEAD = "navya.agarwal+head@devxlabs.ai"
DISTRICTS = [("อำเภอแม่สาย", "navya.agarwal+district-maesai@devxlabs.ai"),
             ("อำเภอเชียงแสน", "navya.agarwal+district-chiangsaen@devxlabs.ai"),
             ("อำเภอพาน", "navya.agarwal+district-phan@devxlabs.ai")]
# Aug 2569 (last month): allocated, disbursed (ล้านบาท), projects total/done/in progress/not started, complaints, water
AUG = {"อำเภอแม่สาย": (30.0, 18.6, 8, 2, 5, 1, 12, 3), "อำเภอเชียงแสน": (25.0, 13.75, 6, 2, 4, 0, 7, 1),
       "อำเภอพาน": (20.0, 9.6, 5, 1, 3, 1, 5, 2)}


def district_list_csv():
    rows = ["ลำดับ,อำเภอ,อีเมลผู้ประสานงาน,กำหนดส่ง"]
    rows += [f"{i},{n},{e},5" for i, (n, e) in enumerate(DISTRICTS, 1)]
    rows.append(f",อีเมลหัวหน้าสำนักงาน (ตั้งค่า),{HEAD},")
    return "\n".join(rows) + "\n"


def aug_report_html():
    def tr(cells, th=False):
        t = "th" if th else "td"
        return "<tr>" + "".join(f"<{t}>{c}</{t}>" for c in cells) + "</tr>"
    alloc = sum(v[0] for v in AUG.values()); disb = sum(v[1] for v in AUG.values())
    t1 = tr(["อำเภอ", "งบที่ได้รับจัดสรร (ล้านบาท)", "เบิกจ่ายแล้ว (ล้านบาท)", "ร้อยละ"], True) + "".join(
        tr([n, f"{v[0]:.2f}", f"{v[1]:.2f}", f"{v[1] / v[0] * 100:.1f}"]) for n, v in AUG.items()) + tr(
        ["<b>รวม</b>", f"<b>{alloc:.2f}</b>", f"<b>{disb:.2f}</b>", f"<b>{disb / alloc * 100:.1f}</b>"])
    t2 = tr(["อำเภอ", "ทั้งหมด", "แล้วเสร็จ", "อยู่ระหว่างดำเนินการ", "ยังไม่เริ่ม"], True) + "".join(
        tr([n, v[2], v[3], v[4], v[5]]) for n, v in AUG.items())
    t3 = tr(["อำเภอ", "ทั้งหมด", "การประปา"], True) + "".join(tr([n, v[6], v[7]]) for n, v in AUG.items())
    return f"""<html><head><meta charset="utf-8">{CSS}</head><body>
<p><b>{BANNER}</b></p>
<h1>รายงานผลการดำเนินงานประจำเดือน สิงหาคม 2569</h1>
<p>สำหรับการประชุมหัวหน้าส่วนราชการประจำเดือน</p>
<h2>บทสรุปผู้บริหาร</h2>
<p>อำเภอส่งรายงานครบทั้ง 3 อำเภอ งบประมาณที่ได้รับจัดสรรรวม {alloc:.2f} ล้านบาท เบิกจ่ายแล้ว {disb:.2f} ล้านบาท คิดเป็นร้อยละ {disb / alloc * 100:.1f} อำเภอแม่สาย มีผลการเบิกจ่ายสูงสุด (ร้อยละ 62.0) เรื่องร้องเรียนศูนย์ดำรงธรรมรวม 24 เรื่อง เป็นเรื่องการประปา 6 เรื่อง</p>
<h2>ประเด็นสำคัญประจำเดือน</h2>
<ul><li>ภาพรวมการเบิกจ่ายร้อยละ {disb / alloc * 100:.1f}</li><li>อำเภอพาน มีผลการเบิกจ่ายต่ำสุด (ร้อยละ 48.0)</li><li>เรื่องร้องเรียนการประปาของอำเภอแม่สาย 3 เรื่อง ควรติดตามต่อเนื่อง</li></ul>
<h2>1. ผลการเบิกจ่ายงบประมาณ</h2><table border="1">{t1}</table>
<h2>2. โครงการตามแผนพัฒนาจังหวัด</h2><table border="1">{t2}</table>
<h2>3. เรื่องร้องเรียนศูนย์ดำรงธรรม</h2><table border="1">{t3}</table>
<h2>ข้อเสนอและสิ่งที่ต้องติดตาม</h2>
<ul><li>อำเภอพาน เร่งรัดการเบิกจ่ายงบประมาณให้เป็นไปตามแผน</li><li>อำเภอแม่สาย ประสานการประปาส่วนภูมิภาคเรื่องน้ำประปาไหลอ่อน</li></ul>
</body></html>"""


def maesai_html():
    return f"""<html><head><meta charset="utf-8">{CSS}</head><body>
<p style="text-align:center"><b>แบบรายงานผลการดำเนินงานประจำเดือน กันยายน 2569</b></p>
<p>หน่วยงาน: ที่ทำการปกครองอำเภอแม่สาย จังหวัดเชียงราย</p>
<p><b>1. ผลการเบิกจ่ายงบประมาณ (หน่วย: ล้านบาท)</b></p>
<table><tr><th>งบประมาณที่ได้รับ</th><th>เบิกจ่ายแล้ว</th><th>ร้อยละการเบิกจ่าย</th></tr><tr><td>30.00</td><td>12.30</td><td>41.0</td></tr></table>
<p><b>2. ความก้าวหน้าโครงการตามแผนพัฒนาจังหวัด</b></p>
<table><tr><th>ทั้งหมด</th><th>แล้วเสร็จ</th><th>อยู่ระหว่างดำเนินการ</th><th>ยังไม่เริ่ม</th></tr><tr><td>8</td><td>3</td><td>4</td><td>1</td></tr></table>
<p><b>3. เรื่องร้องเรียนศูนย์ดำรงธรรม</b></p>
<table><tr><th>เรื่องร้องเรียนทั้งหมด</th><th>เรื่องการประปา</th></tr><tr><td>14</td><td>6</td></tr></table>
<p>ผู้รายงาน: ปลัดอำเภอแม่สาย &nbsp;&nbsp;&nbsp; วันที่: 3 ต.ค. 2569</p>
</body></html>"""


def chiangsaen_csv():
    return "\n".join([
        "แบบรายงานผลการดำเนินงานประจำเดือน กันยายน 2569 – ที่ทำการปกครองอำเภอเชียงแสน,,",
        ",,", "ตัวชี้วัด,ค่า,หน่วย", "งบประมาณที่ได้รับ,25000000,บาท", "เบิกจ่ายแล้ว,14500000,บาท", ",,",
        "โครงการตามแผนพัฒนาจังหวัด,สถานะ,", "โครงการ 1 ปรับปรุงถนนหมู่ 3,แล้วเสร็จ,", "โครงการ 2 ขุดลอกคลองส่งน้ำ,แล้วเสร็จ,",
        "โครงการ 3 ศูนย์พัฒนาเด็กเล็ก,อยู่ระหว่างดำเนินการ,", "โครงการ 4 ไฟฟ้าส่องสว่าง,อยู่ระหว่างดำเนินการ,",
        "โครงการ 5 ระบบประปาหมู่บ้าน,อยู่ระหว่างดำเนินการ,", "โครงการ 6 ลานกีฬาชุมชน,,", ",,",
        "เรื่องร้องเรียนศูนย์ดำรงธรรม (ทั้งหมด),9,เรื่อง", "เรื่องการประปา,1,เรื่อง"]) + "\n"


def phan_html():
    return f"""<html><head><meta charset="utf-8"></head><body>
<p><b>รายงานผลการดำเนินงานประจำเดือน กันยายน 2569 อำเภอพาน</b></p>
<p>เรียน ผู้ว่าราชการจังหวัดเชียงราย</p>
<p>อำเภอพาน ขอรายงานผลการดำเนินงานประจำเดือนกันยายน 2569 ดังนี้</p>
<p>1. งบประมาณที่ได้รับจัดสรร 20.00 ล้านบาท เบิกจ่ายแล้ว 11.40 ล้านบาท</p>
<p>2. โครงการตามแผนพัฒนาจังหวัด ทั้งหมด 5 โครงการ แล้วเสร็จ 2 โครงการ อยู่ระหว่างดำเนินการ 2 โครงการ ยังไม่เริ่ม 1 โครงการ</p>
<p>3. เรื่องร้องเรียนศูนย์ดำรงธรรม ทั้งหมด 4 เรื่อง เรื่องการประปา: อยู่ระหว่างรวบรวมข้อมูล</p>
<p>นายอำเภอพาน</p></body></html>"""


ROUTING = "\n".join([
    "หัวข้อ/ประเภทเรื่อง,หน่วยงานผู้รับผิดชอบ,อีเมลเจ้าหน้าที่ผู้รับผิดชอบ",
    "ภัยพิบัติ น้ำท่วม ภัยแล้ง สาธารณภัย ผู้ประสบภัย,งานป้องกันและบรรเทาสาธารณภัย,navya.agarwal+officer-disaster@devxlabs.ai",
    "งบประมาณ การเงิน การเบิกจ่าย พัสดุ,งานการเงินและบัญชี,navya.agarwal+officer-finance@devxlabs.ai",
    "บุคลากร การฝึกอบรม การประชุม,งานบุคคล,navya.agarwal+officer-hr@devxlabs.ai",
    "ทะเบียนราษฎร บัตรประจำตัวประชาชน,งานทะเบียนและบัตร,navya.agarwal+officer-registry@devxlabs.ai",
    "หัวหน้ากลุ่มงาน,หัวหน้ากลุ่มงาน,navya.agarwal+sectionhead@devxlabs.ai"]) + "\n"
ROUTING_EMPTY = "หัวข้อ/ประเภทเรื่อง,หน่วยงานผู้รับผิดชอบ,อีเมลเจ้าหน้าที่ผู้รับผิดชอบ\nหัวหน้ากลุ่มงาน,หัวหน้ากลุ่มงาน,\n"

LETTER_STYLE = ("<style>body{font-family:'Thonburi',sans-serif;font-size:15pt;width:17cm} .c{text-align:center} .r{text-align:right}"
                " p{margin:4px 0}</style>")
LETTERS = {
    "letter-1": ("หนังสือเข้า ชร 0017-ว 2891 (สแกน).png", f"""<html><head><meta charset="utf-8">{LETTER_STYLE}</head><body>
<p class="r"><b>ด่วนมาก</b></p>
<p>ที่ ชร 0017/ว 2891</p><p class="r">ศาลากลางจังหวัดเชียงราย<br>ถนนแม่ฟ้าหลวง ชร 57000</p>
<p class="c">9 ตุลาคม 2569</p>
<p>เรื่อง ขอข้อมูลครัวเรือนผู้ประสบภัยน้ำท่วม</p>
<p>เรียน นายอำเภอแม่สาย</p>
<p>สิ่งที่ส่งมาด้วย แบบสำรวจครัวเรือนผู้ประสบภัย จำนวน 1 ชุด</p>
<p>&nbsp;&nbsp;&nbsp;&nbsp;ด้วยระหว่างวันที่ 25 – 29 กันยายน 2569 ได้เกิดอุทกภัยในพื้นที่อำเภอแม่สาย ทำให้ประชาชนได้รับความเดือดร้อน
จังหวัดเชียงรายจึงขอให้อำเภอแม่สายรวบรวมข้อมูลจำนวนครัวเรือนที่ได้รับผลกระทบ แยกรายตำบล ตามแบบสำรวจที่ส่งมาด้วย
เพื่อใช้ประกอบการพิจารณาให้ความช่วยเหลือ</p>
<p>&nbsp;&nbsp;&nbsp;&nbsp;จึงเรียนมาเพื่อโปรดดำเนินการ และส่งข้อมูลให้จังหวัดภายในวันที่ 20 ตุลาคม 2569</p>
<p class="c">ขอแสดงความนับถือ</p><p class="c">(นายสมชาย ใจดี)<br>รองผู้ว่าราชการจังหวัด ปฏิบัติราชการแทน<br>ผู้ว่าราชการจังหวัดเชียงราย</p>
<p>สำนักงานป้องกันและบรรเทาสาธารณภัยจังหวัดเชียงราย<br>โทร. 0 5317 7316</p></body></html>"""),
    "letter-2": ("หนังสือเข้า ชร 0023-1544 (สแกน).png", f"""<html><head><meta charset="utf-8">{LETTER_STYLE}</head><body>
<p>ที่ ชร 0023/1544</p><p class="r">สำนักงานคลังจังหวัดเชียงราย<br>ศาลากลางจังหวัดเชียงราย ชร 57000</p>
<p class="c">12 ตุลาคม 2569</p>
<p>เรื่อง ขอให้รายงานผลการเบิกจ่ายงบประมาณรายจ่ายประจำปีงบประมาณ พ.ศ. 2569</p>
<p>เรียน นายอำเภอแม่สาย</p>
<p>&nbsp;&nbsp;&nbsp;&nbsp;ด้วยสำนักงานคลังจังหวัดเชียงรายจะต้องรายงานผลการเบิกจ่ายงบประมาณภาพรวมของจังหวัดต่อกรมบัญชีกลาง
จึงขอให้อำเภอแม่สายรายงานผลการเบิกจ่ายงบประมาณประจำปีงบประมาณ พ.ศ. 2569 แยกตามงบรายจ่าย
พร้อมเหตุผลกรณีที่เบิกจ่ายไม่เป็นไปตามแผน</p>
<p>&nbsp;&nbsp;&nbsp;&nbsp;จึงเรียนมาเพื่อโปรดพิจารณาดำเนินการ ทั้งนี้ ขอให้ส่งข้อมูลภายในวันที่ 30 ตุลาคม 2569</p>
<p class="c">ขอแสดงความนับถือ</p><p class="c">(นางสาววรรณา ศรีสุข)<br>คลังจังหวัดเชียงราย</p>
<p>กลุ่มงานบริหารการเงินการคลัง<br>โทร. 0 5371 1234</p></body></html>"""),
}


def ids_path():
    return pathlib.Path(__file__).with_suffix(".ids.json")


def base():
    top = folder(None, TOP)
    a = folder(top["id"], "สำนักงานจังหวัดเชียงราย – รายงานประจำเดือน")
    a_sep = folder(a["id"], "ผลการดำเนินงาน ก.ย. 69")
    a_hold = folder(top["id"], "เก็บไว้ชั่วคราว")  # holding place for a district file in the reminder states
    put(a["id"], "รายชื่ออำเภอ", district_list_csv(), "text/csv", SHEET)
    put(a["id"], "รายงานผลการดำเนินงาน ส.ค. 69", aug_report_html(), "text/html", DOC)
    have = {f["name"] for f in children(a_sep["id"])} | {f["name"] for f in children(a_hold["id"])}
    if "อำเภอแม่สาย – ก.ย. 69.pdf" not in have:
        put(a_sep["id"], "อำเภอแม่สาย – ก.ย. 69.pdf", soffice(maesai_html(), "maesai.html", "pdf"), "application/pdf")
    if "อำเภอเชียงแสน – ก.ย. 69.xlsx" not in have:
        put(a_sep["id"], "อำเภอเชียงแสน – ก.ย. 69.xlsx", soffice(chiangsaen_csv(), "chiangsaen.csv", "xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if "อำเภอพาน – ก.ย. 69" not in have:
        put(a_sep["id"], "อำเภอพาน – ก.ย. 69", phan_html(), "text/html", DOC)
    b = folder(top["id"], "บันทึกข้อความเสนอผู้บริหาร")
    c = folder(top["id"], "งานสารบรรณ อำเภอแม่สาย")
    c_in = folder(c["id"], "หนังสือเข้า")
    put(c["id"], "ตารางมอบหมายงาน", ROUTING, "text/csv", SHEET)
    ids = {"top": top["id"], "gov_a": a["id"], "gov_a_sep": a_sep["id"], "gov_a_hold": a_hold["id"], "gov_b": b["id"],
           "gov_c": c["id"], "gov_c_in": c_in["id"], "routing": child(c["id"], "ตารางมอบหมายงาน")["id"],
           "district_list": child(a["id"], "รายชื่ออำเภอ")["id"], "aug_report": child(a["id"], "รายงานผลการดำเนินงาน ส.ค. 69")["id"]}
    ids_path().write_text(json.dumps(ids, indent=1) + "\n")
    return ids


def gov_a(state, ids):
    a, sep, hold = ids["gov_a"], ids["gov_a_sep"], ids["gov_a_hold"]
    if state == "keep":
        return
    # outputs of an earlier run for ก.ย. 69 (only inside the GOV-A folder)
    trash_matching(a, r"^(รายงานผลการดำเนินงาน ก\.ย\. 69|บันทึกการทำงาน ก\.ย\. 69|สรุปผลการดำเนินงาน ก\.ย\. 69)")
    want_out = {"full": None, "remind-1": "อำเภอพาน", "remind-2": "อำเภอเชียงแสน", "remind-3": "อำเภอแม่สาย"}[state]
    for f in children(hold):  # bring every district file back
        move(f["id"], hold, sep)
    if want_out:
        for f in children(sep):
            if f["name"].startswith(want_out):
                move(f["id"], sep, hold)
                print("  moved out", f["name"])
    print("  submission folder now:", sorted(f["name"] for f in children(sep)))


def gov_c(state, ids):
    c, cin = ids["gov_c"], ids["gov_c_in"]
    if state in LETTERS:
        name, html = LETTERS[state]
        if not child(cin, name):
            png = soffice(html, state + ".html", "png")
            put(cin, name, png, "image/png")
            print("  added scan", name)
    elif state == "table-empty":
        put(c, "ตารางมอบหมายงาน", ROUTING_EMPTY, "text/csv", SHEET, replace=True)
    elif state == "table-ok":
        put(c, "ตารางมอบหมายงาน", ROUTING, "text/csv", SHEET, replace=True)
    print("  หนังสือเข้า:", sorted(f["name"] for f in children(cin)))


def show(ids):
    for k, v in ids.items():
        print(f"{k:14} https://drive.google.com/drive/folders/{v}" if k not in ("routing", "district_list", "aug_report")
              else f"{k:14} https://drive.google.com/file/d/{v}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "base"
    ids = json.loads(ids_path().read_text()) if ids_path().exists() and cmd != "base" else base()
    if cmd == "gov-a":
        gov_a(sys.argv[2], ids)
    elif cmd == "gov-c":
        gov_c(sys.argv[2], ids)
    else:
        show(ids)
