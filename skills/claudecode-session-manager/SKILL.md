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
4. Also clean up UUID subdirectories (subagent sessions): if a UUID dir has no subagent `.jsonl` with meaningful messages, delete the entire UUID directory
5. Display deletion results, then show the remaining session list

Inline Python to execute:

```python
import json, os, glob, shutil

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

use_trash = shutil.which("trash") is not None

def delete_path(path):
    if use_trash:
        os.system(f"trash {shutil.quote(path)}")
    elif os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)

deleted_sessions = []
deleted_uuid_dirs = []

# Clean root-level .jsonl sessions
for fpath in glob.glob(project_dir + "/*.jsonl"):
    if not has_human_message(fpath):
        deleted_sessions.append(os.path.basename(fpath))
        delete_path(fpath)

# Clean UUID subdirectories (subagent sessions)
import re
uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
for entry in os.scandir(project_dir):
    if not entry.is_dir() or not uuid_pattern.match(entry.name):
        continue
    subagent_files = glob.glob(entry.path + "/subagents/*.jsonl")
    if not subagent_files or not any(has_human_message(f) for f in subagent_files):
        deleted_uuid_dirs.append(entry.name)
        delete_path(entry.path)

action = "Trashed" if use_trash else "Deleted"
print(f"{action} {len(deleted_sessions)} empty sessions:")
for f in deleted_sessions:
    print(f"  - {f}")
print(f"{action} {len(deleted_uuid_dirs)} empty UUID subagent dirs:")
for d in deleted_uuid_dirs:
    print(f"  - {d}/")
```

---

### `delete <session-id> [project-path]`

1. Display the session's basic info (size, time, first few messages) for review
2. Delete after confirmation — use `trash` if available, otherwise `rm`
3. Also delete the UUID subdirectory `<session-id>/` if it exists (contains subagent sessions)

```bash
# prefer trash (recoverable)
trash ~/.claude/projects/<project-key>/<session-id>.jsonl
trash ~/.claude/projects/<project-key>/<session-id>   # if dir exists

# fallback if trash not installed
rm ~/.claude/projects/<project-key>/<session-id>.jsonl
rm -rf ~/.claude/projects/<project-key>/<session-id>  # if dir exists
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
