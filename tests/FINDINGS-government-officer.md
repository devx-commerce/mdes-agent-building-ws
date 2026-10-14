# FINDINGS – government-officer (GOV-A, GOV-B, GOV-C) – overnight 14 Oct 2026

Status: IN PROGRESS (updated as cases run). Results paths are under `tests/results/`. Session ids are in app `mdes-executive-app_1791205779351` (yash-test).

## Fixtures
Builder: `tests/fixtures/government-officer.py` (idempotent; `base`, `gov-a <full|remind-1|remind-2|keep>`, `gov-c <letter-1|letter-2|table-empty|table-ok>`). IDs in `tests/fixtures/government-officer.ids.json`.
Top folder `MDES WS4 yash tests – government-officer`: https://drive.google.com/drive/folders/1QjQTJ6Ya0hediTDBUzikdJEdl7JedDQk
- GOV-A `สำนักงานจังหวัดเชียงราย – รายงานประจำเดือน` https://drive.google.com/drive/folders/1n_ntmV_x7l8EA59NCkHf_O9NM6YVf0ZK : `รายชื่ออำเภอ` (Sheet: แม่สาย/เชียงแสน/พาน, deadline day 5, emails navya.agarwal+district-maesai/-chiangsaen/-phan, Head navya.agarwal+head), `รายงานผลการดำเนินงาน ส.ค. 69` (Doc, last month), `ผลการดำเนินงาน ก.ย. 69/` (แม่สาย PDF, เชียงแสน XLSX in บาท with one blank status, พาน Doc with water complaints missing). `เก็บไว้ชั่วคราว/` holds a district file for the reminder states.
- GOV-B save folder `บันทึกข้อความเสนอผู้บริหาร` https://drive.google.com/drive/folders/17WZ51JJzWi5mUTSjxzzYXpPphdRPHB6i
- GOV-C `งานสารบรรณ อำเภอแม่สาย` https://drive.google.com/drive/folders/1Uy7Rlz1qMR66i7gRDssEXRAA5I8Z447G : `หนังสือเข้า/` (scanned PNG letters, no text layer), `ตารางมอบหมายงาน` (4 units navya.agarwal+officer-*, Section Head navya.agarwal+sectionhead). The agent created `ทะเบียนติดตามหนังสือ` (1wLhxJIdz0SObDrc0CS3T6ngP-HWPwZ9VLkOjmD3Cpqk).
- Before building: no file in Navya's Drive matched รายชื่ออำเภอ / ผลการดำเนินงาน / บันทึกการทำงาน / หนังสือเข้า / ตารางมอบหมายงาน (Drive API search, 14 Oct 03:30 BKK), so no folder links are needed in start messages.

## Results
| Agent | Lang | Case | Result | Session | Min | Evidence |
|---|---|---|---|---|---|---|
| GOV-A | th | gov-a-th-full | PASS (deck loosened, see issues) | 6819735302708994456 | 14.5 | 20261013T205413Z: draft report Thai, 41.0/58.0/14.50/50.9 correct, flags (เชียงแสน blank status, พาน water) listed; work note created; 1 email to +head only |
| GOV-C | th | gov-c-th-full | PASS | 2279200047296254123 | 14.8 | 20261013T204625Z: scan OCR'd (ชร 0017/ว 2891, due 2026-10-20, ด่วนมาก), routed to งานป้องกันฯ, draft reply with [ตราครุฑ] and blanks, register row รอเกษียณ, routing note "[เกษียณหนังสือ][ด่วนมาก] …" to +sectionhead; 2 real inbox mails skipped as not_a_letter |
| GOV-B | th | gov-b-th-full | FAIL (platform: Drive connector auth) | 3784048771084183486 | ~45 | 20261013T203851Z: plan approved, research done (25 refs, Doc 1qJiFTEerUlaBvvDXzdpAmGzkoxn9G39Z6bKJFLHN0Xo), then report_ready: "การเชื่อมต่อ Google Drive หมดอายุหรือถูกยกเลิก"; clean stop, nothing sent. Harness then died on HTTP 401 ACCESS_TOKEN_TYPE_UNSUPPORTED (gcloud token). Drive read of the same Doc works again at 00:10 UTC (probe dir scratchpad) |
| GOV-A | th | gov-a-th-reject | PASS | 16086628121562732889 | 9.9 | 20261014T001105Z: Head rejects with no comment -> stops, draft kept, no deck/note/email; Thai message gives draft link |
| GOV-A | th | gov-a-th-draft-waiting | PASS | 991848570377819249 | 2.4 | 20261014T002159Z: right after reject -> no card, nothing created, says the ร่าง is waiting |
| GOV-A | th | gov-a-th-remind | PASS (wording bug found) | 302558023121418185 | 5.2 | 20261014T002434Z: พาน missing -> 1 email to +district-phan only; body asked to upload "ภายในวันที่ 2026-10-05" (past, ISO) -> fixed |
| GOV-A | th | gov-a-th-remind-2 | PASS (subject bug found) | 7331235174236487702 | 5.9 | 20261014T003356Z: แม่สาย missing -> email to +district-maesai says "เลยกำหนดส่งแล้วเมื่อวันที่ 5 ตุลาคม 2569 … โดยเร็วที่สุด"; but subject used the typed start text instead of the folder name -> fixed |
| GOV-B | th | gov-b-th-from-report | PASS* | 15293964905902437997 | 7.3 | 20261014T001102Z: saved report link -> no plan/research card; memo 18XU-AUA7M7eJmRaLB0JNboUXuMmLMsQ_N3OMDDptaA0 with 5 headings; email to +head with memo + report links. *Only failing check was mine (report ID in plain-text export; hyperlinks are dropped), link verified in card args. Memo had an English gloss "(Sources: …)" -> fixed |
| GOV-B | en | gov-b-en-full (1st) | FAIL (template) | 2832136501996764629 | 2.2 | 20261014T001108Z: propose_plan wrote "โปรดพิจารณาอนุมัติแผน…" as a chat message and the session went 'interrupted' with no card -> fixed (data-only clause) |
| GOV-C | th | gov-c-th-approve | PASS | 7713840393845633221 | 11.0 | 20261014T002156Z: after a reply อนุมัติ in the routing thread (sent via the app's Gmail tool, message 1a137c02eb6cf26f) -> Calendar event 2026-10-20 09:00 for +officer-disaster with the draft attached; register row 2 -> รอดำเนินการ; 10 other inbox mails (other agents' outputs) skipped as not_a_letter |

