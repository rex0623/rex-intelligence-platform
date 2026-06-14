# RIP Operator Deployment Runbook

Rex Intelligence Platform (RIP) v0.7.7-alpha（Phase 19H — Operator Docs for Experimental SQLite Backend）

---

## 概覽

RIP 是一個**本機 CLI operator tool**，不是 web server、不需要 Docker。
Operator 透過 `poetry run rip "指令"` 在本機終端機操作，所有 runtime state 存放於 `runtime/` 目錄，
所有檔案操作錨定在 `SAFE_PDF_ROOT` 指定的目錄下。

**預設 persistence backend**：JSON 檔案（production-safe，v0.7.7-alpha 行為與舊版完全相同）。
**Experimental**：`TRANSACTION_LOG_BACKEND=sqlite` 可選啟用 SQLite transaction log backend（rename / move logs only）——詳見「[Experimental SQLite Transaction Log Backend](#experimental-sqlite-transaction-log-backend)」。

本文涵蓋：安裝、設定、smoke test、runtime 目錄說明、備份、還原、升級、lock 處理、SQLite backend 說明、Git hygiene。

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

# Transaction log persistence backend（Phase 19D，v0.7.7-alpha）
# "json"   → JSON flat-file backend（預設，production-safe，不建立 rip.db）
# "sqlite" → Experimental SQLite backend（僅影響 rename/move transaction logs；
#             ⚠️ 切換前請閱讀「Experimental SQLite Transaction Log Backend」說明）
# TRANSACTION_LOG_BACKEND=json

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
- 若啟用 `TRANSACTION_LOG_BACKEND=sqlite`，也會包含 `rip.db`（及 WAL mode 可能產生的 `rip.db-wal` / `rip.db-shm`）。
- 預設為 `<repo>/runtime`，通常不需改動。
- **如需放到 repo 外**（例如共享磁碟或另一個 partition）：設定 `RUNTIME_DIR=/path/to/runtime`。
- **每個 RIP deployment 應使用獨立的 `RUNTIME_DIR`**，不建議多個專案共用同一 runtime 目錄——
  不同專案的 approval ID / transaction ID 不互通，共用目錄會造成狀態混淆。
- **WSL2 注意**：若使用 `TRANSACTION_LOG_BACKEND=sqlite`，建議 `RUNTIME_DIR` 放在 Linux filesystem（例如 WSL home 底下的 repo `runtime/`）。`/mnt/c` 或 Windows DrvFs/NTFS 路徑可能造成 WAL mode 不穩定。

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
├── rename_transactions.json    # Rename transaction log（已執行的改名紀錄，json backend）
├── move_transactions.json      # Move transaction log（已執行的搬移紀錄，json backend）
├── rip.lock                    # Concurrency lock（OS 管理，見下方說明）
├── rip.db                      # SQLite transaction log DB（僅 TRANSACTION_LOG_BACKEND=sqlite 時建立）
├── rip.db-wal                  # SQLite WAL 日誌（WAL mode 時自動產生，rip.db 存在時可能出現）
└── rip.db-shm                  # SQLite shared-memory 索引（WAL mode 時自動產生）
```

> **預設（json backend）只有前三個 JSON 檔與 rip.lock**。`rip.db` / `rip.db-wal` / `rip.db-shm` 只在 `TRANSACTION_LOG_BACKEND=sqlite` 時才會出現。

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

### rip.db / rip.db-wal / rip.db-shm

- **只在 `TRANSACTION_LOG_BACKEND=sqlite` 時才會建立**。預設 json backend 下永不出現。
- `rip.db`：SQLite transaction log DB，儲存 rename / move transaction 紀錄。
- `rip.db-wal`：WAL（Write-Ahead Log）日誌檔，SQLite WAL mode 下自動產生。
- `rip.db-shm`：WAL shared-memory 索引，WAL mode 下自動產生。
- 備份時需同時處理 wal / shm，建議使用 `sqlite3 .backup` 指令（見下方「備份」）。
- `rip.lock` 不取代 `rip.db`；兩者用途不同（見「[runtime lock 與 SQLite 的關係](#runtime-lock-與-sqlite-的關係)」）。

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

### 備份 SQLite DB（若使用 sqlite backend）

若 `TRANSACTION_LOG_BACKEND=sqlite`，請使用 SQLite hot backup 指令，而非直接 `cp`：

```bash
# 建議：online hot backup（WAL-safe，不需要停止 RIP process）
sqlite3 runtime/rip.db ".backup runtime/rip_backup_$(date +%Y%m%d_%H%M%S).db"

# 若要手動 cp（需確認無 RIP process 正在執行）
cp runtime/rip.db     runtime/rip.db.bak
cp runtime/rip.db-wal runtime/rip.db-wal.bak 2>/dev/null || true
cp runtime/rip.db-shm runtime/rip.db-shm.bak 2>/dev/null || true
```

> 直接 `cp rip.db` 而不處理 WAL 可能產生不一致的備份。優先使用 `sqlite3 .backup`。

### 驗證 SQLite DB 完整性

```bash
sqlite3 runtime/rip.db "PRAGMA integrity_check;"
# 預期輸出：ok

sqlite3 runtime/rip.db "SELECT COUNT(*) FROM rename_transactions;"
sqlite3 runtime/rip.db "SELECT COUNT(*) FROM move_transactions;"
```

### 備份 PDF 原始檔案

**重要**：runtime 檔案（JSON 或 SQLite）**不包含 PDF 原始檔案的內容**，只記錄路徑與狀態。
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

### 還原 JSON backup（json backend，預設）

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

### 還原 SQLite DB backup（sqlite backend）

```bash
# 1. 確認沒有 RIP process 正在執行
ps aux | grep -E "rip|mock_line"

# 2. 保留目前 DB 供診斷（可選）
cp runtime/rip.db runtime/rip.db.corrupt 2>/dev/null || true

# 3. 還原備份
cp runtime/rip_backup_YYYYMMDD_HHMMSS.db runtime/rip.db
# 刪除舊的 WAL/SHM（避免還原的 DB 與舊 WAL 不一致）
rm -f runtime/rip.db-wal runtime/rip.db-shm

# 4. 驗證還原後 DB 完整性
sqlite3 runtime/rip.db "PRAGMA integrity_check;"  # 預期：ok
sqlite3 runtime/rip.db "SELECT COUNT(*) FROM rename_transactions;"
sqlite3 runtime/rip.db "SELECT COUNT(*) FROM move_transactions;"

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

> 升級後若有 runtime JSON schema 或 SQLite schema 變更，CHANGELOG.md 中會有明確說明。
> v0.7.7-alpha 的三個 JSON schema（approvals / rename_transactions / move_transactions）格式不變。

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

## Experimental SQLite Transaction Log Backend

> **Status**：Experimental（v0.7.7-alpha）。JSON backend 仍為預設。此 section 說明如何啟用、限制、備份與切換回 JSON。

### 啟用方式

在 `.env` 中加入：

```bash
TRANSACTION_LOG_BACKEND=sqlite
```

或臨時覆寫（單次指令）：

```bash
TRANSACTION_LOG_BACKEND=sqlite poetry run rip "確認改名 <approval_id>"
```

切換後，rename / move transaction log 會寫入 `runtime/rip.db`（SQLite DB）。**approvals.json 不受影響**。

### 影響範圍

| 功能 | json backend（預設） | sqlite backend（experimental） |
|------|---------------------|-------------------------------|
| Approval store（approvals.json） | JSON 檔案 | 不變，仍 JSON 檔案 |
| Rename transaction log | rename_transactions.json | runtime/rip.db |
| Move transaction log | move_transactions.json | runtime/rip.db |
| Planning / Help 指令 | 不受影響 | 不受影響 |
| Destructive command regex | 不變 | 不變 |
| Runtime lock（rip.lock） | 保留 | 保留 |

### ⚠️ 重要：目前沒有 migration script

**切換到 sqlite backend 前，請先閱讀此節。**

- 目前**沒有** JSON → SQLite migration script（預計 Phase 19I 實作）。
- 若已有 `rename_transactions.json` / `move_transactions.json` 歷史紀錄，切換到 sqlite 後：
  - 舊 JSON transaction history **在 SQLite backend 下完全不可見**。
  - `預覽回滾改名 <tx_id>` → 找不到切換前的 JSON transaction，回覆 `transaction_not_found`。
  - `回滾改名 <tx_id>` → 同上，找不到，**無法回滾切換前的改名**。
  - `預覽回滾搬移 <tx_id>` / `回滾搬移 <tx_id>` → 同理。
- **這不是資料刪除**：JSON 檔案仍完整保留於 `runtime/`。
- **切回 json backend 後，舊 JSON history 立即恢復可用**（見「[Fallback to JSON](#fallback-to-json)」）。

**建議**：若環境中已有重要的 JSON transaction history（例如有尚未回滾的 `success` action），**暫時不要切換到 sqlite**，等待 migration script 完成（Phase 19I）。

### ⚠️ SQLite prune_transactions 尚未實作

- SQLite backend 的 `prune_transactions()` 目前 raise `NotImplementedError`。
- `mock_line` operator commands 目前**沒有 prune 指令**，日常操作（確認 / 預覽 / 回滾）完全不受影響。
- 若需要清理 SQLite transaction log，目前只能手動操作 DB 或切換回 json backend 後使用 JSON prune API。
- SQLite prune 實作預計留至後續 phase。

### Backup（SQLite backend）

```bash
# 建議：online hot backup（WAL-safe）
sqlite3 runtime/rip.db ".backup runtime/rip_backup_$(date +%Y%m%d_%H%M%S).db"

# 驗證備份
sqlite3 runtime/rip_backup_YYYYMMDD_HHMMSS.db "PRAGMA integrity_check;"
```

詳細備份與 WAL 說明見上方「[備份 SQLite DB](#備份-sqlite-db若使用-sqlite-backend)」。

### Fallback to JSON

若 SQLite backend 有問題，隨時可切回 json：

```bash
# 方式 A：在 .env 改回 json（或移除設定）
TRANSACTION_LOG_BACKEND=json
# 方式 B：直接刪除 .env 中的該行（未設定時預設為 json）
```

- `runtime/rip.db` **不需要刪除**（切回 json 後 RIP 不會讀取它）。
- 舊 JSON history（`rename_transactions.json` / `move_transactions.json`）立即恢復可用。
- 若要完全重建 SQLite DB（例如 DB 損壞），確認無 RIP process 後：

```bash
rm -f runtime/rip.db runtime/rip.db-wal runtime/rip.db-shm
# 下次啟用 sqlite backend 時，schema 會自動重建（initialize_sqlite_schema）
```

### runtime lock 與 SQLite 的關係

| 機制 | 層次 | 用途 |
|------|------|------|
| `runtime/rip.lock`（fcntl.flock） | RIP operator workflow 層 | 防止多個 RIP process 同時執行 destructive action |
| SQLite WAL mode | SQLite DB 層 | 提供 DB 層讀寫並發安全（允許多 reader / 單 writer） |

- 兩者**不互相取代**，同時存在。
- `rip.lock` 保護整個 operator workflow（從 mock_line 指令到 filesystem rename/move）。
- SQLite WAL 保護 DB 檔案層的讀寫一致性。
- Destructive commands 仍由 `rip.lock` 全程保護，SQLite backend 不改變此行為。

### WSL2 / Filesystem 注意事項

- SQLite WAL mode 在 `/mnt/c` 或 Windows DrvFs/NTFS 路徑可能出現 locking 問題（已知 SQLite 限制）。
- **建議**：`RUNTIME_DIR` 放在 Linux filesystem（WSL home 底下的 repo `runtime/`）。
- 若必須放在 `/mnt/c`，請在正式使用前測試 backup / restore / concurrent behavior。

---

## JSON → SQLite Migration（Phase 19J）

> **Status**：Available（v0.7.7-alpha Phase 19J）。這是一次性的手動工具，不會自動執行。

### 何時需要 migration

當您決定將 `TRANSACTION_LOG_BACKEND` 切換到 `sqlite`，且希望過去的 JSON transaction history（`rename_transactions.json` / `move_transactions.json`）也能在 SQLite backend 下可見時，才需要執行 migration。

若您只是測試 SQLite backend，且不需要舊 JSON history，可以直接切換 `TRANSACTION_LOG_BACKEND=sqlite`，不需要 migration。

**Migration 前請注意**：

- `approvals.json` **不在** migration scope，approval store 仍使用 JSON
- SQLite prune（`prune_transactions()`）**尚未實作**，migration 後 SQLite 沒有 prune 功能
- Approval SQLite backend **尚未實作**

### Migration 前備份（必做）

```bash
# 備份整個 runtime/ 目錄
cp -rp runtime/ runtime_backup_$(date +%Y%m%d_%H%M%S)/

# 確認 RIP 沒有其他 process 在執行
ps aux | grep -E "rip|mock_line" | grep -v grep
```

### Step 1：Dry-run 預覽（不寫入任何資料）

```bash
poetry run python scripts/migrate_transaction_logs.py --dry-run
```

預設行為即為 dry-run；不加 `--apply` 不會寫入 DB。

範例輸出：

```
RIP transaction log migration — DRY-RUN
  source dir : runtime
  db path    : runtime/rip.db
  [rename] DRY-RUN: migrated=3  already_present=0  corrupted=0  skipped=0
  [move]   DRY-RUN: migrated=5  already_present=0  corrupted=0  skipped=0

(Dry-run: no changes written. Use --apply to perform migration.)
```

若 `rename_transactions.json` / `move_transactions.json` 不存在：

```
  [rename] DRY-RUN: source not found — skipped (runtime/rename_transactions.json)
```

這是正常行為（沒有要 migrate 的資料）。

### Step 2：執行 migration（--apply --backup）

```bash
poetry run python scripts/migrate_transaction_logs.py --apply --backup
```

`--apply` 才會真正寫入 SQLite DB；`--backup` 會在寫入前備份 JSON source files 與現有 `rip.db`。

**重要**：`--apply` 會取得 runtime lock（`rip.lock`），期間無法同時執行其他 RIP 指令。

### 指定 source / db path（進階）

```bash
# 使用非預設路徑
poetry run python scripts/migrate_transaction_logs.py \
    --dry-run \
    --source-json-dir runtime \
    --db-path runtime/rip.db
```

### 只 migrate rename 或 move

```bash
# 只 migrate rename_transactions.json
poetry run python scripts/migrate_transaction_logs.py --apply --rename-only

# 只 migrate move_transactions.json
poetry run python scripts/migrate_transaction_logs.py --apply --move-only
```

### Step 3：驗證 migration 結果

```bash
# 驗證 SQLite DB 完整性
sqlite3 runtime/rip.db "PRAGMA integrity_check;"
# 預期輸出：ok

# 確認 transaction 筆數
sqlite3 runtime/rip.db "SELECT COUNT(*) FROM rename_transactions;"
sqlite3 runtime/rip.db "SELECT COUNT(*) FROM move_transactions;"
```

### Step 4：切換到 SQLite backend

```bash
# 在 .env 加入（或修改）
TRANSACTION_LOG_BACKEND=sqlite
```

驗證：

```bash
poetry run rip "說明"
# 確認正常回覆
```

### Rollback to JSON

若切換後遇到問題，可隨時切回 JSON：

```bash
# 在 .env 改回（或移除該行）
TRANSACTION_LOG_BACKEND=json
```

切回後：

- `rename_transactions.json` / `move_transactions.json` 的 JSON history 立即恢復可用
- `runtime/rip.db` 不需要刪除（JSON backend 不讀取它）
- 切換後新執行的 transaction 將再次寫入 JSON 檔

### Migration 安全保證

| 保證 | 說明 |
|------|------|
| JSON 原檔不被修改 | migration 對 JSON 側為純讀取，不刪除、不覆寫、不 rename |
| `approvals.json` 不受影響 | migration 完全不讀寫 approval store |
| Idempotent | 重複執行 migration 安全；已存在的 transaction 計入 already_present，不重複寫入 |
| Dry-run 預設 | 不加 `--apply` 不會建立或修改 `rip.db` |
| Runtime lock | `--apply` 期間持有 lock，防止與 `確認改名` / `確認搬移` 等指令 race |
| Corrupt entry 不擴散 | 單筆 corrupt transaction 只 skip 該筆，不影響其他 entry 的 migration |

### Exit codes

| Code | 情況 |
|------|------|
| 0 | 成功（dry-run 或 apply，包括 nothing to migrate） |
| 1 | Runtime lock busy |
| 2 | Corrupt source file / entry 且使用 `--fail-on-corrupt` |
| 3 | Unexpected DB / migration error |

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
| 升級前備份（json backend） | `cp -rp runtime/ runtime_backup_$(date +%Y%m%d_%H%M%S)/` |
| 升級前備份（sqlite backend） | `sqlite3 runtime/rip.db ".backup runtime/rip_backup_$(date +%Y%m%d_%H%M%S).db"` |
| 升級 | `git pull && poetry install && poetry run pytest -q` |
| Lock busy 且無 process 在跑 | `rm runtime/rip.lock && poetry run rip "<指令>"` |
| 確認 runtime 未進 Git | `git ls-files runtime/` |
| 驗證 JSON 完整性 | `python -m json.tool runtime/approvals.json` |
| 驗證 SQLite DB 完整性 | `sqlite3 runtime/rip.db "PRAGMA integrity_check;"` |
| 啟用 SQLite backend | `.env` 中加入 `TRANSACTION_LOG_BACKEND=sqlite` |
| 切回 JSON backend | `.env` 中改為 `TRANSACTION_LOG_BACKEND=json` 或刪除該行 |
| 重建損壞的 SQLite DB | `rm -f runtime/rip.db runtime/rip.db-wal runtime/rip.db-shm` |
| Migration dry-run | `poetry run python scripts/migrate_transaction_logs.py --dry-run` |
| Migration 執行 | `poetry run python scripts/migrate_transaction_logs.py --apply --backup` |
| Migration JSON report | `poetry run python scripts/migrate_transaction_logs.py --dry-run --json-report` |
