---
name: session-manager
description: This skill should be used when the user asks to "list sessions", "list conversations", "show claude sessions", "clean up sessions", "delete a session", "remove conversation history", "truncate a session", or "recover from SSH conflict". Manages Claude Code conversation records (.jsonl files) under ~/.claude/projects/.
argument-hint: "list|clean|delete <session-id>|truncate [project-path]"
allowed-tools: Bash, Read
version: 0.1.0
---

# Claude Code Session Manager

Manages `.jsonl` conversation record files under `~/.claude/projects/`.

## Project Path Resolution

When no project-path is provided, derive from the current working directory:

```python
cwd = os.getcwd()
project_key = cwd.replace("/", "-").replace(".", "-").lstrip("-")
project_dir = f"~/.claude/projects/-{project_key}"
```

When project-path is provided, use it directly.

---

## Sub-commands

### `list [project-path]`

Run:
```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/list_sessions.py [project-path]
```

Display each session's ID, file size, last modified time, and first 5 user messages. Sessions with no user messages are marked ⚠️.

---

### `clean [project-path]`

1. Run `list` to display the full session list
2. Find all sessions with no meaningful user messages — excludes lines where all content starts with `<` (system-injected commands like `/clear`, `/exit`, `<local-command-caveat>`)
3. Delete them immediately — no confirmation needed, as they contain no human conversation
4. Display deletion results, then show the remaining session list

Inline Python to execute:

```python
import json, os, glob

project_dir = "<resolved project_dir>"

def has_human_message(fpath):
    with open(fpath, encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if obj.get("message", {}).get("role") != "user":
                    continue
                content = obj["message"].get("content", "")
                if isinstance(content, list):
                    text = " ".join(
                        c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                else:
                    text = str(content)
                text = text.strip()
                if text and not text.startswith("<"):
                    return True
            except:
                pass
    return False

import shutil
use_trash = shutil.which("trash") is not None

deleted = []
for fpath in glob.glob(project_dir + "/*.jsonl"):
    if not has_human_message(fpath):
        deleted.append(os.path.basename(fpath))
        if use_trash:
            os.system(f"trash {fpath}")
        else:
            os.remove(fpath)

action = "Trashed" if use_trash else "Deleted"
print(f"{action} {len(deleted)} empty sessions:")
for f in deleted:
    print(f"  - {f}")
```

---

### `delete <session-id> [project-path]`

1. Display the session's basic info (size, time, first few messages) for review
2. Delete after confirmation — use `trash` if available, otherwise `rm`:

```bash
# prefer trash (recoverable)
trash ~/.claude/projects/<project-key>/<session-id>.jsonl

# fallback if trash not installed
rm ~/.claude/projects/<project-key>/<session-id>.jsonl
```

---

### `truncate [project-path]`

Follow the steps in [references/session-recovery.md](references/session-recovery.md) to guide the truncation:

1. Run `list` to identify the target session
2. Read the `.jsonl`, display timestamped user messages to confirm the cut point
3. Back up, then truncate (keep up to the target `last-prompt` line)
4. Prompt the user to run `claude -r` to resume

---

## JSONL Structure

```
~/.claude/projects/<project-key>/<session-id>.jsonl
```

| Field | Description |
|-------|-------------|
| `message.role == "user"` | User message |
| `{"type":"last-prompt"}` | Resume anchor for `claude -r` |
| `{"type":"file-history-snapshot"}` | Session branch pointer |

Messages form a tree via `uuid` / `parentUuid` (append-only).

## Additional Resources

- **`scripts/list_sessions.py`** — Lists all sessions with preview of user messages
- **`references/session-recovery.md`** — SSH multi-host conflict recovery guide for `truncate`
