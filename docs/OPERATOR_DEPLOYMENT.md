# RIP Operator Deployment Runbook

Rex Intelligence Platform (RIP) v0.7.4-alpha

---

## 概覽

RIP 是一個**本機 CLI operator tool**，不是 web server、不需要 Docker、不需要資料庫。
Operator 透過 `poetry run rip "指令"` 在本機終端機操作，所有 runtime state 以 JSON 檔案
存放於 `runtime/` 目錄，所有檔案操作錨定在 `SAFE_PDF_ROOT` 指定的目錄下。

本文涵蓋：安裝、設定、smoke test、runtime 目錄說明、備份、還原、升級、lock 處理、Git hygiene。

---

## 前置條件

| 項目 | 需求 | 說明 |
|------|------|------|
| Python | 3.12 以上 | `python --version` |
| Poetry | 1.8 以上 | `poetry --version` |
| git | 任意現代版本 | `git --version` |
| OS | Linux / macOS / WSL2 | Windows native **不支援**（見下方說明） |

### Windows native 不支援 Runtime Lock

`runtime/rip.lock` 使用 POSIX `fcntl.flock`（`LOCK_EX | LOCK_NB`），
**僅 Linux / macOS / WSL2 有效**。Windows native 環境下 `fcntl` 模組不存在，
無法啟動 RIP。請使用 WSL2 或 macOS。

---

## 安裝流程

```bash
# 1. 取得原始碼
git clone <repo-url>
cd rex-intelligence-platform

# 2. 安裝 Python 相依套件
poetry install

# 3. 確認測試全數通過
poetry run pytest -q
# 預期輸出：709 passed（或更多）

# 4. 確認 CLI entry point 可用
poetry run rip "說明"
# 預期輸出：完整指令說明文字
```

> **注意**：`poetry install` 才會建立 `rip` console_scripts entry point。
> 若跳過此步驟，`poetry run rip` 會找不到指令。

---

## 設定（.env）

RIP 從 `.env`（如存在）讀取設定。絕大多數場景只需設定 `SAFE_PDF_ROOT`。
其他 Settings 欄位（`DATABASE_URL`、`REDIS_URL` 等）為平台遠期擴充預留，
**CLI 模式下不使用，無需設定**。

### .env 範例

```bash
# =====================================================
# RIP CLI operator 設定（只需設定以下兩項）
# =====================================================

# PDF 操作的根目錄：改名 / 搬移計畫與執行均限制在此目錄下
# 預設值：<repo>/workspace/sandbox/pdf_inbox
SAFE_PDF_ROOT=/Users/operator/Documents/pdf_inbox

# Runtime state 目錄（approvals.json / transaction logs / rip.lock）
# 預設值：<repo>/runtime
# 一般不需更動；僅在需要將 runtime 存放到 repo 外時才設定
# RUNTIME_DIR=/path/to/external/runtime

# =====================================================
# 以下欄位在 CLI 模式下不使用，可不設定
# =====================================================
# ANTHROPIC_API_KEY=
# LINE_CHANNEL_ID=
# DATABASE_URL=
# REDIS_URL=
```

### SAFE_PDF_ROOT 說明

- RIP 所有改名 / 搬移操作的**根目錄邊界**（path traversal 防護錨定點）。
- **相對路徑** 均在此目錄下解析；逃出此目錄的路徑會被 fail-safe 拒絕。
- **建議**：指定一個專門存放待整理 PDF 的目錄，不要指定到整個 home 目錄。
- 環境變數未設定時，預設為 `<repo>/workspace/sandbox/pdf_inbox`。

### RUNTIME_DIR 說明

- 存放 `approvals.json`、`rename_transactions.json`、`move_transactions.json`、`rip.lock`。
- 預設為 `<repo>/runtime`，通常不需改動。
- **如需放到 repo 外**（例如共享磁碟或另一個 partition）：設定 `RUNTIME_DIR=/path/to/runtime`。
- **每個 RIP deployment 應使用獨立的 `RUNTIME_DIR`**，不建議多個專案共用同一 runtime 目錄——
  不同專案的 approval ID / transaction ID 不互通，共用目錄會造成狀態混淆。

