# Executive agents (EXE-A, EXE-B, EXE-C): test findings, 14 Oct 2026 (overnight, as Navya, yash-test)

Status: in progress (written incrementally).

## Fixtures
- Top folder: [MDES WS4 yash tests – executive](https://drive.google.com/drive/folders/1xqxkOxmRYNkDNqQYsXFjXaFkYCSIvh7I). Builder: `tests/fixtures/executive.py` (`setup`, `reset a|b|c th|en [full|missing]`, `show`).
- The six agent folders pinned in `configs/yash-test.json` were moved into it, IDs unchanged. Old parent: "Excutive Agent" (1Bi6f6IjQ8YqHmpRfwOs65V1OUwyjTlEh).
- `reset` moves run outputs to the top folder's `Archive` subfolder (1yCKbICqyedBFs3rMFt2UL8hHrbdLltcb). Nothing is deleted.
- All addresses are navya.agarwal+<role>@devxlabs.ai: +head, +analyst, +secretary (A); +ceo, +strategy (B); +ceo, +assistant, +cfo, +coo, +sales, +strategy (C).
- Test markers were removed: "SYNTHETIC SAMPLE", "Sample document for testing", "TEST DATES".
- EXE-A: the current cycle is Q2 (quarter ended 2026-06-30, board 2026-10-28), because the bank files are 30 June 2026 statements. The prior cycle is Q1, with different numbers.
  - TH cycle names are "Peer Benchmark ไตรมาส 1/2-2569". "Peer Benchmark Q2-2569 - board pack" was already sent on 9 Oct, and the agent reads its stage from sent subjects.
  - EN cycle names are "Q1/Q2-2026". The two builds share one mailbox.
- EXE-C calendar fixture, in Navya's primary calendar (delete after review): "ExCom (ประชุมคณะกรรมการบริหาร)", 14 Oct 2026 17:00-18:30 Bangkok, event id 4co3bop15f4ooidhhg35dn36co. It was created with the Claude Calendar connector, not the app's.

## Cleanup list (outside the fixture folder)
- Calendar: the ExCom event above, and the "Due: … [2026-10-13-excom-N]" all-day invites created by the EXE-C runs (20, 22 and 27 Oct, guests +cfo/+sales/+coo).
- A pre-read that run exe-c-en-full (session 13527680991844538018) saved into Navya's real folder "Daily Sync - MDES (recurring)" (17-j166kutWmyYzvDpKlivZ36mzIaKXqP) was moved to Archive (1oQ5AgbbCsNGXXeBtObHrY-x4sSDUkLITmUauZHqz0tk).

## Running log (newest last)
- exe-a-en-full-table PASS (session 4674538769654991722, 12.4 min): the table is right (KBANK 2.75/3.50/38.52/3.25; SCB 2.97/3.78/41.34/2.65). One email went to +analyst.
- exe-b-en-full: harness PASS (session 1366228843551956520, 26.1 min), but the "Board deck" is a blank one-slide file (1hTgG0LVuqC8C1HNdyvcRevEdlRUMVfNGR1XIdx2uXKI).
  - create_presentation_from_outline failed because the Slides connector is not authorised. The agent then made an empty presentation through Drive.
  - The file is named with the UTC date ("Decision brief v1 (2026-10-13)"); in Bangkok it was already 14 Oct.
- exe-c-en-full: harness PASS (session 13527680991844538018, 48.8 min), but it had a serious bug.
  - The calendar step matched all 8 of the CEO's meetings to the ExCom folder.
  - One pre-read was saved into Navya's real Drive folder "Daily Sync - MDES (recurring)".
  - The EN pre-reads were half Thai.
  - Three invites were created correctly (+cfo 20 Oct, +sales 22 Oct, +coo 27 Oct). The vague action was held.
- exe-b-th-full, 1st attempt: FAIL, platform error (session 9074352141902130976). The `merge` step returned INTERNAL "Requests ending with a model turn are not supported" right after the plan card was approved. Re-run.
- exe-a-th-full-table: functionally right (session 11115789356412450627).
  - The table numbers match EN. One Thai email went to +analyst with the subject "Peer Benchmark ไตรมาส 2-2569 - ขอให้ช่วยตรวจสอบตัวเลข".
  - The email used ครับ. The run ended with JSON only, with no message to the user. One row key was "ธนาคาร SCB" instead of "SCB".
- exe-b-th-full, 2nd attempt (session 1397576411247554329, 22.2 min).
  - Plan, research, Thai draft, Thai brief v1, Signposts, Decision history and the Thai email to +ceo all came out right.
  - No deck was made (Slides). The harness's deck hit was A's file of the same name, made by a run at the same time.
  - The email used ครับ and ดิฉัน, and the run ended without a plain message.
- exe-a-th-full-report (session 9709714564215034283, 19.3 min). The analyst's Thai reply was read as approval with the SCB NPL correction.
  - The table was corrected (SCB 3.70, flag "นักวิเคราะห์แก้ไข: เดิม 3.78 ใหม่ 3.70"). The Thai report shows the right Q1→Q2 changes.
  - The Head's card warned that the deck was not updated (Slides). His typed point went into the report's "ประเด็นเพื่อพิจารณา". A Thai work note was written.
  - The email went to +secretary, cc +head.
  - The deck is still last quarter's: FAIL, Slides.
- exe-c-th-full, 1st attempt (session 18249853900245281459, 32.2 min). The folder fix worked: one Thai pre-read was saved, in ExCom only.
  - No invites were made: the TH action IDs (2026-10-13-excom-N) were the same as EN's, already in the same calendar, and the step correctly skipped them.
  - Even so, the summary said "4 invites created". Fixture changed: TH minutes are now dated 12 Oct. Re-run.