Earlier failed attempts (fixed): gov-a-th-full 20261013T203923Z (start text '[scheduled run]' skipped: NON_ASSIST_SEEKING_QUERY_IGNORED); gov-c-th-full 11228344311110578029 (find_reply error); gov-a-th-full 6640156905986996555 (build_deck error).

## Template fixes
1. TH approval cards (GOV-A review_report/_2, GOV-B plan_approval/_2/review_memo) still had English glosses → removed; `if true, the districts can see…` translated (TH only; EN is bilingual by design).
2. GOV-C find_reply (EN+TH): with no letter in status รอเกษียณ the model raised "LLM agent node 'find_reply' failed…" and the whole run failed (session 11228344311110578029). Added step 0: no pending letter = normal, return has_decision=false. Re-run passed.
3. GOV-A compare_months (EN+TH): an empty last-month work-note ID made it mark every change 'not comparable' and put "ไม่สามารถประเมินการเปลี่ยนแปลง… ไม่มีบันทึกการทำงาน" into the report's key points (session 6640156905986996555). Now only an empty REPORT ID means not comparable; TH uses 'เปรียบเทียบไม่ได้' instead of English.
4. GOV-A build_deck (EN+TH): a Slides tool error failed the whole run (6640156905986996555). Now it returns deck_link='' and the run continues to the work note and Head email (6819735302708994456: note says "สไลด์: ไม่มี", email omits the deck line).
5. GOV-A email_head and GOV-B email_head (EN+TH): "(เรียน หัวหน้าสำนักงาน…)" was copied literally with the ellipsis (6819735302708994456 email body). Now an explicit first line without ellipsis.

6. GOV-B propose_plan/replan (EN+TH): added the data-only clause (no message, never ask to approve). Verified: EN re-run shows the plan card.
7. GOV-B TH write_memo: removed the English gloss "(Sources: public sources only; …)" that was copied into the Thai memo. GOV-C TH node name "อนุมัติหรือไม่ (Approved?)" -> Thai only.
8. GOV-A send_reminders (EN+TH): deadline as a Thai date; if past, say เลยกำหนดส่งแล้ว and ask โดยเร็วที่สุด (verified 7331235174236487702). TH machine-translation leftovers ("ได้used", "จำนวน once ครั้ง") fixed.
9. GOV-A send_reminders + plan_reminders (EN+TH): subject pinned to "หนังสือติดตาม – ผลการดำเนินงาน <month> – <district>" and the sent-mail search uses the same text (7331235174236487702 used the typed start text as the "folder name", which would also break the 2-day reminder spacing).

## Harness change (shared file, minimal)
`tests/harness.py` grade(): the Thai-share check now ignores the ```json blocks the platform streams for data-only steps (they made Thai finals score 23–33%).

## Open issues
- Slides connector not connected for Navya in yash-test: "No Google Slides account is connected for this user…" (probe session 13578801035938876716; GOV-A build_deck). Deck creation cannot pass until Navya connects Slides. GOV-A full cases therefore do not require the deck file (stated in the cases).
- Drive connector auth dropped once mid-run (GOV-B 3784048771084183486, ~21:15 UTC), recovered later. Unverified cause.
- GOV-C read_letter set sender = "ศาลากลางจังหวัดเชียงราย" (the address line) instead of the issuing office; harmless but imprecise.
- GOV-C Calendar description says "สิ่งที่ขอความร่วมมือ/สั่งการ" instead of what is asked: find_reply returns no request summary (7713840393845633221). Minor, not fixed.
- Data-only steps stream their JSON output as chat text (every turn file); the user sees it unless the UI hides it (unverified in UI).