---

## 啟動與 Smoke Test

```bash
# 1. 檢視指令說明（zero side effects）
poetry run rip "說明"

# 2. Dry-run 計畫（不會改動任何檔案）
poetry run rip "整理檔名"
poetry run rip "整理資料夾"

# 3. 確認 runtime/ 目錄已自動建立
ls runtime/
# 預期看到：approvals.json（首次執行 planning 後建立）

# 4. 舊版 entry point（向下相容，仍可使用）
poetry run python scripts/mock_line.py "說明"
```

> `runtime/` 目錄會在第一次執行需要寫入 runtime state 的指令時自動建立，
> 不需要手動 `mkdir`。

---

## runtime/ 目錄說明

`runtime/` 目錄存放所有 RIP 的 runtime state，**全數已 gitignored，不進 Git**。

```
runtime/
├── approvals.json              # Approval store（改名 / 搬移計畫的核准狀態）
├── rename_transactions.json    # Rename transaction log（已執行的改名紀錄）
├── move_transactions.json      # Move transaction log（已執行的搬移紀錄）
└── rip.lock                    # Concurrency lock（OS 管理，見下方說明）
```

### approvals.json

- 存放所有待核准 / 已核准 / 已取消的計畫（改名、搬移、電費單）。
- 格式：`{ "approvals": { "<approval_id>": { ... } } }`
- `確認 {id}` / `確認改名 {id}` / `確認搬移 {id}` / `取消 {id}` 都會讀寫此檔。
- 檔案不存在時（首次執行）會自動建立。

### rename_transactions.json

- 存放所有已執行的改名交易紀錄（含 original_path / new_path / timestamp）。
- `確認改名` 執行後寫入；`回滾改名` 執行後標記 rolled_back。
- 可用 `預覽回滾改名 {transaction_id}` 檢視內容（純讀取，不修改）。

### move_transactions.json

- 存放所有已執行的搬移交易紀錄。
- `確認搬移` 執行後寫入；`回滾搬移` 執行後標記 rolled_back。
- 可用 `預覽回滾搬移 {transaction_id}` 檢視內容（純讀取，不修改）。

### rip.lock

- POSIX advisory lock 檔案，由 `fcntl.flock(LOCK_EX | LOCK_NB)` 管理。
- **檔案存在不代表 lock 正被持有。** Lock 的有效性由 OS kernel 的 fd 追蹤，
  不在 rip.lock 檔案內容裡。
- Process 正常結束或意外 crash 時，OS 自動釋放 lock（fd 關閉 → lock 解除）。
- **一般不需要手動處理 rip.lock**（見下方「runtime_lock_busy 處理」）。

---

## 備份

### 何時備份

- 執行 `確認改名` / `確認搬移` 等 destructive action **之前**。
- 升級 RIP 版本之前。
- 需要保存某個時間點的計畫 / 交易狀態時。

### 備份 runtime/ JSON

```bash
# 一次備份全部 runtime JSON（推薦）
cp -rp runtime/ runtime_backup_$(date +%Y%m%d_%H%M%S)/

# 或只備份特定檔案
cp runtime/approvals.json         runtime/approvals.json.bak
cp runtime/rename_transactions.json runtime/rename_transactions.json.bak
cp runtime/move_transactions.json   runtime/move_transactions.json.bak
```

> `rip.lock` 不需要備份（OS managed，無持久內容）。

### 驗證備份完整性

```bash
# 確認 JSON 格式正確
python -m json.tool runtime/approvals.json > /dev/null && echo "OK"
python -m json.tool runtime/rename_transactions.json > /dev/null && echo "OK"
python -m json.tool runtime/move_transactions.json > /dev/null && echo "OK"
```

### 備份 PDF 原始檔案

