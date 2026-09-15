#!/usr/bin/env bash
# master.sh — the drift authority. One job: interrogate a subject's self-report
# and rule whether it has actually loaded and internalised this identity + rules
# (phase=identity), or understood the project as briefed (phase=project).
#
# Not a daemon: a long-lived master would need its own supervisor (lifecycle
# rule). It is a neutral judge spawned on demand, LEX_CLAUDE_DISABLE=1 so the
# judge does NOT itself load the identity it is judging (no jeanjean-judges-
# jeanjean bias, cheaper, no hook noise).
#
#   master.sh verify --answer <file> --phase identity
#   master.sh verify --answer <file> --phase project --briefing <file>
#
# Ground truth: expected identity = basename of the ~/.claude/CLAUDE.md symlink;
# rules = DIGEST.md next to this script. Verdict on stdout, strict JSON:
#   {"pass":true|false,"reason":"<one line>"}
# Anything the judge returns that is not parseable as that = fail (fail closed).
# Exit 0 = pass, 1 = fail, 2 = usage/setup error.
#
# Needs jq. Model: LEX_CLAUDE_MASTER_MODEL (default haiku).

set -o pipefail
command -v jq >/dev/null 2>&1 || { echo '{"pass":false,"reason":"jq missing"}'; exit 2; }
command -v claude >/dev/null 2>&1 || command -v claude >/dev/null || true

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
DIGEST="$SELF_DIR/DIGEST.md"
MODEL="${LEX_CLAUDE_MASTER_MODEL:-haiku}"

fail() { jq -n --arg r "$1" '{pass:false,reason:$r}'; exit 1; }

# --- args ---
[ "${1:-}" = "verify" ] || { echo "usage: master.sh verify --answer <file> --phase identity|project [--briefing <file>]" >&2; exit 2; }
shift
answer_file=""; phase=""; briefing_file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --answer)   answer_file="$2"; shift 2 ;;
    --phase)    phase="$2"; shift 2 ;;
    --briefing) briefing_file="$2"; shift 2 ;;
    *) echo "master.sh: unknown arg $1" >&2; exit 2 ;;
  esac
done
[ -f "$answer_file" ] || { echo "master.sh: --answer file not found" >&2; exit 2; }
case "$phase" in identity|project) ;; *) echo "master.sh: --phase must be identity|project" >&2; exit 2 ;; esac

# --- ground truth ---
expected_identity="?"
link="$HOME/.claude/CLAUDE.md"
if [ -L "$link" ]; then
  expected_identity="$(basename "$(readlink "$link" 2>/dev/null)" .md 2>/dev/null)"
fi
subject_answer="$(cat "$answer_file")"

# --- compose the verifier prompt ---
if [ "$phase" = "identity" ]; then
  rules="$( [ -f "$DIGEST" ] && cat "$DIGEST" || echo '(digest unavailable)' )"
  prompt=$(cat <<EOF
You are a verifier deciding whether the SUBJECT has LOADED and INTERNALISED the
target identity and its non-negotiable rules. This is a load check, not an exam.

PASS if: the subject names the identity correctly (case-insensitive, minor
spelling of the name is fine) AND shows awareness of several of the non-negotiable
rules in its own words (it need not recite them all).
FAIL if: it is a generic assistant answer, names the wrong identity, or shows no
awareness of the specific rules.

Respond with ONLY a JSON object, no prose, no markdown fences:
{"pass": true|false, "reason": "<one short line>"}

=== GROUND TRUTH: IDENTITY (expected) ===
$expected_identity

=== GROUND TRUTH: RULES ===
$rules

=== SUBJECT SELF-REPORT ===
$subject_answer
EOF
)
else
  [ -f "$briefing_file" ] || fail "project phase needs --briefing"
  briefing="$(cat "$briefing_file")"
  prompt=$(cat <<EOF
You are a strict verifier. Judge ONLY whether the SUBJECT below correctly
understood the project state and the next step as described in the BRIEFING
(the ground truth). A restatement that misses the current task, contradicts the
briefing, or is vague/generic = fail.

Respond with ONLY a JSON object, no prose, no markdown fences:
{"pass": true|false, "reason": "<one short line>"}

=== BRIEFING (ground truth) ===
$briefing

=== SUBJECT RESTATEMENT ===
$subject_answer
EOF
)
fi

# --- spawn the neutral judge ---
raw=$(LEX_CLAUDE_DISABLE=1 command claude -p --output-format json \
        --no-session-persistence --model "$MODEL" "$prompt" 2>/dev/null) \
  || fail "judge spawn failed"

# -p --output-format json wraps the model text in .result. The verdict JSON is
# inside that string; salvage the first {...} block if the model added noise.
result=$(printf '%s' "$raw" | jq -r '.result // empty' 2>/dev/null)
[ -n "$result" ] || fail "judge returned no result"
# Extract the JSON object from the judge's reply: first { to last } across the
# whole blob (RS="\0" so ^/$ span all lines), dropping any fences or prose it
# wrapped around the verdict. Unparseable remainder → jq fails → fail closed.
verdict=$(printf '%s' "$result" | awk 'BEGIN{RS="\0"} {sub(/^[^{]*/,""); sub(/[^}]*$/,""); print}')
pass=$(printf '%s' "$verdict" | jq -r '.pass // empty' 2>/dev/null)
reason=$(printf '%s' "$verdict" | jq -r '.reason // empty' 2>/dev/null)
# jq can choke when the judge puts an unescaped quote in the reason. The pass
# boolean is what gates the reroll — recover it directly rather than lose the
# verdict to a messy reason string.
if [ -z "$pass" ]; then
  pass=$(printf '%s' "$result" | grep -oE '"pass"[[:space:]]*:[[:space:]]*(true|false)' | head -1 | grep -oE 'true|false')
  reason=$(printf '%s' "$result" | tr '\n' ' ' | sed -n 's/.*"reason"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p' | cut -c1-200)
fi

case "$pass" in
  true)  jq -n --arg r "${reason:-ok}" '{pass:true,reason:$r}'; exit 0 ;;
  false) jq -n --arg r "${reason:-rejected}" '{pass:false,reason:$r}'; exit 1 ;;
  *)     fail "unparseable verdict: $(printf '%s' "$result" | head -c 120)" ;;
esac
