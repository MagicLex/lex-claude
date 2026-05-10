#!/usr/bin/env bash
# Managed by lex-claude. Source: $INSTALL_DIR/statusline-command.sh
# Renders: ➜ dir git:(branch) ✗ identity f:lu/ctx/kn tok:Nk

set -u
input=$(cat)

j() { jq -r "$1" 2>/dev/null <<<"$input"; }
cwd=$(j '.workspace.current_dir')
[ -z "$cwd" ] && cwd=$(j '.cwd')
dir_name=$(basename "${cwd:-?}")
transcript=$(j '.transcript_path // empty')

git_info=""
if [ -n "$cwd" ] && git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git -C "$cwd" --no-optional-locks symbolic-ref --short HEAD 2>/dev/null \
             || git -C "$cwd" --no-optional-locks rev-parse --short HEAD 2>/dev/null)
    if [ -n "$branch" ]; then
        if git -C "$cwd" --no-optional-locks diff --quiet 2>/dev/null \
           && git -C "$cwd" --no-optional-locks diff --cached --quiet 2>/dev/null; then
            git_info=$(printf " \033[1;34mgit:(\033[0;31m%s\033[1;34m)\033[0m" "$branch")
        else
            git_info=$(printf " \033[1;34mgit:(\033[0;31m%s\033[1;34m) \033[0;33m✗\033[0m" "$branch")
        fi
    fi
fi

ident_info=""
if [ -L "$HOME/.claude/CLAUDE.md" ]; then
    ident=$(basename "$(readlink "$HOME/.claude/CLAUDE.md")" .md)
    [ -n "$ident" ] && ident_info=$(printf " \033[0;35m%s\033[0m" "$ident")
fi

files_info=""
if [ -n "$transcript" ] && [ -f "$transcript" ] && command -v jq >/dev/null 2>&1; then
    lu_paths=$(jq -r 'select(.type=="assistant") | .message.content[]?
                      | select(.type=="tool_use" and (.name=="Read" or .name=="Edit" or .name=="Write" or .name=="NotebookEdit"))
                      | .input.file_path // empty' "$transcript" 2>/dev/null \
               | awk 'NF' | sort -u)
    n_lu=$(printf '%s\n' "$lu_paths" | awk 'NF' | wc -l | tr -d ' ')

    # in-ctx: reads after the last compaction marker. No marker → in-ctx == lu.
    cutoff=$(grep -nE '"isCompactSummary"[[:space:]]*:[[:space:]]*true|"type"[[:space:]]*:[[:space:]]*"summary"|<command-name>compact' \
             "$transcript" 2>/dev/null | tail -1 | cut -d: -f1)
    if [ -n "$cutoff" ]; then
        n_inctx=$(tail -n +"$cutoff" "$transcript" 2>/dev/null \
                  | jq -r 'select(.type=="assistant") | .message.content[]?
                           | select(.type=="tool_use" and (.name=="Read" or .name=="Edit" or .name=="Write" or .name=="NotebookEdit"))
                           | .input.file_path // empty' 2>/dev/null \
                  | awk 'NF' | sort -u | wc -l | tr -d ' ')
    else
        n_inctx=$n_lu
    fi

    n_known=0
    if [ -n "$cwd" ]; then
        cwd_re=$(printf '%s' "$cwd" | sed 's/[].[^$*\/]/\\&/g')
        all_paths=$(grep -oE "${cwd_re}/[A-Za-z0-9_./@+-]+\\.[a-zA-Z0-9]{1,8}" "$transcript" 2>/dev/null \
                    | sort -u)
        if [ -n "$all_paths" ]; then
            if [ -n "$lu_paths" ]; then
                n_known=$(comm -23 <(printf '%s\n' "$all_paths") <(printf '%s\n' "$lu_paths") | wc -l | tr -d ' ')
            else
                n_known=$(printf '%s\n' "$all_paths" | wc -l | tr -d ' ')
            fi
        fi
    fi

    [ "$((n_lu + n_known))" -gt 0 ] 2>/dev/null \
        && files_info=$(printf " \033[2;37mf:%d/%d/%d\033[0m" "$n_lu" "$n_inctx" "$n_known")
fi

tok_info=""
ctx_tokens=$(j '.context_window.used_tokens // empty')
if [ -z "$ctx_tokens" ]; then
    ctx_used=$(j '.context_window.used_percentage // empty')
    if [ -n "$ctx_used" ]; then
        total=$(j '.context_window.total_tokens // .context_window.window_size // 1000000')
        ctx_tokens=$(awk -v u="$ctx_used" -v t="$total" 'BEGIN{printf "%d", u*t/100}')
    fi
fi
if [ -n "$ctx_tokens" ]; then
    threshold=${LEX_CLAUDE_DUMB_ZONE_TOKENS:-50000}
    k=$(awk -v t="$ctx_tokens" 'BEGIN{printf "%d", t/1000}')
    if [ "$ctx_tokens" -ge "$threshold" ] 2>/dev/null; then
        tok_info=$(printf " \033[1;31mtok:%dk\033[0m" "$k")
    else
        tok_info=$(printf " \033[2;37mtok:%dk\033[0m" "$k")
    fi
fi

printf "\033[1;32m➜\033[0m  \033[0;36m%s\033[0m%s%s%s%s" \
    "$dir_name" "$git_info" "$ident_info" "$files_info" "$tok_info"