**重要**：runtime JSON 檔案**不包含 PDF 原始檔案的內容**，只記錄路徑與狀態。
在執行大量改名 / 搬移前，除了備份 `runtime/`，也請：

- 確認 `SAFE_PDF_ROOT` 對應目錄下的原始 PDF 已有外部備份（Time Machine / rsync / cloud storage 等）；
  或在執行前手動備份整個 PDF 目錄：
  ```bash
  cp -rp /path/to/pdf_inbox/ /path/to/pdf_inbox_backup_$(date +%Y%m%d)/
  ```
- 回滾 (`回滾改名` / `回滾搬移`) 只能還原已記錄在 transaction log 的操作，
  **無法還原未記錄的手動 filesystem 改動**。

---

## 還原

```bash
# 1. 確認沒有 RIP process 正在執行
ps aux | grep -E "rip|mock_line"

# 2. 若 rip.lock 存在，確認上一步確實沒有任何 process 仍在跑
#    （lock 存在不代表被持有；確認無 process 後可安全跳過）
ls -la runtime/rip.lock 2>/dev/null

# 3. 還原 JSON 備份
cp runtime_backup_YYYYMMDD_HHMMSS/approvals.json          runtime/approvals.json
cp runtime_backup_YYYYMMDD_HHMMSS/rename_transactions.json  runtime/rename_transactions.json
cp runtime_backup_YYYYMMDD_HHMMSS/move_transactions.json    runtime/move_transactions.json

# 4. 驗證還原後 JSON 格式正確
python -m json.tool runtime/approvals.json > /dev/null && echo "approvals OK"
python -m json.tool runtime/rename_transactions.json > /dev/null && echo "rename_tx OK"
python -m json.tool runtime/move_transactions.json > /dev/null && echo "move_tx OK"

# 5. 恢復操作
poetry run rip "說明"
```

---

## 升級

```bash
# 1. 備份 runtime JSON（必做）
cp -rp runtime/ runtime_backup_$(date +%Y%m%d_%H%M%S)/

# 2. 確認沒有 RIP process 正在執行
ps aux | grep -E "rip|mock_line"

# 3. 拉取新版本
git pull origin main

# 4. 更新相依套件
poetry install

# 5. 確認測試通過
poetry run pytest -q
# 預期：所有測試 passed（新版本 test count 可能增加）

# 6. Smoke test
poetry run rip "說明"

# 7. 恢復操作
```

> 升級後若有 runtime JSON schema 變更，CHANGELOG.md 中會有明確說明。
> v0.7.4-alpha 的三個 JSON schema 在 Phase 17C 前後無異動。

---

## runtime_lock_busy 處理

當指令回覆出現以下訊息時：

```
小雷收到：目前有另一個操作正在執行中，請稍候再試。
- 原因：runtime_lock_busy
```

### 標準處理流程

```bash
# 1. 稍等數秒，確認另一個 rip 指令已完成
#    （lock 會在 process 結束時由 OS 自動釋放）

# 2. 重試指令
poetry run rip "確認改名 <approval_id>"
```

### 若重試後仍持續 lock_busy

```bash
# 1. 確認是否有 RIP process 仍在執行
ps aux | grep -E "rip|mock_line" | grep -v grep

# 若有 process 在跑：等待其完成後重試，不要強制刪除 lock。

# 若確認沒有任何 RIP process 在執行：
# 2. 此時 lock 屬於 crash 殘留（fd 已關閉，OS 已釋放；rip.lock 檔案仍存在但 lock 無效）
#    可安全刪除 rip.lock 後重試
rm runtime/rip.lock
poetry run rip "<原本的指令>"
```

### 重要提醒

- `rip.lock` **檔案存在 ≠ lock 正被持有**。Lock 有效性由 OS kernel 追蹤，
  rip.lock 只是 lock 的 fd target，本身沒有狀態資訊。
- **絕對不可在確認有 RIP process 仍在執行時刪除 rip.lock**——
  強制刪除會破壞正在進行的 destructive action 的並發保護，可能導致 runtime state 損毀。
