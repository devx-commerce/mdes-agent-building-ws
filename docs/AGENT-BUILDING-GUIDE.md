# Building MDES agents: what we learned (read before building a new one)

This guide is for anyone adding agents on top of this repo. Every rule here was learned by building and testing the 9 MDES agents (GOV-A/B/C, RES-A/B/C, EXE-A/B/C) on Gemini Enterprise Workflow Builder, Oct 2026. Where a rule came from a test, the session id or finding is given, so you can check it.

---

## 1. What these agents are

**Personal productivity tools, not shared services.** Each agent runs **as the user who starts it**, on **their own** Google (and Microsoft) data, through MCP connectors the user signs in to once. An officer types `@agent` + a request, or a schedule starts it. The agent reads their Drive, drafts in their Docs and mails from their Gmail, and every write waits for **their** confirmation.

So:
- **Nothing per user, office, month or person is built into an agent.** No folder IDs, emails, names or months in instructions.
  - The month comes from today's date or the message.
  - Files are found **by name** in the user's Drive.
  - People's emails come from the **user's own list file** (e.g. a district list Sheet).
- **Found → use it. Missing or two matches → stop and tell the user exactly what to create or type** (names and links, never IDs). If something can be created safely (an empty template, a folder), create it and say so.
- **Show what was used** (names + links) and **where to change it**, in the final message.
- **Fewest cards.** Every card is a click and a chance to stall. Justify each one.
- When a workflow is shared, **each user runs it on their own data with their own triggers.** Google: "Triggers on a shared workflow are user-specific". Design for that.

## 2. Where things live

| Environment | Project / app | Use |
|---|---|---|
| **yash-test** | yash-test-495112 / `mdes-executive-app_1791205779351` (global) | Build and test. The only project where approval and tool cards can be answered **through the API** (Google preview feature), so automated end-to-end tests and evals run here. All 18 builds (EN + TH). |
| thai-gov-poc | thai-gov-poc / `mdes-executive-agents` (us) | Internal review env shown to Google. No API card answering. |
| **Non-prod (HI)** | aip-nprd-ge / `thai-citizen-app_1791807878985` (us) | What the customer sees. **Thai builds only**, display names without "(TH)". Published + shared with all users. Triggers are manual until MCPs are connected (`manual_triggers` in `configs/non-prod.json`). No API card answering (tested 14 Oct, session 8867930253280610994). Google says preview access is unlikely there. |

**Repo:**
```
agents/<persona>/<en|th>/<agent>.json     the agent (template with {{PLACEHOLDERS}})
configs/*.json                            one per target app (project, app, connector IDs, per-agent vars)
deploy.py                                 create/update/publish/share, by display name; can create the app
tools/translate.py                        en -> th template + meaning check
tests/harness.py, tests/cases/*.json      end-to-end API tests (yash-test)
tests/fixtures/<persona>.py               synthetic test data in the tester's Drive
```

## 3. Workflow design rules

