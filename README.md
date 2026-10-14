# mdes-agent-building-ws

This repo holds the MDES WS4 agents (Gemini Enterprise Workflow Builder agents) as JSON, in English and Thai. It also has one command that sets them up in **any app in any project**, from scratch, and a test harness that runs them end to end through the API.

## Layout
```
agents/<persona>/<lang>/<agent>.json    templates: {id, persona, lang, display_name, description, definition{agentFlow}}
                                        {{PROJECT_NUMBER}} {{LOCATION}} {{DRIVE_MCP}} {{DRIVE_MCP_STORE}} ... filled at deploy
agents/<persona>/th/<agent>.review.json translation review: English | Thai | Thai back to English | meaning check
configs/*.json                          deploy targets (project, app, connector IDs, per-agent vars)
deploy.py                               deploy / check / create the app
tools/translate.py                      en template -> th template (Gemini on Vertex, protected tokens, meaning check)
tests/harness.py                        run a case through the API, answer cards, check files / cards / Thai
tests/cases/*.json                      test cases (happy path + basic failure paths per agent and language)
tests/fixtures/<persona>.py             builds the synthetic test data in the tester's Google Drive
tests/FINDINGS-<persona>.md             latest test results with evidence
docs/AGENT-BUILDING-GUIDE.md            what we learned: read before building a new agent
```

## Agents
| ID | Persona | Agent | Start (Asia/Bangkok) |
|---|---|---|---|
| GOV-A | government-officer | Monthly Operations Report | daily 08:00 |
| GOV-B | government-officer | Policy Briefing Memo | by hand (typed request) |
| GOV-C | government-officer | Incoming Letters | hourly |
| RES-A | researcher | Evidence Review | hourly 07:00–18:00 |
| RES-B | researcher | Survey Analysis | every 30 min 08:00–20:00 |
| RES-C | researcher | Funding Calls | daily 07:00 |
| EXE-A | executive | Peer Benchmark Pack | weekdays 09:00 |
| EXE-B | executive | Decision Brief Tracker | 1st of month 09:00 (or typed goal) |
| EXE-C | executive | Meeting Prep & Actions | daily 06:00 |

Every agent has an `en` build and a `th` build. The `th` display name ends in "(TH)". TCH-A is not built.

- **th** is the Thai-native experience. Its instructions, step names, cards and descriptions are in Thai, and every message, email and document is Thai only. Some things stay English: the field names that steps pass to each other (the platform rejects Thai names in `${...}` references), tool names and status codes.
- **en** has English instructions. The GOV/RES `en` builds answer bilingually (Thai first, then English) for English-speaking reviewers.

## Deploy
```bash
python3 deploy.py --config configs/yash-test.json --dry-run     # fill and check every template; no API calls
python3 deploy.py --config configs/yash-test.json               # create/update every agent (drafts unless "publish": true)
python3 deploy.py --config configs/yash-test.json --only GOV-A,EXE-B --lang th
python3 deploy.py --config configs/yash-test.json --check       # what differs from the app; changes nothing
```
Before you run it, sign in with `gcloud auth login <user>` as the config's `user`. That user needs a Gemini Enterprise licence in the project. The script needs only the Python 3 standard library.

For each agent, the script:
1. backs up the live version to `backups/`;
2. creates or updates the agent, matching it by display name;
3. reads it back and compares it with the template;
4. publishes and shares it, if the config says so.

**New app from scratch:** set `"create_app": true` and a new `app` ID. The script creates the app with all the config's connectors attached, then deploys the agents. Proven on 14 Oct with `configs/yash-test-scratch.json`: the new app was created, an agent was deployed, and its test case passed in 3.2 min.

### Config keys
| Key | Meaning |
|---|---|
| `user`, `project`, `project_number`, `location`, `app` | The target |
| `create_app`, `app_display_name` | Create the app if it is missing |
| `langs` | `["en","th"]` |
| `publish` / `share` | `false` deploys drafts only (API test runs use the draft). `share` is `PRIVATE` or `ALL_USERS` |
| `connectors` | MCP connector IDs in that project: DRIVE, GMAIL, CALENDAR, DOCS, SHEETS, SLIDES, RESEARCH, ANALYSIS |
| `drop_missing_connectors` | `true` deploys steps without any connector whose ID is empty, for a project where the connectors don't exist yet |
| `agents.<ID>` | `enabled`, `langs`, `app`, `cron`, `display_name {en,th}`, `vars` / `vars_en` / `vars_th` (EXE folder IDs) |

### Targets
| Config | Project / app | Use |
|---|---|---|
| `configs/yash-test.json` | yash-test-495112 / `mdes-executive-app_1791205779351` (global) | Testing. Cards can be answered through the API here (EAP), so `tests/harness.py` can run every path. |
| `configs/yash-test-scratch.json` | yash-test-495112 / `mdes-ws4-scratch-app` | Proof of the from-scratch path |
| `deploy.config.json` | thai-gov-poc / `mdes-agents` (us) | Internal review environment |
| `configs/non-prod.json` | aip-nprd-ge / `thai-citizen-app_1791807878985` (us) | HI non-prod, Thai builds only. No MCP connectors exist there yet, so the steps are deployed without them and cannot run. Once Kenil's servers exist in non-prod (`aip-nprd-agent-mcp`), fill in `connectors` and redeploy. |

## Thai builds
```bash
python3 tools/translate.py agents/government-officer/en/incoming-letters.json   # writes th/ + review
python3 tools/translate.py --check agents/researcher/th/funding-calls.json      # meaning check only
```
These are never translated: `${refs}`, `{{PLACEHOLDERS}}`, URLs, emails, long IDs, snake_case and camelCase names, `word:` and `word=` assignments, quoted strings, and status values.

After translating, the script checks:
- the meaning of every instruction and card, by back-translating it;
- that every Thai literal and protected token in the English is still there;
- that there are no gendered particles (ครับ/ค่ะ).

A native Thai reviewer must still read the Thai before go-live.

The EXE `th` builds were made with `mdes-work-log/wf/lens.py`. They use Thai field names where no other step refers to the field.

## Tests
```bash
python3 tests/harness.py tests/cases/gov-b-th-plan-rejected.json   # one case
python3 tests/harness.py --all --lang th                           # every Thai case
```
For each case, the harness:
- starts the draft through `streamAssist`;
- answers each card by the case's rules (`actionExecutionParams`), and refuses any send, draft or invite to an address outside the allow-list;
- checks the session status, the final answer, which cards appeared, the Drive files created (name, Thai share, content) and the email recipients.

Raw turns, cards and `result.json` go to `tests/results/`, which is git-ignored. Results and evidence are in `tests/FINDINGS-*.md`.

## Where the templates came from
| Agents | Source |
|---|---|
| GOV-A/B/C, RES-A/B/C en | `devx-commerce/mdes-agent` @ `12b22d7` (Vishal), `workflows-user/*/build_*.py` with production settings |
| GOV/RES th | `tools/translate.py` from the en templates (14 Oct) |
| EXE-A/B/C en + th | `mdes-work-log/wf/specs/exe_*.py` (Navya) and `wf/lens.py` |
