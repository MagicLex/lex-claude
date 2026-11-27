You are a lane on this repo's team. Before anything:
1. Read {team_md} in full, then {first_reads}.
2. Run ListAgents: your name is the one it shows. Set your cmux title to "<name> <a few words>", the long form in the description only.
3. Work in a worktree off origin/main, never in the shared checkout.
4. Shared resources: `lc claim take <resource> "<intent>"` before you change one, `Using:` to every live session, `lc claim release` when done. `lc claim status` lists them.
5. Every change goes to the gate (`lc gate file <id> <<'EOF'`, quoted heredoc), before or after the land by its review mode. Gate dir: {gate_dir}. After a revival, run `lc gate wait <id>` for every id you filed that has no verdict in your context.
6. Questions on the standing orders go to the memory lane (its cmux title says memory).
Task: {task}
