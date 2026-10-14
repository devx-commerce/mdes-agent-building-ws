# FINDINGS – researcher persona (RES-A, RES-B, RES-C), yash-test, 14 Oct 2026 (night run, Bangkok time)

Status: IN PROGRESS (updated as runs finish). Sessions are in app `mdes-executive-app_1791205779351`
(`projects/632653045864/locations/global/collections/default_collection/engines/mdes-executive-app_1791205779351/sessions/<id>`).
Results: `tests/results/<stamp>/<case>/result.json`.

## How to run
`python3 tests/fixtures/researcher.py build` once (idempotent), then per case
`python3 tests/fixtures/researcher.py run tests/cases/<case>.json`: it puts the fixtures in the state the case needs
(Setup Doc text, Drive `modifiedTime` inside the agent's time slot, a renamed file for "missing" cases), runs
`tests/harness.py`, and restores renamed files. `harness.py` alone skips the prep, so the slot rules decide the path.
Run cases of the same agent one at a time (TH and EN share the same Drive fixtures).

Start text: `[scheduled run]` is dropped by the platform before the agent runs (`assistSkippedReasons:
NON_ASSIST_SEEKING_QUERY_IGNORED`, no session: `tests/results/20261013T203933Z`, `…203940Z`, `…203941Z`). The cases use
an assist-seeking text: TH `เริ่มการทำงานรอบตามกำหนดเวลาตอนนี้`, EN `Run the scheduled check now.`

Slot rules, as the templates define them (the PREVIOUS slot, not the current one):
- RES-A: Setup Doc modified in [current hour − 1 h, current hour:00) (07:00 run: from 18:00 yesterday).
- RES-B: newest data file or plan modified in [half hour − 30 min, half hour).
- RES-C: calls log modified in [yesterday 07:00, today 07:00); weekly search only when today is a Monday.

## Fixtures
Top folder `MDES WS4 yash tests – researcher`: https://drive.google.com/drive/folders/1tU0m2hA0JxxGOqZVMWb_mcffifCOxllO
- RES-A `RES-A ทบทวนหลักฐาน` https://drive.google.com/drive/folders/1Ml73t01ycgGgXM9x_PO5h_soc-u3LPTF : Setup Doc
  `ตั้งค่า – ทบทวนหลักฐาน` (159YBRuFevgFW0F2Jntk9NBWKkUHflZxMuaUHk6l04Pc); library `คลังเอกสาร EV`
  https://drive.google.com/drive/folders/1NeK4xq7BGhtMWpTM-7NrsjVgqiiwr2TI : 5 Google Docs with Vishal's planted conflicts
  (mdes-agent/test-data/res/ANSWER-KEY.md), without test markers.
- RES-B `RES-B วิจัยความตั้งใจซื้อรถยนต์ไฟฟ้า` https://drive.google.com/drive/folders/1W6kg6xokZaIlwU3A3gC_XSsI_tqOV6iv :
  data folder `ข้อมูลแบบสอบถาม EV` with `แบบสอบถาม EV 2569 – n1200.csv` (= Vishal's survey_v2_1200: 300 'South',
  14 × q12 = 9, 23 blank incomes), the codebook Doc and the analysis plan Doc.
- RES-C `RES-C ประกาศทุน` https://drive.google.com/drive/folders/1gO2VFXZ3yogpGK-V_NnMjRr-4aXHsSmj : profile Doc
  `ประวัตินักวิจัย – ดร.ปิยะ`, funder list, 2 past proposals, calls log Sheet `บันทึกประกาศทุน` with a funded row.
- Before the build, no file in Navya's Drive matched any name the agents search for (Drive search, 14 Oct 03:3x).
- Ids are in `tests/fixtures/researcher.ids.json`. The only address in play is navya.agarwal@devxlabs.ai (the owner
  of the folders, which the agents email); the fixtures contain no other address.

## Results

Session ids are the last part of the session name. "Pre-fix" = run before the template fix listed below was deployed.

### RES-C Funding Calls – TH
| case | result | session | min | evidence |
|---|---|---|---|---|
| res-c-th-results | PASS | 1897022573631105896 | 4.7 | append_to_doc added `ผลการพิจารณาทุน 2026-10-14` with the funded call + reviewer comment to the profile Doc; final Thai, names the call (`tests/results/20261014T001328Z`). Earlier PASS 3762187758884906915 (pre-fix: final message was the raw data line with "Wednesday", "True", a Python list) |
| res-c-th-quiet | PASS | 6667855702962978881 | 2.9 | log last edited 3 days ago, not Monday → one Thai line, no cards (`20261013T205106Z`) |
| res-c-th-missing | PASS | 4716635361171487574 | 3.8 | profile renamed away → ONE send_email to navya.agarwal@devxlabs.ai, subject `ติดตามประกาศทุน: ยังเริ่มไม่ได้` (`20261014T000929Z`). Pre-fix run 4700081362270645598 had an English gloss in the subject |
| res-c-th-weekly (probe) | PASS (as template designs) | 5179051151533076737 | 2.7 | typed "ค้นหาประกาศทุนประจำสัปดาห์ตอนนี้" on a Wednesday → find_setup search_day=false → 'not today' summary, no search (`20261013T205945Z`) |

The Monday weekly search (deep research, rating, starter packs, calendar deadlines, digest email, go/skip card, proposal
folders, invites) cannot be reached on 14 Oct (a Wednesday): `search_day` is computed from today's date only, and a
typed request does not change it (session 5179051151533076737). NOT TESTED; re-run `res-c-*-weekly` (expect changes:
cards_seen deep_research_run, create_file, create_event, send_email, go_skip) on a Monday.

### RES-B Survey Analysis – TH
| case | result | session | min | evidence |
|---|---|---|---|---|
| res-b-th-full | FAIL (platform) | 15272027436308400751 | 16.3 | data check = answer key (300 'South', 23 blank income, 14 × q12=9); rules card; analyse_survey H1 r 0.453, H2 r −0.209, H3 F 22.67, region means 2.87/2.67/3.30/3.10 = ANSWER-KEY v2_1200; chapter `บทที่ 4 ผลการวิจัย – v1` (Thai, 86 %) + chart sheet + chart inserted; then make_slides errorEvent "ไม่สามารถสร้างสไลด์ได้เนื่องจากระบบยังไม่ได้เชื่อมต่อกับบัญชี Google Slides" → run failed, no log row, no email (`20261013T204011Z`) |
| res-b-th-rejected | PASS | 3779185334723028481 | 4.8 | reject on the issues card → "ผู้วิจัยปฏิเสธ … ไม่มีการวิเคราะห์หรือเปลี่ยนแปลงสิ่งใด", no chapter/slides/email (`20261013T205936Z`) |
| res-b-th-nothing-new | PASS | 14361543802507475140 | 2.4 | data + plan last saved 2 h ago → Thai 'nothing new, save again' line, no cards (`20261013T210429Z`) |
| res-b-th-missing | PASS | 301203776390695590 | 4.2 | codebook renamed away → ONE email to navya.agarwal@devxlabs.ai naming the codebook (`20261014T000929Z`). Pre-fix run 16898420145089982293 also listed the rules for the two files that were found |

### RES-A Evidence Review – TH
| case | result | session | min | evidence |
|---|---|---|---|---|
| res-a-th-full | PASS (pre-fix template) | 8737104977138571001 | 40.9 | plan card → added question → changed plan card (question 4 = the added one) → deep_research_run → table `ตารางเปรียบเทียบหลักฐาน – เปรียบเทียบเป้าหมายยานยนต์ไฟฟ้าไทย` (1YhL7Q73pH8SlJaAz5bKqzoRxucOaW4OY5MGAKxD3O70) has 359,000 and 41,800 → question card → briefing 16onDd-otxYRVWo_dhPMpUaVVmsNv3tEmdV5Ru1r1g-g (Thai 97 %, has 725,000) → change-record row. Final answer explains approved capacity 359,000 vs built 41,800 vs BEV+PHEV 78,000, as the answer key plants (`20261013T204020Z`) |
| res-a-th-rejected | FAIL → re-run | 15226700458155214128 | 6.9 | reject worked, but r_log_rejected asked "กรุณายืนยัน…" in TEXT instead of calling append_rows → session interrupted waiting for typed text (`20261014T000933Z`). Fixed (see below), re-run pending |
| res-a-th-idle | FAIL (time limit only) | 10791171012792698731 | 17.4 | correct path: goal already reviewed → tell_idle Thai line, no cards; but the first stream call took >10 min (case limit 10 min). Limits raised to 25 min; re-run pending (`20261014T001634Z`) |
