#!/usr/bin/env python3
"""
列出 Claude Code 專案的所有對話 ID 與前 5 句用戶訊息
用法: python3 list_sessions.py [project_dir]
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

tw_tz = timezone(timedelta(hours=8))

if len(sys.argv) > 1:
    project_dir = sys.argv[1]
else:
    cwd = os.getcwd()
    project_key = cwd.replace("/", "-").replace(".", "-").lstrip("-")
    project_dir = os.path.expanduser(f"~/.claude/projects/-{project_key}")

if not os.path.isdir(project_dir):
    print(f"找不到 project 目錄: {project_dir}")
    sys.exit(1)

jsonl_files = sorted(
    [f for f in os.listdir(project_dir) if f.endswith(".jsonl")],
    key=lambda f: os.path.getmtime(os.path.join(project_dir, f)),
    reverse=True,
)

if not jsonl_files:
    print("沒有找到任何對話檔案")
    sys.exit(0)

print(f"專案目錄: {project_dir}")
print(f"共 {len(jsonl_files)} 個 session\n")

for fname in jsonl_files:
    fpath = os.path.join(project_dir, fname)
    session_id = fname.replace(".jsonl", "")
    size_kb = os.path.getsize(fpath) // 1024
    mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tw_tz)

    user_messages = []
    with open(fpath, encoding="utf-8") as f:
        for line in f:
            if len(user_messages) >= 5:
                break
            try:
                obj = json.loads(line)
                if obj.get("message", {}).get("role") != "user":
                    continue
                content = obj["message"].get("content", "")
                if isinstance(content, list):
                    text = " ".join(
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                else:
                    text = str(content)
                text = text.strip()
                if text and not text.startswith("<"):
                    user_messages.append(text)
            except (json.JSONDecodeError, KeyError):
                pass

    print(f"{'─' * 60}")
    print(f"ID   : {session_id}")
    print(f"大小 : {size_kb}KB    最後修改: {mtime.strftime('%Y/%m/%d %H:%M')}")
    if user_messages:
        print("前 5 句用戶訊息:")
        for i, msg in enumerate(user_messages, 1):
            print(f"  {i}. {msg[:100]}")
    else:
        print("  ⚠️  (無用戶訊息，可自動清理)")
    print()
