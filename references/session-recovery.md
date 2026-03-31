# Claude Code 多主機 SSH 對話衝突復原手冊

## 問題情境

兩台遠端電腦（A、B）同時透過 SSH 連接同一台主機，都在操控同一個 Claude Code session。
A 主機因看到舊的對話記錄而輸入新訊息，導致 `claude -r` 恢復時跑到 A 主機的分支，B 主機的最新進度消失。

---

## 核心原理

Claude Code 對話存在 `~/.claude/projects/<project>/` 下的 `.jsonl` 檔：

```
~/.claude/projects/-home-<user>-myproject/
  3c8895f4-462c-47ee-b47e-d32f2916e5dd.jsonl   ← 主對話樹
```

- **JSONL 是 append-only**，訊息不會被刪除，只會往後加
- 每條訊息有 `uuid` 和 `parentUuid`，形成一棵樹
- `claude -r` 依賴 JSONL 末尾的 metadata 決定恢復位置：
  - `{"type":"last-prompt",...}` — 最後一次使用者輸入
  - `{"type":"file-history-snapshot",...}` — session 分支指針

---

## 偵查步驟

### 1. 確認 JSONL 位置與時間

```bash
ls -lh ~/.claude/projects/<project>/*.jsonl
```

### 2. 找出 16:30~17:20 間的 user 訊息（依需求調整時間）

```python
python3 -c "
import json
from datetime import datetime, timezone, timedelta
tw_tz = timezone(timedelta(hours=8))
with open('對話.jsonl') as f:
    for line in f:
        obj = json.loads(line)
        ts = obj.get('timestamp','')
        if not ts: continue
        msg = obj.get('message', {})
        if msg.get('role') != 'user': continue
        dt = datetime.fromisoformat(ts.replace('Z','+00:00'))
        tw = dt.astimezone(tw_tz)
        content = msg.get('content','')
        text = content if isinstance(content,str) else ' '.join(
            c.get('text','') for c in content if isinstance(c,dict) and c.get('text'))
        if text.strip():
            print(f'[{tw.strftime(\"%H:%M:%S\")}] {text[:150]}')
"
```

### 3. 找出所有 leaf node（沒有子節點的訊息）

```python
python3 -c "
import json
from datetime import datetime, timezone, timedelta
tw_tz = timezone(timedelta(hours=8))
with open('對話.jsonl') as f:
    lines = f.readlines()
all_uuids, all_parents, uuid_info = set(), set(), {}
for i, line in enumerate(lines):
    try:
        obj = json.loads(line)
        uuid, parent = obj.get('uuid',''), obj.get('parentUuid','')
        if uuid:
            all_uuids.add(uuid)
            content = obj.get('message',{}).get('content','')
            text = content if isinstance(content,str) else str(content)[:60]
            uuid_info[uuid] = (i, obj.get('timestamp',''), obj.get('message',{}).get('role','?'), text)
        if parent: all_parents.add(parent)
    except: pass
for uuid in sorted(all_uuids - all_parents, key=lambda u: uuid_info[u][1] if u in uuid_info else ''):
    i, ts, role, text = uuid_info[uuid]
    if ts:
        tw = datetime.fromisoformat(ts.replace('Z','+00:00')).astimezone(tw_tz)
        print(f'L{i} [{tw.strftime(\"%H:%M:%S\")}] {role} {uuid[:8]} | {text[:60]}')
"
```

**目標**：找到 B 主機最後一條 assistant leaf（時間最近且在 A 主機操作之前）

### 4. 找出截斷點

在 B 主機最後 assistant 訊息之後，檢查 metadata 行：

```bash
python3 -c "
import json
with open('對話.jsonl') as f:
    lines = f.readlines()
# 檢查 B 主機最後 assistant 訊息附近的幾行
for i in range(B_last_line, B_last_line + 5):
    print(f'L{i}: {lines[i][:120]}')
"
```

找到 `{"type":"last-prompt",...}` 行 → 這就是截斷點（保留到這行）

---

## 復原步驟

### Step 1：備份

```bash
cp 對話.jsonl 對話.jsonl.bak_$(date +%Y%m%d_%H%M%S)
```

### Step 2：截斷（移除 A 主機的記錄）

```python
python3 -c "
KEEP_LINES = 1224  # 保留到 last-prompt 那行（含），依實際調整

with open('對話.jsonl') as f:
    lines = f.readlines()

with open('對話.jsonl', 'w') as f:
    f.writelines(lines[:KEEP_LINES])

print(f'保留 {KEEP_LINES} 行，移除 {len(lines)-KEEP_LINES} 行')
print(f'最後一行: {lines[KEEP_LINES-1][:100]}')
"
```

確認最後一行是 `{"type":"last-prompt","lastPrompt":"...B主機最後輸入...",...}`

### Step 3：恢復

```bash
cd ~/myproject   # 切到目標 project 目錄
claude -r
```

---

## 預防建議

| 情境 | 建議做法 |
|------|---------|
| 多人/多主機共用同一主機 | 每個主機用不同的 project 目錄 |
| 同一 project 多台連線 | 操作前先確認對方是否在作業，避免同時輸入 |
| 長時間離開 | 先 `/compact` 壓縮，再記錄當前 uuid，方便事後定位 |
| 定期備份 | 對重要 session 定時 `cp *.jsonl *.jsonl.bak_$(date +%s)` |

---

## 快速診斷指令

```bash
# 查看某 project 所有 session 的最後修改時間
ls -lt ~/.claude/projects/<project>/*.jsonl

# 查看今天的 user 訊息摘要
python3 -c "
import json, sys
from datetime import datetime, timezone, timedelta
tw_tz = timezone(timedelta(hours=8))
today = datetime.now(tw_tz).date().isoformat()
with open(sys.argv[1]) as f:
    for line in f:
        try:
            obj = json.loads(line)
            msg = obj.get('message',{})
            if msg.get('role') != 'user': continue
            ts = obj.get('timestamp','')
            if not ts: continue
            tw = datetime.fromisoformat(ts.replace('Z','+00:00')).astimezone(tw_tz)
            if tw.date().isoformat() != today: continue
            content = msg.get('content','')
            text = content if isinstance(content,str) else str(content)[:80]
            if text.strip() and not text.startswith('<'):
                print(f'[{tw.strftime(\"%H:%M:%S\")}] {text[:100]}')
        except: pass
" ~/.claude/projects/<project>/*.jsonl
```
