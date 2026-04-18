# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` for full workflow context.

## Task tracking (beads)
The beads MCP server is running. Use MCP tools directly — do NOT shell out to `bd`
via Bash unless a tool is unavailable for that operation.

**Workflow per session:**
1. Start: call `ready` to see what's unblocked
2. Claim: call `update` to set status → `in_progress`
3. During work: if you discover new tasks, call `create` with `dep` type
   `discovered-from` linking back to the current issue
4. Finish: call `close` with a one-line summary of what was done
5. Loop: call `ready` again to find newly unblocked work

**Available MCP tools:** `init`, `create`, `list`, `ready`, `show`, `update`,
`close`, `dep`, `blocked`, `stats`

**Dependency types:** use `blocks` for hard deps (affects the ready queue),
`related` for soft links, `parent-child` for epics, `discovered-from` to track
work found during implementation.

**Priority:** 0=critical, 1=high, 2=medium, 3=low, 4=backlog

## Beads has a memory function

- **Memory**: Use `bd remember "insight"` for persistent knowledge across sessions. Do NOT use MEMORY.md files — they fragment across accounts. Search with `bd memories <keyword>`.
- Persistence you don't need beats lost context

Use `bd prime` for a primer.

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var