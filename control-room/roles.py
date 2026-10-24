"""Resolve configured team bindings from current pointers and succession records."""

from pathlib import Path
import re


UUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")


def lineage_records(directory):
    records = {}
    for index, path in enumerate(Path(directory).iterdir()):
        if index >= 4096:
            raise ValueError("Lineage directory exceeds 4096 entries")
        if not UUID.fullmatch(path.name):
            continue
        with path.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError(f"Oversized lineage record: {path}")
        text = raw.decode("utf-8").strip()
        fields = text.split("\t")
        if len(fields) != 2 or not fields[0].isdigit() or int(fields[0]) < 1 or not UUID.fullmatch(fields[1]):
            raise ValueError(f"Invalid lineage record: {path}")
        sid = path.name.upper()
        if sid in records:
            raise ValueError(f"Duplicate lineage record: {sid}")
        records[sid] = {"parent": fields[1].upper(), "generation": int(fields[0]),
                        "path": str(path), "line": 1, "quote": text}
    return records


def successor(session, records):
    evidence, seen = [], set()
    while True:
        if session in seen or len(seen) >= 128:
            raise ValueError("Cyclic or excessive succession chain")
        seen.add(session)
        children = [(sid, row) for sid, row in records.items() if row["parent"] == session]
        if len(children) > 1:
            raise ValueError(f"Ambiguous successors for session {session}")
        if not children:
            return session, evidence
        child, record = children[0]
        if session in records and record["generation"] != records[session]["generation"] + 1:
            raise ValueError(f"Invalid succession generation for {child}")
        evidence.append({key: record[key] for key in ("path", "line", "quote")})
        session = child


def resolve(config, sessions, sources):
    """Return endpoint aliases and evidence; never retain an unresolved old binding."""
    panes = {row["id"]: row for row in sessions if row["id"]}
    source_by_path = {row["path"]: row for row in sources}
    directories, resolutions = {}, []
    for row in sessions:
        row.update(roles=[], role="Unassigned", role_evidence=[])
    for anchor, assigned in config["roles"].items():
        assigned = [assigned] if isinstance(assigned, str) else assigned
        binding = config.get("role_bindings", {}).get(anchor, {})
        project = binding.get("project") or panes.get(anchor, {}).get("project", "Unassigned")
        result = {"anchor": anchor, "project": project, "roles": assigned,
                  "surface": "", "evidence": [], "error": ""}
        try:
            target = anchor
            if binding.get("pointer"):
                source = source_by_path.get(binding["pointer"])
                if not source or source["error"] or source["project"] != project:
                    raise ValueError("Role pointer source unavailable or outside the project")
                target = source["text"].strip().upper()
                if not UUID.fullmatch(target):
                    raise ValueError("Role pointer must contain one surface UUID")
                result["evidence"] = [{"path": source["path"], "line": 1, "quote": source["text"].strip()}]
            elif binding.get("session_id"):
                session = binding["session_id"].upper()
                if not UUID.fullmatch(session):
                    raise ValueError("Invalid bound session UUID")
                directory = binding.get("lineage_dir")
                if directory:
                    if directory not in directories:
                        try:
                            directories[directory] = lineage_records(directory)
                        except (OSError, ValueError) as exc:
                            directories[directory] = str(exc)
                    records = directories[directory]
                    if isinstance(records, str):
                        raise ValueError(records)
                    session, result["evidence"] = successor(session, records)
                matches = [row for row in panes.values() if row.get("session_id", "").upper() == session]
                if len(matches) != 1:
                    raise ValueError(f"Session {session} has no unique current pane")
                target = matches[0]["id"]
                result["session_id"] = session
            if target not in panes or panes[target]["project"] != project:
                raise ValueError("Bound pane unavailable or outside the project")
            result["surface"] = target
        except (OSError, ValueError) as exc:
            result["error"] = str(exc)
        resolutions.append(result)
    for project in {r["project"] for r in resolutions}:
        leads = [r for r in resolutions if r["project"] == project and "Lead" in r["roles"]]
        if len(leads) > 1:
            for result in leads:
                result.update(surface="", error="Multiple lead bindings for this project")
    for result in resolutions:
        if result["surface"]:
            row = panes[result["surface"]]
            row["roles"] = list(dict.fromkeys(row["roles"] + result["roles"]))
            row["role"] = " / ".join(row["roles"]) or "Unassigned"
            row["role_evidence"].append(result)
    return {r["anchor"]: r["surface"] for r in resolutions}, resolutions
