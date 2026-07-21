#!/usr/bin/env python3
"""Scan Claude Code transcripts for moments where Lex corrected/redirected the
agent. Emits candidate windows as JSONL on stdout for /sonoflex-learn to judge.

Wide net on purpose: recall over precision. The agent reading the candidates is
the precision filter. This only surfaces "Lex pushed back here, look."

Usage:
  scan.py [--since EPOCH] [--projects DIR] [--max-user-chars N]
"""
import sys, os, json, glob, argparse, re

PROJECTS = os.path.expanduser("~/.claude/projects")

# System-injected user turns that are never Lex typing.
SKIP_PREFIX = ("<task-notification>", "<system-reminder>", "<command-name>",
               "<command-message>", "<local-command", "<bash-input>",
               "<bash-stdout>", "<bash-stderr>", "caveat:", "<user-memory")

# Pure approvals / non-corrections: if the whole message is one of these, drop.
APPROVAL = {"oui", "ok", "okay", "yes", "go", "yep", "yed", "yup", "vas-y",
            "vasy", "continue", "next", "suivant", "merci", "thanks", "nice",
            "cool", "parfait", "top", "good", "gg", "bien", "ok go", "do it"}

# Correction signal. Two tiers: LEADING (message starts with it) and ANYWHERE.
LEAD = ("non", "nan", "no ", "nope", "stop", "attends", "arrete", "arrête",
        "annule", "revert", "undo", "rollback", "recommence", "wait", "wtf",
        "euh non", "ah non", "bah non", "mais non", "nah")
ANY = ("fait pas", "fais pas", "faut pas", "c'est pas", "cest pas", "pas comme ça",
       "pas comme ca", "pas ce que", "pas ce quon", "t'as oublié", "tas oublie",
       "tu as oublié", "oublie pas", "j'ai pas demandé", "jai pas demande",
       "je t'ai pas demandé", "on avait dit", "on a dit", "je t'avais dit",
       "pourquoi t'as", "pourquoi tu", "au lieu de", "plutôt", "plutot",
       "en fait non", "pas besoin", "n'importe quoi", "nimporte quoi",
       "marche pas", "marche toujours pas", "toujours pas", "relis",
       "you forgot", "not what", "that's wrong", "thats wrong", "not like that",
       "i didn't ask", "i didnt ask", "we said", "instead of", "why did you",
       "why'd you", "that's not", "thats not", "don't do", "dont do",
       "c'est faux", "cest faux", "faux", "mauvais", "t'es sûr", "tes sur",
       "fait pas semblant", "sur-", "trop de", "trop long")

def norm(s): return re.sub(r"\s+", " ", s).strip()

def user_text(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = [b.get("text", "") for b in c
                 if isinstance(b, dict) and b.get("type") == "text"]
        # a list carrying a tool_result is a tool turn, not Lex typing
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        return "\n".join(p for p in parts if p) or None
    return None

def asst_text(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""

def is_correction(t):
    low = t.strip().lower()
    if low in APPROVAL or len(low) < 2:
        return False
    if low.startswith(("http://", "https://", "www.")):
        return False
    if any(low.startswith(p) for p in LEAD):
        return True
    return any(k in low for k in ANY)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=float, default=0.0, help="epoch; only turns at/after")
    ap.add_argument("--projects", default=PROJECTS)
    ap.add_argument("--max-user-chars", type=int, default=800)
    ap.add_argument("--max-asst-chars", type=int, default=700)
    a = ap.parse_args()

    files = glob.glob(os.path.join(a.projects, "**", "*.jsonl"), recursive=True)
    n_files = n_cand = 0
    for f in files:
        try:
            if a.since and os.path.getmtime(f) < a.since:
                continue
        except OSError:
            continue
        n_files += 1
        last_asst = ""
        last_asst_ts = ""
        try:
            fh = open(f, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = o.get("type")
                if t == "assistant":
                    txt = asst_text(o.get("message", {}))
                    if txt:
                        last_asst = txt
                        last_asst_ts = o.get("timestamp", "")
                    continue
                if t != "user":
                    continue
                if o.get("isMeta") or o.get("isSidechain"):
                    continue
                if a.since:
                    # timestamps are ISO; fall back to file mtime already filtered
                    pass
                txt = user_text(o.get("message", {}))
                if not txt:
                    continue
                low = txt.strip().lower()
                if any(low.startswith(p) for p in SKIP_PREFIX):
                    continue
                if not is_correction(txt):
                    continue
                n_cand += 1
                out = {
                    "session": os.path.basename(f),
                    "project": os.path.basename(os.path.dirname(f)),
                    "ts": o.get("timestamp", ""),
                    "cwd": o.get("cwd", ""),
                    "branch": o.get("gitBranch", ""),
                    "prev_assistant": norm(last_asst)[-a.max_asst_chars:],
                    "user": norm(txt)[:a.max_user_chars],
                }
                sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stderr.write(f"scanned {n_files} files, {n_cand} correction candidates\n")

if __name__ == "__main__":
    main()
