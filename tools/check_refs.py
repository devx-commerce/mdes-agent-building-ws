"""Check that every ${step.field...} in a template points at an existing step and a top-level output field it declares."""
import json, re, sys
def nodes(flow):
    for n in flow.get("nodes", []):
        yield n
        if "forLoopNode" in n:
            yield from nodes(n["forLoopNode"]["subAgentFlow"])
for path in sys.argv[1:]:
    t = json.load(open(path)); flow = t["definition"]["agentFlow"]
    out = {n["id"]: set(n.get("outputSchema", {}).get("properties", {})) for n in nodes(flow)}
    loops = {n["id"] for n in nodes(flow) if n["nodeType"] == "FOR_LOOP_NODE"}
    triggers = {n["id"]: n["forLoopNode"]["currentItemVariable"] for n in nodes(flow) if n["nodeType"] == "FOR_LOOP_NODE"}
    bad = set()
    for n in nodes(flow):
        s = json.dumps(n, ensure_ascii=False)
        for ref in re.findall(r"\$\{([^}]+)\}", s):
            head, *rest = ref.split(".")
            if head not in out:
                bad.add((n["id"], ref, "no such step")); continue
            if head in loops or not rest or n.get("nodeType") == "FOR_LOOP_NODE":
                continue
            f = re.sub(r"\[.*", "", rest[0])
            if head.endswith("_start") or head == "start":
                continue
            if out[head] and f not in out[head] and head not in ("manual_trigger",):
                bad.add((n["id"], ref, "no such field"))
    ids = [n["id"] for n in flow["nodes"]]
    dangling = [e for e in flow["edges"] if e["sourceNodeId"] not in ids or e["targetNodeId"] not in ids]
    print(path.split("/")[-2] + "/" + path.split("/")[-1], "bad refs:", sorted(bad) or "none", "| dangling edges:", dangling or "none")
