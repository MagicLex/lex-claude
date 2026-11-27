#!/usr/bin/env python3
"""PreToolUse hook on Agent: in a team repo, prepend the subagent brief verbatim.

The brief is team/TEAM.md's "Subagent brief" section plus the repo's
subagentBrief lines (.claude/team.json). A rule restated by each lane in each
brief gets paraphrased or dropped; this puts the one written copy at the top of
every subagent prompt. Outside team mode it does nothing. Fail-open: any error
leaves the call unchanged.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import team  # noqa: E402


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str):
        return
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    if not team.is_on(cwd):
        return
    rules = team.brief(cwd)
    if not rules or rules.splitlines()[0] in prompt:
        return
    updated = dict(tool_input, prompt=rules + "\n\n---\n\n" + prompt)
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        # Claude Code drops updatedInput without a decision (tested on 2.1.316).
        # "allow" adds no grant here: Agent needs no prompt in default mode, and
        # ask and deny rules still apply after a hook allow.
        "permissionDecision": "allow",
        "updatedInput": updated,
    }}, sys.stdout)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"subagent-brief: {e}", file=sys.stderr)