### Triggers
- **Exactly one trigger per workflow.** Two triggers save fine, but every run fails (Vishal #220–#224). Two different starts means two workflows.
- **Schedule triggers need a `scheduleId`** (upper-case UUID). `deploy.py` adds and keeps it.
- **A scheduled workflow can also be started by hand.** Its first step then sees the typed text. Give the schedule a marker query so the step can tell them apart. A blank or marker query must still read as a request (see "launch messages" below).
- **Schedules are defaults.** Each user can change them on a shared workflow.
- **Polling schedules pile up runs.** A new scheduled run starts even while an earlier run waits at a card. So each event (file, letter, edit) must belong to exactly one run **by time slot** (e.g. "files modified in the previous 30-min slot"). A "busy" marker doesn't work. Tested 13 Oct.

### Starting from chat (manual triggers): what the user must do
Tested 14 Oct in yash-test. Full table with sessions: `mdes-work-log/CHAT_WORKFLOW_BEHAVIOUR_14Oct.md`.
- The user must **select the agent with `@`** (the chip).
- Any real request starts the run, in Thai, English or question form, and the **first step receives the full text**.
- **A bare word, a topic only or a greeting is silently dropped** (`NON_ASSIST_SEEKING_QUERY_IGNORED`): no run and no reply. Examples: "start", "PM2.5 เชียงราย", "สวัสดี". Tell users in the agent description to write a full sentence. "start the workflow" and "เริ่ม" work.
- The manual trigger's input field stayed empty in API runs. **Read the request from the chat message in the first step**, not from the input field.

### While a run waits at a card
- **Only the card moves the run on.** Typed text does not approve:
  - a short reply is ignored;
  - a **question typed with the agent chip still selected cancels the whole run**, silently;
  - without the chip, the question is answered as normal chat and the run stays paused.
- **After a page reload the chip is gone.** A card click is then handled as chat and the run does not resume, until the user re-selects `@agent` (Vishal #263, reproduced 14 Oct).
- Put one line on every approval card: "press the button below; don't type here. If the button doesn't respond, select @<agent> again."
- **Chat-started runs are cut at about 16–17 min** (#266), and their cards don't appear in the Inbox (#274). Long research waits need a "come back and press Approve" card.

### Steps
- **Data steps return data (output schema) and never talk to the user. Message steps return text.** A data step that writes prose makes the platform pause the run waiting for a reply (#183, #187).
- **Each step gets only the connectors it needs.** Both `dataStoreSpecs` and `connectorToolSelections` must be set, or scheduled runs get no tools (#177, #196).
- **`mutateEnabled` only on write steps.**
- **Name the exact tools** in the instruction ("Sheets MCP: append_rows").
- **Check every write** with a Condition on `created`/`success` before later steps rely on it. A cancelled card ends the run, so end with a clear message.
- **No Request-info card right after a Condition.** Answering it re-runs the earlier step and can loop (#181).
- **Never write a literal `${`** in instruction text. Every `${…}` is parsed as a variable (#180). Don't put `${…}` inside URLs either (#278).
- **Find files by name with the name start-anchored and the folder scoped**, or last month's files get picked up (#188).
- **One run per period:** a work note records what was done; a second run stops and links it.
- **Never ask the model to delete anything.** The MCPs have no delete tools by design.

### Writes and approval cards: the one rule every write step carries
The platform turns every write/send/update tool call into a confirmation card **by itself**. But models sometimes decide to ask "please confirm…" in chat text instead of calling the tool. Then:
- no card appears;
- the step pauses waiting for typed text;
- typing "yes" doesn't help (see above).

We saw this 3 times (GOV-B plan, RES-B chart, RES-B log: model thoughts "Seeking Row Confirmation", and no tool call reached the server). Every write step ends with:

> How writes work here: the platform shows every write, send or update to the user as a confirmation card by itself. Call the tool directly with the final values. Never ask the user in text first and never wait for a typed 'yes'. If the platform says the action was confirmed but you got no result, call the same tool once more with exactly the same values. If it is cancelled or fails, stop and return your output fields with the success field false and the reason in problems.

**Don't** write "write tools ask the user to confirm": models read it as "I should ask". Stress test 14 Oct: 8/8 runs produced the card (EN on gemini-3.1-pro-preview, TH on gemini-3.8-flash).

## 4. Connectors (MCP)

- **Custom MCP connectors only.** Never attach native GE connectors (Drive, Gmail, Outlook, OneDrive…), even if they exist in the project.
- **Use the newest set**, built by Kenil to mirror the native connectors:
  - Google: `mdesx-drive`, `mdesx-gmail`, `mdesx-calendar`, `mdesx-docs`, `mdesx-sheets`, `mdesx-slides` (13 Oct);
  - Microsoft: `mdesm-outlook-mail`, `mdesm-outlook-calendar`, `mdesm-outlook-contacts`, `mdesm-onedrive`, `mdesm-excel` (14 Oct);
  - Research + Analysis: the 5 Oct ones (no newer version).
- **Every user signs in to each connector once** (OAuth per connector, not per app). New scopes or new connectors need a new sign-in.
- **Tool names changed in mdesx:**

  | Old | New |
  |---|---|
  | `send_email` | `send_message` |
  | `read_file_text` | `read_file_content` |
  | `create_file_if_absent` | `search_files`, then `create_file` |
  | `insert_sheets_chart` | gone (`tools/port_mdesx.py` has the port) |
- **Folders:** Drive `create_file` takes `parentId`. Slides `create_presentation_from_outline` and Sheets `create_spreadsheet` don't yet, so **create, then move with Drive `update_file`** (fileId + parentId). Proven 14 Oct: deck in the right folder, 9 Thai slides.
- **Charts in Docs:** no tool. The chapter links to the chart in its Sheet (RES-B).
- **Open blocker (14 Oct):** `mdesx-drive read_file_content` returns PDFs and Excel files as raw attachments, not text, and the model can't read them (sessions 321064768433671759, 7930748337049178169). Agents reading PDFs or XLSX (GOV-A, GOV-C, EXE-A) are blocked until Kenil changes it.
- **Ask Kenil for changes only when the tools truly can't do it.** Show the evidence and try the workaround first.
- Prakhar (Google) advises keeping connectors per app lean, ideally fewer than 4. We have 13 in the test app; watch tool-selection quality.
- MCP tool calls time out at 300 s, with up to 3 retries (Google, 13 Oct).

## 5. Thai

- Each agent has an `en` build and a `th` build. **Thai builds are Thai-only**: instructions, step names, cards, descriptions and every output, with no English glosses. Non-prod gets Thai only.
- **Field names that other steps reference stay English.** A Thai name in `${…}`, a condition or a loop variable is rejected at publish ("Invalid format for variable"). Create/PATCH don't check, so an unpublished draft fails only at run time. Thai names are fine for fields nothing references.
- Keep tool names, status values (`done`, `missing`, `approved`…), quoted literals and `{{PLACEHOLDERS}}` untranslated. `tools/translate.py` protects them, then back-translates every instruction and flags meaning changes.
- **No gendered particles** (ครับ/ค่ะ) anywhere. Models still slip, especially in EXE emails.
- The model's thinking and the platform's run summary stay English. We can't change that.
- **Machine-checked Thai is not reviewed Thai.** A native reviewer must read every Thai build before go-live.

## 6. Build → deploy → test loop

1. Write the en template (`agents/<persona>/en/<agent>.json`).
   - Use `{{DRIVE_MCP}}` / `{{DRIVE_MCP_STORE}}` etc. for connectors.
   - Use `{{VARS}}` for anything environment-specific.
2. `python3 tools/translate.py agents/<persona>/en/<agent>.json` → th template + review. Read the flagged items.
3. `python3 deploy.py --config configs/yash-test.json --only <ID> --dry-run`, then deploy. Drafts are enough for API tests (API runs use the draft).
4. Fixtures: add a builder in `tests/fixtures/<persona>.py`.
   - Realistic synthetic data in the tester's Drive.
   - **No "TEST" markers**, because agents refuse or copy them.
   - All emails `navya.agarwal+<role>@devxlabs.ai`.
   - Archive old outputs instead of deleting them.
5. Cases: at least the happy path plus 1–2 failure paths, per language (`tests/cases/<id>-<lang>-<what>.json`). Run them with `python3 tests/harness.py <case>`.
   - The harness answers cards per the case.
   - It refuses mail or invites to any address outside the allow-list.
   - It checks status, cards, created files (content, Thai share) and recipients.
6. **Verify the outputs yourself.** A green status isn't proof: open the deck, read the numbers.
7. Fix a failure in **both** en and th, redeploy, re-run. Write down what changed and why.
8. Deploy to non-prod with `configs/non-prod.json` (Thai only; publish + share).
9. Commit as yourself (no tool co-author) on `dev`, then fast-forward `main`.

## 7. Platform behaviour to expect

- Agent creation is limited per project per day (Vishal saw 429s at 7–8 creates). We did 30+ in yash-test on 14 Oct without hitting it. **Reuse agents by display name.**
- One-off platform errors happen; re-run once before debugging:
  - "Severe loop detected" (RES-B, GOV-A);
  - "Unhandled model error code 3" (EXE-B);
  - a connector auth drop mid-run (GOV-B).
- A **gcloud login expires** periodically and kills long scripts. `gcloud auth login <user>` again.
- To share an agent:
  1. publish;
  2. set sharing `ALL_USERS`;
  3. `requestAgentReview` (private agents only; needs `discoveryengine.agents.requestReview`, granted on non-prod 14 Oct);
  4. set `ALL_USERS` again.

  `deploy.py` does all of this.
- Publishing a scheduled workflow turns its schedule on. Use manual triggers if it must be visible but not run.

## 8. Checklist for a new agent

- [ ] One job, one trigger. Schedule or manual decided, and why.
- [ ] Nothing user-specific built in. Finds inputs by name; clear "missing" message.
- [ ] Data steps vs message steps separated. Every write checked.
- [ ] Only the needed connectors per step; `mutateEnabled` only on writes; tools named.
- [ ] Every write step carries the write rule (section 3).
- [ ] Approval cards say "press the button; re-select @agent if it doesn't respond".
- [ ] Description tells users to write a full request.
- [ ] Thai build made, reviewed (machine + native), no particles.
- [ ] Fixtures + happy path + failure cases pass in yash-test, outputs read by a human.
- [ ] Deployed to non-prod in Thai, published and shared.
