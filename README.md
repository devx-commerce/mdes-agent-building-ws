# mdes-agent-building-ws

The MDES WS4 agents (Gemini Enterprise workflows) as JSON, and one command that deploys them to any app.

## Deploy
```bash
python3 deploy.py --dry-run                 # fill and check every template; no API calls
python3 deploy.py                           # deploy every enabled agent, en + th
python3 deploy.py --only GOV-A,EXE-B        # some agents
python3 deploy.py --lang th                 # one language
python3 deploy.py --check                   # what differs from the app; changes nothing
python3 deploy.py --config configs/x.json   # another target
```
Needs `gcloud auth login <user>` for the config's user. No other dependencies.

Per agent, it backs up the live one to `backups/`, creates or updates it by display name, reads it back and compares,
then publishes and shares if the config says so.

## Config (`deploy.config.json`)
| Key | Meaning |
|---|---|
| `app` | The app (engine ID) to deploy on |
| `create_app` | `true`: create the app if it does not exist, with the connectors attached |
| `langs` | `["en", "th"]` |
| `publish` | `false`: drafts only. `true`: publish after deploy |
| `share` | `PRIVATE` or `ALL_USERS` |
| `connectors` | Kenil's MCP connector IDs (`{{DRIVE_MCP}}` etc. in the templates) |
| `agents.<ID>` | `enabled`, `langs`, `app` (other app for this agent), `cron`, `display_name: {en, th}`, `vars` / `vars_en` / `vars_th` |

The EXE agents need their Drive folder IDs (`EXE_A_FOLDER_ID` etc.) in `vars_en` / `vars_th`.

## Agents
| ID | Persona | Agent | Start | en | th |
|---|---|---|---|---|---|
| GOV-A | government-officer | Monthly Operations Report | daily 08:00 | ✓ | — |
| GOV-B | government-officer | Policy Briefing Memo | by hand | ✓ | — |
| GOV-C | government-officer | Incoming Letters | hourly | ✓ | — |
| RES-A | researcher | Evidence Review | hourly 07:00–18:00 | ✓ | — |
| RES-B | researcher | Survey Analysis | every 30 min 08:00–20:00 | ✓ | — |
| RES-C | researcher | Funding Calls | daily 07:00 | ✓ | — |
| EXE-A | executive | Peer Benchmark Pack | weekdays 09:00 | ✓ | ✓ |
| EXE-B | executive | Decision Brief Tracker | 1st of month 09:00 | ✓ | ✓ |
| EXE-C | executive | Meeting Prep & Actions | daily 06:00 | ✓ | ✓ |

Times are Asia/Bangkok. TCH-A is not built.

`en` = English instructions. The GOV/RES `en` agents already write their messages and documents in Thai, some with English added.
`th` = instructions translated to Thai; field names Thai only where no other step refers to them (the platform rejects Thai names in `${...}` references).

## Where each JSON came from (13 Oct 2026)
| Agents | Source |
|---|---|
| GOV-A/B/C, RES-A/B/C | `devx-commerce/mdes-agent` @ `12b22d7` (Vishal), `workflows-user/*/build_*.py` run with production settings. The committed JSONs equal the live drafts in thai-gov-poc, but GOV-A, GOV-C, RES-B and RES-C were in test mode (manual start or a one-off cron); only the trigger and the first step's time-slot rule differ. |
| EXE-A/B/C en | `mdes-work-log/wf/specs/exe_*.py` (Navya). Equal to the live drafts in `mdes-executive-agents` except the test cron. |
| EXE-A/B/C th | `wf/lens.py build` from the same specs. Newer than the live `(TH)` drafts. |

## Not done / untested
- Thai versions of GOV and RES do not exist yet.
- `create_app` and deploying into a new app have not been run yet. `--dry-run` and `--check` were run against thai-gov-poc on 13 Oct.
- The new Thai EXE builds have not been run on the platform.
