#!/usr/bin/env python3
"""Deploy the MDES agents (agents/<persona>/<lang>/*.json) to a Gemini Enterprise app, in one command.

  python3 deploy.py                              every enabled agent, every language in the config
  python3 deploy.py --only GOV-A,EXE-B           just these agents
  python3 deploy.py --lang th                    just one language
  python3 deploy.py --config configs/<x>.json    another target (default: deploy.config.json)
  python3 deploy.py --dry-run                    fill the templates and check them; no API calls
  python3 deploy.py --check                      compare with what is in the app; changes nothing

For each agent: back up the live one (backups/), create or update it by display name, read it back and compare,
then publish and share as the config says. If the app does not exist and "create_app" is true, it is created first
with the config's connectors attached.
Uses the undocumented v1alpha agents API (workflowAgentDefinition, :publish), always as the config's user."""
import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parent
DROP = {"name", "createTime", "updateTime", "owner", "scheduleId"}  # set by the platform: ignored in comparisons


# ---------- config and templates ----------
def load_config(path):
    cfg = json.loads((ROOT / path).read_text())
    for k in ("user", "project", "project_number", "location", "app", "connectors", "agents"):
        if k not in cfg:
            sys.exit(f"config {path}: '{k}' is missing")
    return cfg


def templates(cfg, only, langs):
    out = []
    for p in sorted((ROOT / "agents").glob("*/*/*.json")):
        t = json.loads(p.read_text())
        a = cfg["agents"].get(t["id"], {})
        if only and t["id"] not in only:
            continue
        if not only and not a.get("enabled", True):
            continue
        if t["lang"] not in (langs or a.get("langs") or cfg.get("langs", ["en", "th"])):
            continue
        out.append((p, t, a))
    return out


def render(cfg, t, a):
    """Fill {{PLACEHOLDERS}}: project, connectors (+ their _STORE data stores), then the agent's own vars."""
    values = {"PROJECT_NUMBER": cfg["project_number"], "LOCATION": cfg["location"]}
    for k, v in cfg["connectors"].items():
        values[k] = v
        values[k + "_STORE"] = v + "_mcp_data" if v else ""
    values.update(a.get("vars", {}))
    values.update(a.get("vars_" + t["lang"], {}))  # e.g. vars_th: a different test folder for the Thai copy
    s = json.dumps(t["definition"], ensure_ascii=False)
    missing = sorted({m for m in re.findall(r"\{\{(\w+)\}\}", s) if not values.get(m)})
    if missing:
        return None, missing
    for k, v in values.items():
        s = s.replace("{{" + k + "}}", v)
    d = json.loads(s)
    trig = d["agentFlow"]["nodes"][0]
    sch = trig.get("scheduleTrigger", {}).get("schedule")
    if sch is not None:
        if a.get("cron"):
            sch["cronTab"] = a["cron"]
        if cfg.get("timezone"):
            sch["timeZone"] = cfg["timezone"]
    return d, []


def display_name(t, a):
    return a.get("display_name", {}).get(t["lang"]) or t["display_name"]


# ---------- API ----------
class Api:
    def __init__(self, cfg):
        self.cfg = cfg
        host = "discoveryengine.googleapis.com" if cfg["location"] == "global" else f"{cfg['location']}-discoveryengine.googleapis.com"
        self.coll = f"https://{host}/v1alpha/projects/{cfg['project_number']}/locations/{cfg['location']}/collections/default_collection"
        self._token = None

    def token(self):
        if not self._token:
            self._token = subprocess.check_output(["gcloud", "auth", "print-access-token", self.cfg["user"]], text=True).strip()
        return self._token

    def whoami(self):
        with urllib.request.urlopen(f"https://oauth2.googleapis.com/tokeninfo?access_token={self.token()}") as r:
            email = json.loads(r.read()).get("email")
        if email != self.cfg["user"]:
            sys.exit(f"STOP: token is for {email}, config user is {self.cfg['user']}")
        print("calling as", email, "| project", self.cfg["project"], "| app", self.cfg["app"])

    def call(self, method, url, body=None, ok404=False):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token()}", "X-Goog-User-Project": self.cfg["project"], "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if ok404 and e.code == 404:
                return None
            sys.exit(f"HTTP {e.code} {method} {url}\n{e.read().decode()[:2000]}")

    def engine(self, app):
        return f"{self.coll}/engines/{app}"

    def agents_url(self, app):
        return f"{self.engine(app)}/assistants/default_assistant/agents"


def ensure_app(api, cfg, app, dry):
    """The app must exist; create it (copying the shape of the MDES apps, 13 Oct 2026) when create_app is true."""
    stores = [v + "_mcp_data" for v in cfg["connectors"].values() if v]
    eng = api.call("GET", api.engine(app), ok404=True)
    if eng is None:
        if not cfg.get("create_app"):
            sys.exit(f"app '{app}' does not exist in {cfg['project']}. Set \"create_app\": true in the config to create it.")
        if dry:
            print(f"would create app '{app}' with {len(stores)} connectors")
            return
        body = {"displayName": cfg.get("app_display_name", app), "dataStoreIds": stores, "solutionType": "SOLUTION_TYPE_SEARCH",
                "searchEngineConfig": {"searchTier": "SEARCH_TIER_ENTERPRISE", "searchAddOns": ["SEARCH_ADD_ON_LLM"]},
                "industryVertical": "GENERIC", "appType": "APP_TYPE_INTRANET",
                "features": {"workflow-agents": "FEATURE_STATE_ON", "agent-sharing-without-admin-approval": "FEATURE_STATE_ON"},
                "observabilityConfig": {"observabilityEnabled": True}}
        api.call("POST", f"{api.coll}/engines?engineId={app}", body)
        print(f"created app '{app}' (creation can take a few minutes; run deploy again if the next step fails)")
        return
    have = set(eng.get("dataStoreIds", []))
    add = [s for s in stores if s not in have]
    if add and not dry:
        api.call("PATCH", api.engine(app) + "?updateMask=dataStoreIds", {"dataStoreIds": sorted(have) + add})
        print(f"attached connectors to '{app}':", ", ".join(add))