- 只有在確認「沒有任何 RIP process 仍在持續 busy」的前提下，才可刪除 `runtime/rip.lock` 後重試。

---

## Git Hygiene

### runtime/ 目錄不進 Git

```bash
# 確認 runtime/ 內容未被 git 追蹤
git ls-files runtime/
# 預期輸出：（空，無任何追蹤檔案）

# runtime/ 已在根目錄 .gitignore 覆蓋：
#   runtime/approvals.json
#   runtime/rename_transactions.json
#   runtime/move_transactions.json
#   runtime/                      ← 完整目錄 gitignored
```

> **絕對不要 `git add runtime/`**。runtime JSON 可能包含本機檔案路徑，
> 提交後難以清除，且對其他 operator 毫無意義。

### dist/ 目錄不進 Git

```bash
# 確認 dist/ 未被追蹤（poetry build 產出，已 gitignored）
git ls-files dist/
# 預期輸出：（空）
```

### backup 目錄不進 Git

若備份目錄建在 repo 根目錄下（例如 `runtime_backup_20260613_120000/`），
請確認已加入 `.gitignore` 或使用 repo 外路徑：

```bash
# 選項 A：備份到 repo 外
cp -rp runtime/ ~/Desktop/rip_backup_$(date +%Y%m%d)/

# 選項 B：備份在 repo 內，手動加 gitignore
echo "runtime_backup_*/" >> .gitignore
```

---

## Preflight Validation（Phase 17D）

`app/core/preflight.py` 提供 **safe preflight（low-write）** 驗證，確認 operator 本機環境
滿足 RIP 執行條件。

### Preflight 檢查項目

| 項目 | 說明 |
|------|------|
| `python_version` | Python ≥ 3.12 |
| `fcntl_available` | `fcntl` 模組可 import（Linux / macOS / WSL2 only） |
| `safe_pdf_root_exists` | `SAFE_PDF_ROOT` 目錄存在（只回報，**不自動建立**） |
| `runtime_dir_writable` | `RUNTIME_DIR` 可建立 / 可寫入（**允許 mkdir**，不寫 JSON） |
| `runtime_not_git_tracked` | `runtime/` 下無 git 追蹤檔案 |
| `dist_not_git_tracked` | `dist/` 下無 git 追蹤檔案 |
| `pyproject_console_scripts` | pyproject.toml 含 `rip = "scripts.mock_line:main"` |

### Safe preflight 保證

- **不呼叫** `acquire_runtime_lock()`（不取得 `fcntl` lock，不建立 `rip.lock`）
- **不建立** `approvals.json` / `rename_transactions.json` / `move_transactions.json`
- **不修改** 任何 workflow state
- `SAFE_PDF_ROOT` 不存在時只回報失敗，不自動建立目錄
- `RUNTIME_DIR` 不存在時允許建立目錄（寫入測試用臨時檔案 `.preflight_write_test` 後立即刪除）

### 執行 Preflight

```python
# Python 直接執行
from pathlib import Path
from app.core.preflight import run_operator_preflight

results = run_operator_preflight()
for item in results:
    status = "✅" if item.ok else "❌"
    print(f"{status} [{item.name}] {item.message}")
```

```bash
# 透過 pytest 執行（輸出各項 pass / fail）
poetry run pytest tests/test_operator_preflight.py -v
```

---

## 快速參考

| 情境 | 指令 |
|------|------|
| 查看所有可用指令 | `poetry run rip "說明"` |
| 執行 preflight 驗證 | `poetry run pytest tests/test_operator_preflight.py -v` |
| 升級前備份 | `cp -rp runtime/ runtime_backup_$(date +%Y%m%d_%H%M%S)/` |
| 升級 | `git pull && poetry install && poetry run pytest -q` |
| Lock busy 且無 process 在跑 | `rm runtime/rip.lock && poetry run rip "<指令>"` |
| 確認 runtime 未進 Git | `git ls-files runtime/` |
| 驗證 JSON 完整性 | `python -m json.tool runtime/approvals.json` |