# ---------- compare ----------
def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in DROP}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


def diff(a, b, path="", out=None):
    out = [] if out is None else out
    if type(a) != type(b):
        out.append(path or "/")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}")
            else:
                diff(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path} (length {len(a)} vs {len(b)})")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(path)
    return out


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="deploy.config.json")
    ap.add_argument("--only", default="", help="comma-separated agent IDs, e.g. GOV-A,EXE-B")
    ap.add_argument("--lang", default="", help="en or th")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    only = {x.strip().upper() for x in args.only.split(",") if x.strip()}
    todo = templates(cfg, only, [args.lang] if args.lang else None)
    if not todo:
        sys.exit("nothing to deploy (check --only / --lang / 'enabled' in the config)")

    rendered, bad = [], 0
    for p, t, a in todo:
        d, missing = render(cfg, t, a)
        if missing:
            bad += 1
            print(f"✗ {t['id']} {t['lang']}: no value for {', '.join(missing)} (set in the config: connectors, or agents.{t['id']}.vars / vars_{t['lang']})")
        else:
            rendered.append((p, t, a, d))
    if bad:
        sys.exit(f"{bad} template(s) not filled: nothing deployed")
    if args.dry_run:
        for p, t, a, d in rendered:
            sch = d["agentFlow"]["nodes"][0].get("scheduleTrigger", {}).get("schedule", {})
            print(f"ok  {t['id']:6} {t['lang']}  {display_name(t, a):32} -> {a.get('app', cfg['app'])}  "
                  f"{len(d['agentFlow']['nodes'])} steps  {sch.get('cronTab', 'manual')}")
        return

    api = Api(cfg)
    api.whoami()
    for app in sorted({a.get("app", cfg["app"]) for _, _, a, _ in rendered}):
        ensure_app(api, cfg, app, args.check)
    live = {}
    backups = ROOT / "backups"
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    publish, share = cfg.get("publish", False), cfg.get("share", "PRIVATE")
    for p, t, a, want in rendered:
        app, name = a.get("app", cfg["app"]), display_name(t, a)
        base = api.agents_url(app)
        if app not in live:
            live[app] = {x["displayName"]: x["name"].split("/")[-1] for x in (api.call("GET", base + "?pageSize=200") or {}).get("agents", [])}
        aid = live[app].get(name)
        label = f"{t['id']:6} {t['lang']}  {name[:40]:40}"
        cur = api.call("GET", f"{base}/{aid}") if aid else None
        if args.check:
            d = diff(strip(want), strip(cur["workflowAgentDefinition"])) if cur else ["(not in app)"]
            print(f"{label} {'same' if not d else f'{len(d)} difference(s): ' + ', '.join(d[:4])}")
            continue
        sch = want["agentFlow"]["nodes"][0].get("scheduleTrigger", {}).get("schedule")
        if sch is not None:  # the editor needs a schedule ID ("Needs info" without one); keep the live one if there is one
            old = (cur or {}).get("workflowAgentDefinition", {}).get("agentFlow", {}).get("nodes", [{}])[0]
            sch["scheduleId"] = old.get("scheduleTrigger", {}).get("schedule", {}).get("scheduleId") or str(uuid.uuid4()).upper()
        if cur:
            backups.mkdir(exist_ok=True)
            (backups / f"{app}-{aid}-{stamp}.json").write_text(json.dumps(cur, ensure_ascii=False, indent=1))
            if not diff(strip(want), strip(cur["workflowAgentDefinition"])) and not publish:
                print(f"{label} unchanged  id={aid}")
                continue
            api.call("PATCH", f"{base}/{aid}?updateMask=description,workflowAgentDefinition",
                     {"description": t["description"], "workflowAgentDefinition": want})
            what = "updated"
        else:
            aid = api.call("POST", base, {"displayName": name, "description": t["description"], "workflowAgentDefinition": want})["name"].split("/")[-1]
            what = "created"
        after = diff(strip(want), strip(api.call("GET", f"{base}/{aid}")["workflowAgentDefinition"]))
        if after:
            print(f"{label} ⚠ {what}, but {len(after)} difference(s) on read-back: {', '.join(after[:4])}  id={aid}")
            continue
        if publish:
            api.call("POST", f"{base}/{aid}:publish", {})
            what += ", published"
        if share != "PRIVATE":
            api.call("PATCH", f"{base}/{aid}?updateMask=sharingConfig", {"sharingConfig": {"scope": share}})
            what += f", shared {share}"
        print(f"{label} {what}  id={aid}")
    if not args.check and not publish:
        print("\nDrafts only (publish: false). Publish in the editor, or set \"publish\": true and run again.")


if __name__ == "__main__":
    main()
