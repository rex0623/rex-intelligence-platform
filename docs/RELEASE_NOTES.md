# Rex Intelligence Platform（RIP）Release Notes

---

## v0.7.8-alpha

**Phase 19H / 19J / 19L — SQLite Operator Docs / Migration Script / Prune Implementation Release Checkpoint**

---

### Purpose

v0.7.8-alpha 收斂 Phase 19H（Operator Docs for Experimental SQLite Backend）、Phase 19J（JSON → SQLite Transaction Log Migration Script）、Phase 19L（SQLite `prune_transactions()` Implementation）三個 phase 的工作，確認 SQLite experimental backend 已具備 prune 支援，JSON backend 預設行為完全不變，並為後續 Approval SQLite backend 建立穩定基準。

---

### Highlights

- **Operator Docs — Experimental SQLite Backend（Phase 19H）** — `docs/OPERATOR_DEPLOYMENT.md` 全面補充 experimental SQLite backend 的 operator 說明：啟用方式、影響範圍表（json vs sqlite）、No migration warning、WAL / busy_timeout / runtime lock 說明、SQLite backup / restore / integrity check 流程、WSL2 注意事項、快速參考條目。
- **JSON → SQLite Migration Script（Phase 19J）** — 新增 `app/core/transaction_log_migration.py`（migration library）與 `scripts/migrate_transaction_logs.py`（CLI wrapper）；idempotent migration；dry-run 預設；argparse CLI 支援 `--apply` / `--backup` / `--fail-on-corrupt` / `--json-report`；lock-aware（`acquire_runtime_lock()`）；WAL-safe backup；JSON 原檔 read-only。
- **SQLite `prune_transactions()` Implementation（Phase 19L）** — `SqliteRenameTransactionLog.prune_transactions()` 與 `SqliteMoveTransactionLog.prune_transactions()` 完整實作，對齊 JSON backend 行為：rename prune 支援 `max_transactions` / `max_age_days` / rollbackable protection；move prune 支援 `older_than_days` / `dry_run` / 3-state（protected / retained / pruned）；`corrupted_count` 恆為 0（SQLite schema 保證 validity）；`prune_transactions()` 不進 Protocol（簽名相異）。
- **JSON backend 完全不變（v0.7.7-alpha → v0.7.8-alpha 升級影響為零）** — `TRANSACTION_LOG_BACKEND` 預設 "json"；不建立 `runtime/rip.db`；`rename_transactions.json` / `move_transactions.json` schema 不變；所有現有 operator 操作行為與 v0.7.7-alpha 完全相同。

---

### SQLite Backend 重要限制（v0.7.8-alpha）

| 限制 | 說明 |
|------|------|
| No migration（自動） | 切換到 `sqlite` 後，現有 JSON transaction history 不可見；請使用 `scripts/migrate_transaction_logs.py` 手動 migrate |
| No Approval SQLite | `ApprovalManager` / `JsonApprovalStore` 不變，approval 仍存 JSON |
| Experimental only | 不建議在有歷史資料的環境切換 sqlite，除非先執行 migration |

---

### Test Count

| 里程碑 | Tests |
|--------|-------|
| v0.7.7-alpha（Phase 19G Tag） | 816 |
| Phase 19J（Migration Script） | 855（+39）|
| Phase 19L（SQLite Prune） | 878（+23）|
| **v0.7.8-alpha** | **878** |

---

### Final Regression（v0.7.8-alpha readiness）

| 指令 | 結果 |
|------|------|
| `poetry check` | All set! |
| `poetry run pytest -q` | 878 passed |
| `poetry build` | `rex_intelligence_platform-0.1.0.tar.gz` ✅ |
| `poetry run rip "說明"` | 正常回覆指令說明 ✅ |
| GitHub Actions CI | #17（pending — Release Checkpoint Prepared）|

---

### Non-Goals（v0.7.8-alpha）

- 不實作 Approval SQLite backend（`ApprovalManager` / `JsonApprovalStore` 不變）
- 不切換 default backend 至 sqlite
- 不修改 destructive command regex
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`
- 不修改 runtime JSON schema

---

### Tag Status（v0.7.8-alpha）

Release Checkpoint Prepared — tag 尚未建立。等待 GitHub Actions CI #17 green 後建立 annotated tag。

---

## v0.7.7-alpha

**Phase 19B–19D — Optional SQLite Transaction Log Backend Release Checkpoint**

---

### Purpose

v0.7.7-alpha 收斂 Phase 19B（Experimental SQLite Transaction Log Backend）與 Phase 19D（Optional Backend Factory / TRANSACTION_LOG_BACKEND Integration）兩個 phase 的工作，確認 optional SQLite backend 可正確選擇、JSON backend 預設行為完全不變，並為後續 migration / prune 實作建立穩定基準。

---

### Highlights

- **Experimental SQLite Transaction Log Backend（Phase 19B）** — `app/core/sqlite_transaction_log.py`：`SqliteRenameTransactionLog` / `SqliteMoveTransactionLog` 兩個 class 滿足 Phase 18E 定義的 `@runtime_checkable` Protocol（PEP 544 structural subtyping）；5 tables + 2 indexes DDL；WAL / foreign keys / busy timeout PRAGMA；ON DELETE CASCADE；AUTOINCREMENT action 順序保留；Python stdlib sqlite3 only（無新 dependency）；`prune_transactions()` 明確 raise `NotImplementedError`（experimental 限制）。
- **Optional Backend Factory + TRANSACTION_LOG_BACKEND（Phase 19D）** — `app/core/config.py` 新增 `TRANSACTION_LOG_BACKEND: Literal["json", "sqlite"] = "json"`（預設 "json"）與 `get_sqlite_db_path()`；新增 `app/core/transaction_log_factory.py`（`make_rename_transaction_log()` / `make_move_transaction_log()`）；本機 import 設計確保 backend="json" 時不 import SQLite module；`app/folder_intelligence/approval_bridge.py` `default_move_transaction_log()` 改用 factory 路由；`scripts/mock_line.py` 三個 rename log 實例化改用 `make_rename_transaction_log()`。
- **JSON backend 完全不變（v0.7.6-alpha → v0.7.7-alpha 升級影響為零）** — `TRANSACTION_LOG_BACKEND` 預設 "json"；不建立 `runtime/rip.db`；`rename_transactions.json` / `move_transactions.json` schema 不變；所有現有 operator 操作行為與 v0.7.6-alpha 完全相同。

---

### SQLite Backend 重要限制（v0.7.7-alpha）

| 限制 | 說明 |
|------|------|
| No migration | 切換到 `sqlite` 後，現有 JSON transaction history 完全不可見（`預覽回滾改名` / `回滾改名` 等查不到舊 transaction）；migration script 延後至 Phase 19H |
| No SQLite prune | `prune_transactions()` 在 SQLite backend raise `NotImplementedError`；延後至 Phase 19I |
| No Approval SQLite | `ApprovalManager` / `JsonApprovalStore` 不變，approval 仍存 JSON |
| Experimental only | 不建議在有歷史資料的環境切換 sqlite，除非接受歷史不可見 |

---

### Test Count

| 里程碑 | Tests |
|--------|-------|
| v0.7.6-alpha | 765 |
| Phase 19B | 794（+29）|
| Phase 19D | 816（+22）|
| Phase 19G（Tag Confirmation） | +0 → 816（純文件）|
| **v0.7.7-alpha** | **816** |

---

### Final Regression（v0.7.7-alpha readiness）

| 指令 | 結果 |
|------|------|
| `poetry check` | All set! |
| `poetry run pytest -q` | 816 passed |
| `poetry build` | `rex_intelligence_platform-0.1.0.tar.gz` ✅ |
| `poetry run rip "說明"` | 正常回覆指令說明 ✅ |
| GitHub Actions CI | #11 green（before checkpoint）|

---

### Non-Goals（v0.7.7-alpha）

- 不做 migration script（JSON → SQLite；延後至 Phase 19H）
- 不實作 SQLite prune_transactions（延後至 Phase 19I）
- 不導入 `ApprovalStoreProtocol` / `SqliteApprovalStore`
- 不更新 `docs/OPERATOR_DEPLOYMENT.md`（延後至 Phase 19G）
- 不切換 default backend 至 sqlite
- 不修改 destructive command regex
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`
- 不修改 runtime JSON schema

---

### Tag Confirmation（Phase 19G）

| 欄位 | 值 |
|------|----|
| tag | `v0.7.7-alpha` |
| tag object | `80d234676bdacbc8b5dafefa427f59289e471b81` |
| target commit | `86c3b9b3d938b574c5d5bdcda4519604476d0733` |
| remote tag pushed | ✅ yes |

---

### Commits Since v0.7.6-alpha

| Commit | Phase | 說明 |
|--------|-------|------|
| `（Phase 19B commit）` | 19B | feat(transactions): add experimental SQLite transaction log backend |
| `26c47d5` | 19D | feat(transactions): add optional SQLite backend factory |
| `86c3b9b` | 19F | docs(release): prepare v0.7.7-alpha release checkpoint |

---

### Recommended Next

- **Phase 19I** — SQLite Migration Script（`scripts/migrate_transaction_logs.py`）
- **Phase 19J** — SQLite Prune Implementation

---

## Phase 19J — SQLite Transaction Log Migration Script（2026-06-14）

**目標**：新增 JSON → SQLite transaction log migration library 與 CLI wrapper。不修改 application code，不做 SQLite prune，不改 default backend，不自動執行 migration。

---

### 新增

- **`app/core/transaction_log_migration.py`**（新增）：
  - `MigrationResult` dataclass
  - `_load_json_strict(path)` — 嚴格讀取，明確區分 file_not_found / corrupt_json / invalid_structure
  - `migrate_rename_transactions()` / `migrate_move_transactions()` / `migrate_all()`
  - 預設 `dry_run=True`；`dry_run=False` 才寫入 SQLite
  - Idempotency：`transaction_id` 已存在時 skip（`already_present_count++`），不覆蓋
  - JSON 原檔永遠不修改（read-only on JSON side）
  - Pydantic `model_validate()` 驗證每筆 entry；validation error → skip + `corrupted_count++`
  - 不使用 `shutil`（符合 AST safety test 限制）
- **`scripts/migrate_transaction_logs.py`**（新增）：
  - CLI：`--dry-run`（預設）/ `--apply` / `--backup` / `--source-json-dir` / `--db-path` / `--rename-only` / `--move-only` / `--fail-on-corrupt` / `--json-report`
  - `--apply` 取得 runtime lock；lock busy → exit 1
  - Backup（`--backup --apply`）：JSON 用 `.bak_YYYYMMDD_HHMMSS`；DB 用 `sqlite3.backup()`
  - Exit codes：0 / 1（lock busy）/ 2（corrupt + fail_on_corrupt）/ 3（unexpected error）
- **`tests/test_transaction_log_migration.py`**（新增）：39 tests（816 → **855**）
- **`docs/OPERATOR_DEPLOYMENT.md`**（修改）：新增 `## JSON → SQLite Migration（Phase 19J）` section

### Non-Goals（Phase 19J）

- 不修改 `TRANSACTION_LOG_BACKEND` 預設值（仍為 "json"）
- 不做 SQLite prune（`prune_transactions()` 仍 raise NotImplementedError）
- 不做 Approval SQLite migration / backend
- 不新增 mock_line migration 指令
- 不做自動 migration（migration 永遠需要 operator 明確執行）
- 不修改 runtime lock / destructive command regex
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`

### Test Count

| 里程碑 | Tests |
|--------|-------|
| v0.7.7-alpha | 816 |
| Phase 19J（migration script） | +39 → **855** |

---

## Phase 19H — Operator Docs for Experimental SQLite Backend（2026-06-14）

**目標**：更新 `docs/OPERATOR_DEPLOYMENT.md`，為 optional SQLite transaction log backend 補充完整 operator 文件。不修改任何 application code、不做 migration、不做 prune 實作。

---

### 新增 / 修改

- **`docs/OPERATOR_DEPLOYMENT.md`**（修改）：
  - 文件版本更新至 v0.7.7-alpha（Phase 19H）
  - 概覽補充 optional SQLite backend 說明與文件連結
  - `.env` 範例新增 `TRANSACTION_LOG_BACKEND`（含警告注釋）
  - `RUNTIME_DIR 說明` 新增 `rip.db` / `rip.db-wal` / `rip.db-shm`，WSL2 filesystem 注意事項
  - `runtime/` directory tree 補充 `rip.db` / `rip.db-wal` / `rip.db-shm`（sqlite-only 標注）
  - 新增 `### rip.db / rip.db-wal / rip.db-shm` subsection（含 WAL 說明）
  - 備份 section 新增：SQLite hot backup（`sqlite3 .backup`）、WAL 注意事項、DB integrity check
  - 還原 section 拆分為 JSON restore（預設）與 SQLite restore 兩個 subsection
  - 新增 `## Experimental SQLite Transaction Log Backend` 獨立 section，含：
    - 啟用方式（`.env` 設定 / 臨時環境變數）
    - 影響範圍表（json vs sqlite backend 對照）
    - ⚠️ No migration script warning（舊 JSON history 不可見、影響的 operator 操作）
    - ⚠️ SQLite `prune_transactions()` 尚未實作說明
    - SQLite backup 指令（`sqlite3 .backup`）
    - Fallback to JSON 流程（`rm -f rip.db*` 後 unset / 刪除 .env 設定）
    - runtime lock 與 SQLite WAL 的關係說明（table）
    - WSL2 / Filesystem 注意事項（DrvFs / NTFS / `/tmp` 建議）
  - 快速參考 table 新增：SQLite backup、integrity check、啟用、切回 JSON、重建 DB 條目

---

### Non-Goals（Phase 19H）

- 不修改 application code / tests / pyproject.toml / poetry.lock / ci.yml
- 不做 migration script（JSON → SQLite；延後 Phase 19I）
- 不實作 SQLite `prune_transactions()`（延後 Phase 19J）
- 不修改 `TRANSACTION_LOG_BACKEND` 預設值（仍為 "json"）
- 不建立 runtime/rip.db
- 不建立 git tag / 不 push

---

## v0.7.6-alpha

**Phase 18B–18G — Persistence Refactors Release Checkpoint**

---

### Purpose

v0.7.6-alpha 收斂 Phase 18B / 18C / 18E 三個 persistence refactor 工作至一個正式 release checkpoint，確認 JSON backend 穩定、所有架構重構已 green CI，並為未來 SQLite optional backend 鋪好型別接縫（Protocol）。

---

### Highlights

- **`JsonApprovalStore`（Phase 18B）** — `app/approvals/store.py`：stateless JSON I/O helper，從 `ApprovalManager` 提取 `load` / `save` static method；`approvals.json` schema / `self.store_path` / `self._store` 不變；所有 monkeypatch 測試零改動。
- **Shared JSON transaction log I/O（Phase 18C）** — `app/core/json_log_io.py`：`read_json_log` / `write_json_log` / `ensure_utc_aware` 三個 module-level helper，提取 `RenameTransactionLog` / `MoveTransactionLog` 的重複 JSON 邏輯；Move prune 的 corrupt JSON early return 保留；AST 安全測試全數通過。
- **Transaction log Protocols（Phase 18E）** — `app/core/transaction_log_protocol.py`：`RenameTransactionLogProtocol` / `MoveTransactionLogProtocol` 兩個 `@runtime_checkable` structural Protocol（PEP 544）；executor / approval_bridge 型別標注更新；`prune_transactions()` 不納入 Protocol（Rename / Move signature 發散）。
- **SQLite Reconnaissance（Phase 18A / 18D / 18F）** — 三個純偵察 phase（no commit）：SQLite persistence option 設計完成，建議 Route A（transaction logs only），實作延後至 v0.8.0-alpha。

---

### Test Count

| 里程碑 | Tests |
|--------|-------|
| v0.7.5-alpha | 726 |
| Phase 18B | 737（+11） |
| Phase 18C | 757（+20） |
| Phase 18E | 765（+8） |
| Phase 18H（Tag Confirmation） | +0 → 765（純文件）|
| **v0.7.6-alpha** | **765** |

---

### Final Regression（v0.7.6-alpha readiness）

| 指令 | 結果 |
|------|------|
| `poetry check` | All set! |
| `poetry run pytest -q` | 765 passed |
| `poetry build` | `rex_intelligence_platform-0.1.0.tar.gz` ✅ |
| `poetry run rip "說明"` | 正常回覆指令說明 ✅ |
| GitHub Actions CI | #7 green（before checkpoint） |

---

### Non-Goals（v0.7.6-alpha）

- 不導入 SQLite backend
- 不建立 `runtime/rip.db`
- 不新增 `TRANSACTION_LOG_BACKEND` / `APPROVAL_BACKEND` flag
- 不做 migration script
- 不修改 runtime lock 行為
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`
- 不修改 destructive command regex
- 不修改 `approvals.json` / `rename_transactions.json` / `move_transactions.json` schema

---

### Tag Confirmation（Phase 18H）

| 欄位 | 值 |
|------|----|
| tag | `v0.7.6-alpha` |
| tag object | `55d560580433d4026609d33fdd87765a76a73d22` |
| target commit | `8299b9f3cbb3b184671cd885d32ddd8e1d3f8acb` |
| remote tag pushed | ✅ yes |

---

### Commits Since v0.7.5-alpha

| Commit | Phase | 說明 |
|--------|-------|------|
| `47a4128` | 18B | refactor(approvals): extract JSON approval store |
| `31c1037` | 18C | refactor(transactions): extract shared JSON log IO |
| `c5434ff` | 18E | refactor(transactions): define transaction log protocols |

---

## Post-v0.7.6-alpha Development

### Phase 19D — Optional SQLite Transaction Log Backend Integration（2026-06-14）

**目標**：將 Phase 19B 的 SQLite backend 接入 production runtime，以 `TRANSACTION_LOG_BACKEND` 設定旗標選擇。JSON 仍是預設值，SQLite 為 experimental opt-in，不做 migration。

**新增 / 修改：**
- `app/core/config.py` — `TRANSACTION_LOG_BACKEND: Literal["json", "sqlite"] = "json"` + `get_sqlite_db_path()`
- `app/core/transaction_log_factory.py`（新增）— `make_rename_transaction_log()` / `make_move_transaction_log()`；本機 import 確保 backend="json" 時不 import SQLite module
- `app/folder_intelligence/approval_bridge.py` — `default_move_transaction_log()` 改用 factory 路由
- `scripts/mock_line.py` — 三個 rename log 實例化改用 `make_rename_transaction_log()`
- `tests/test_transaction_log_factory.py`（新增）— 22 tests（794 → 816）

**Non-Goals（Phase 19D）：**
- JSON 仍是 default / production path（`TRANSACTION_LOG_BACKEND` 預設 "json"）
- 不修改 `ApprovalManager` / `JsonApprovalStore`
- 不做 migration script / SQLite prune / `ApprovalStoreProtocol`
- 不修改 runtime lock / destructive command regex
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`

**Test Count：**

| 里程碑 | Tests |
|--------|-------|
| v0.7.6-alpha | 765 |
| Phase 19B | 794（+29）|
| Phase 19D | 816（+22）|

---

### Phase 19B — Experimental SQLite Transaction Log Backend（2026-06-14）

**目標**：為 Phase 18E Protocol 提供第二個實作，驗證 Protocol 合約。SQLite backend 不接 default runtime。

**新增：**
- `app/core/sqlite_transaction_log.py` — `SqliteRenameTransactionLog` / `SqliteMoveTransactionLog` + connection helper + schema DDL
- `tests/test_sqlite_transaction_log.py` — 29 tests（765 → 794）

**SQLite Schema（transaction logs only）：**

| Table | 說明 |
|-------|------|
| `schema_version` | 版本追蹤（1 row，version=1）|
| `rename_transactions` | `transaction_id PK / plan_id / created_at ISO text` |
| `rename_transaction_actions` | `AUTOINCREMENT id / transaction_id FK CASCADE / action fields / status CHECK` |
| `move_transactions` | 鏡像 rename_transactions |
| `move_transaction_actions` | 鏡像 rename_transaction_actions |

**Non-Goals（Phase 19B）：**
- 不接 default runtime backend
- 不新增 TRANSACTION_LOG_BACKEND flag
- 不修改 config.py / executor / approval_bridge
- 不做 migration script
- 不實作 `prune_transactions`（SQLite backend raise NotImplementedError）
- 不導入 SqliteApprovalStore
- 不建立 runtime/rip.db
- 不新增 pyproject.toml dependency（stdlib sqlite3）

**Test Count：**

| 里程碑 | Tests |
|--------|-------|
| v0.7.6-alpha | 765 |
| Phase 19B | 794（+29）|

---

## Post-v0.7.5-alpha Development

### Phase 18E — Transaction Log Protocol Definition（2026-06-14）

- **新增 `app/core/transaction_log_protocol.py`**：兩個 `@runtime_checkable` structural Protocol（PEP 544）：`RenameTransactionLogProtocol` / `MoveTransactionLogProtocol`，各含 5 個方法（`save_transaction` / `load_transaction` / `list_transactions` / `update_transaction` / `mark_transaction_actions`）。
- **executor / approval_bridge 型別標注更新**：4 個檔案（`app/filename/executor.py`、`app/filename/approval_bridge.py`、`app/folder_intelligence/executor.py`、`app/folder_intelligence/approval_bridge.py`）的 `transaction_log` 參數型別改為對應的 Protocol；runtime 行為完全不變。
- **prune_transactions() 不納入 Protocol**：Rename / Move 的 prune signature 發散（参數名、回傳型別均不同），不強制統一，保留各自 concrete class 的 prune API。
- **`rename_transactions.json` / `move_transactions.json` schema 不變**：`{"transactions": [...]}` wrapper；transaction_id / plan_id / created_at / actions 欄位不變。
- **JSON backend 仍是唯一 backend**；不導入 SQLite，不建立 DB 檔案，不修改 runtime lock、pyproject.toml、poetry.lock。
- **循環 import 處理**：`transaction_log_protocol.py` 使用 `from __future__ import annotations` + `TYPE_CHECKING` guard，避免 `folder_intelligence.__init__` → `approval_bridge` → `transaction_log_protocol` 循環；`isinstance()` 行為完全不受影響。
- **新增 8 個測試**（`tests/test_transaction_log_protocol.py`）：757 → 765 passing。
- Phase 18D（Protocol / SQLite Reconnaissance）→ Phase 18E（Protocol Definition）→ Phase 18F（SQLite backend，未來）。

---

### Phase 18C — Shared JSON Transaction Log I/O Extraction（2026-06-14）

- **新增 `app/core/json_log_io.py`**：`read_json_log` / `write_json_log` / `ensure_utc_aware` 三個 module-level helper function，提取 `RenameTransactionLog` 和 `MoveTransactionLog` 中完全相同的 JSON I/O 邏輯（byte-for-byte duplicate）。
- **`RenameTransactionLog._read()` / `_write()` 委派重構**：改為 thin wrapper，移除內嵌 JSON I/O 邏輯；`self._log_path` 屬性不變，現有 `._log_path.read_bytes()` 等測試存取繼續有效。
- **`MoveTransactionLog._read()` / `_write()` 同上**：Move prune 的整檔 corrupt JSON 特殊 early return（`corrupted_count=1`, `dry_run` 保留, 不覆寫原檔）保留不變。
- **`rename_transactions.json` / `move_transactions.json` schema 不變**：`{"transactions": [...]}` wrapper；transaction_id / plan_id / actions 欄位不變。
- **prune 行為完全不變**：rename prune（max_transactions / max_age_days）；move prune（older_than_days / dry_run / protected / retained / corrupted 三態）；rollback safety（success action 永不被 prune）。
- **AST 安全測試全通過**：move prune 不呼叫 rename/move/replace/mkdir 的限制繼續有效。
- **新增 20 個測試**（`tests/test_json_log_io.py`）：737 → 757 passing。
- Phase 18B（Approval JSON Store）→ Phase 18C（Transaction Log I/O）→ Phase 18D（Protocol + SQLite，未來）。

---

### Phase 18B — Approval JSON Store Extraction（2026-06-14）

- **新增 `JsonApprovalStore`**（`app/approvals/store.py`）：stateless JSON I/O helper，提供 `load(store_path)` 與 `save(store_path, data)` static method，將 ApprovalManager 的 JSON 序列化邏輯集中至單一模組。
- **`ApprovalManager` 委派重構**：`_load_store` / `_save_store` 改為委派 `JsonApprovalStore`；`self.store_path` 和 `self._store` 屬性不變，所有現有 monkeypatch 測試零改動。
- **approvals.json schema 不變**：仍為 array of approval dicts；payload 內 `execution_status` / `executed_at` / `execution_transaction_id` 保留。
- **新增 11 個測試**（`tests/test_approval_store.py`）：726 → 737 passing。
- **不導入 SQLite**；`rename_transactions.json` / `move_transactions.json` 及對應 transaction log 類別不變。
- Phase 18A（Reconnaissance）→ Phase 18B（JSON Store Extraction）→ Phase 18C（Protocol + SQLite，未來）。

---

## v0.7.5-alpha

**Phase 17A–17I — console_scripts Entry Point / Runtime Lock / Operator Runbook / Preflight Validation / Packaging Metadata Modernization / GitHub Actions CI / CI Result Confirmation / Release Tag Readiness / Tag Confirmation**

---

### Highlights

- **console_scripts entry point** — `rip = "scripts.mock_line:main"`；`poetry run rip "..."` 可替代 `poetry run python scripts/mock_line.py "..."`；向下相容（17A）
- **Runtime Lock / Concurrency Guard** — `fcntl.flock` advisory lock on `runtime/rip.lock`；防止多 process 同時寫入 runtime state；help / preview 不受鎖影響（17B）
- **Operator Deployment Runbook** — `docs/OPERATOR_DEPLOYMENT.md`；涵蓋安裝 / 設定 / backup / restore / upgrade / runtime_lock_busy 處理（17C）
- **Operator Preflight Validation** — `app/core/preflight.py`；safe preflight（low-write）；7 個 check；不取 lock / 不建 JSON state（17D）
- **Packaging Metadata Modernization** — PEP 621 `[project]` 格式；`poetry check` **All set!**；PyMuPDF 正式納入 locked runtime dependency（17E）
- **GitHub Actions CI** — `.github/workflows/ci.yml`；push / pull_request to main；Python 3.12 / ubuntu-22.04 / Poetry 2.4.1；726 tests（17F）
- **CI #1 Run Confirmed** — commit 9c0173c；34s；726 passed；poetry check All set；build 成功（17G）
- **Release Tag Readiness** — v0.7.5-alpha 文件準備完成；final regression 通過（17H）
- **Tag Confirmed** — v0.7.5-alpha tag 建立並 push 至 origin；commit d96f657；working tree clean（17I）

---

### Tag Confirmed（Phase 17I）

| 項目 | 結果 |
|------|------|
| tag | `v0.7.5-alpha` |
| commit | `d96f657` |
| remote tag pushed | ✅ yes |
| working tree | clean |

---

### Final Regression（v0.7.5-alpha tag 前）

| 指令 | 結果 |
|------|------|
| `poetry check` | All set! |
| `poetry run pytest -q` | 726 passed |
| `poetry build` | `rex_intelligence_platform-0.1.0.tar.gz` ✅ |
| `poetry run rip "說明"` | 正常回覆指令說明 ✅ |

---

### Package Artifact（v0.7.5-alpha）

**`poetry check` 結果**：**All set!**（Phase 17E PEP 621 migration 後，0 warnings）

**`poetry build` 結果**：成功 ✅

```
Building rex-intelligence-platform (0.1.0)
Built rex_intelligence_platform-0.1.0.tar.gz
Built rex_intelligence_platform-0.1.0-py3-none-any.whl
```

**注意**：artifact 版本為 `0.1.0`（pyproject.toml packaging version），非 RIP release version v0.7.5-alpha。RIP release source of truth 為 git tag / release docs。

---

### Tagging Instructions（v0.7.5-alpha）— ✅ Completed（Phase 17I）

**以下指令已於 Phase 17I 人工執行完成。**

```bash
# 1. 確認 working tree 乾淨
git status --short          # ✅ 輸出為空

# 2. 確認所有測試通過
poetry run pytest -q        # ✅ 726 passed

# 3. 確認 CI run green（GitHub Actions）
# ✅ CI #1 commit 9c0173c，34s，726 passed

# 4. 建立本機 annotated tag
git tag -a v0.7.5-alpha -m "RIP v0.7.5-alpha"   # ✅ 已執行

# 5. 確認 tag
git show v0.7.5-alpha                            # ✅ tag 指向 d96f657

# 6. 推送 tag
git push origin v0.7.5-alpha                    # ✅ 已 push
```

> tag `v0.7.5-alpha` dereferences to commit `d96f657`（`git ls-remote --tags origin v0.7.5-alpha^{}` 驗證）。

---

### Test Count（v0.7.5-alpha）

| Phase | Tests |
|-------|-------|
| 17A（console_scripts entry point） | +3 → 693 |
| 17B（Runtime Lock / Concurrency Guard） | +16 → 709 |
| 17C（Operator Deployment Runbook） | +0 → 709（純文件）|
| 17D（Operator Preflight Validation） | +17 → 726 |
| 17E（Packaging Metadata Modernization） | +0 → 726 |
| 17F（GitHub Actions CI） | +0 → 726 |
| 17G（CI Result Confirmation） | +0 → 726 |
| 17H（Release Tag Readiness） | +0 → 726（純文件）|
| 17I（Tag Confirmation） | +0 → 726（純文件 tag confirmation）|

---

## v0.7.4-alpha

**Phase 16E–17G — Release Candidate Stabilization / Final Regression / Tag Readiness / console_scripts Entry Point / Runtime Lock / Operator Runbook / Preflight Validation / Packaging Metadata Modernization / GitHub Actions CI / CI Result Confirmation**

---

### Highlights

- **Rename workflow completed** — RenamePlan → Approval → 確認改名 → Transaction log → 預覽回滾改名 → 回滾改名 → Log cleanup
- **Move workflow completed** — MovePlan → Approval → 確認搬移 → Transaction log → 預覽回滾搬移 → 回滾搬移 → Log cleanup
- **Approval workflow completed** — create / confirm / cancel；once-only guard 防止重複執行
- **Transaction log / rollback completed** — JSON persistent log；read-only preview 先確認，再明確指令回滾；once-only rollback guard
- **Runtime settings consolidated** — 所有 runtime 路徑由 `app/core/config.py` 單一來源；相對路徑錨定 SAFE_PDF_ROOT，path traversal fail-safe 拒絕
- **Operator help text completed** — 說明 / 指令說明 / help / /help；錯誤 reason 中文化；下一步提示
- **CLI smoke tests completed** — `tests/test_cli_smoke.py` 22 個測試稽核 README、packaging metadata、CLI 入口、runtime gitignore
- **Release readiness checklist completed** — 18 項 ✅ 已完成；5 項 ⬜ 待完成（16E）
- **Final regression audit completed** — `tests/test_final_regression_release_candidate.py`；文件一致性、destructive command 不變式、runtime 零污染（16F）
- **Tag readiness preparation completed** — Tagging Instructions 文件化、package artifact 建置驗證、pyproject version strategy 最終確認（16G）
- **console_scripts entry point added** — `rip = "scripts.mock_line:main"`；`poetry run rip "..."` 可替代 `poetry run python scripts/mock_line.py "..."`；舊用法向下相容（17A）
- **Runtime Lock / Concurrency Guard** — `fcntl.flock` advisory lock on `runtime/rip.lock`；防止多 process 同時寫入 runtime state；lock busy 立即回覆提示；help / preview 不受鎖影響（17B）
- **Operator Deployment Runbook** — `docs/OPERATOR_DEPLOYMENT.md`；涵蓋安裝 / 設定（.env / SAFE_PDF_ROOT / RUNTIME_DIR）/ smoke test / runtime 目錄 / 備份 / 還原 / 升級 / runtime_lock_busy 處理 / Git hygiene（17C）
- **Operator Preflight Validation** — `app/core/preflight.py`；safe preflight（low-write）；7 個 check（Python 版本 / fcntl / SAFE_PDF_ROOT / RUNTIME_DIR writable / git hygiene / pyproject）；不取 lock / 不建 JSON state；`tests/test_operator_preflight.py`（17 tests）（17D）
- **Packaging Metadata Modernization** — `pyproject.toml` 遷移至 PEP 621 `[project]` 標準格式；消除所有 6 個 `poetry check` deprecation warnings；`poetry check` 結果：**All set!**；runtime dependencies PEP 508 等價轉換；**PyMuPDF is now declared as a locked runtime dependency for PDF analysis workflows**（`pymupdf>=1.27.2,<1.28.0`，先前僅手動安裝）；package version 維持 0.1.0（17E）
- **GitHub Actions CI** — `.github/workflows/ci.yml`；push / pull_request to main 自動觸發；Python 3.12 / ubuntu-22.04 / Poetry 2.4.1；`poetry check` + `pytest -q`（726 tests）+ `poetry run rip "說明"`（console_scripts smoke）+ `poetry build`（packaging 驗證）；venv cache keyed on `poetry.lock`（17F）
- **CI #1 Run Confirmed** — commit 9c0173c；duration 34s；726 passed；poetry check All set；build 成功；PyMuPDF 在 clean ubuntu-22.04 環境正常安裝；console_scripts entry point 驗證通過（17G）

---

### Safety Guarantees

| 保證 | 說明 |
|------|------|
| Planning 指令不會改動檔案 | 「整理檔名」「整理資料夾」等只產生計畫（dry-run），不操作 filesystem |
| Preview 指令純讀取 | 「預覽回滾改名」「預覽回滾搬移」只查詢 log，不 rollback、不改檔案、不寫 log（byte-level 驗證） |
| Destructive 指令需 full match | 四個執行/回滾指令 regex 全數 `^…$` 錨定，格式不符不會執行 |
| Rename / Move logs 分離 | rename commands 只作用 rename log；move commands 只作用 move log（互不干擾） |
| Runtime JSON 不進 Git | `runtime/approvals.json`、`runtime/rename_transactions.json`、`runtime/move_transactions.json` 均已 gitignored |
| 相對路徑錨定 SAFE_PDF_ROOT | `resolve_under_safe_root()` 防止 path traversal；逃出 root 以 `path_escapes_safe_root` fail-safe 拒絕 |
| Once-only guard | 同一 approval_id 成功執行後不可重複執行；同一 transaction_id 已全部回滾後不可重複回滾 |
| Mock LINE 不直接碰 filesystem | 所有 destructive action 一律透過 approval bridge → safe executor（AST 驗證） |
| Concurrent access guard | `fcntl.flock` on `runtime/rip.lock`；多 process 同時執行時立即回覆 lock_busy，不等待，不損毀 runtime state |

---

### Operator Commands

#### Non-destructive（不會改動任何檔案）

| 指令 | 說明 |
|------|------|
| `說明` / `指令說明` / `help` / `/help` | 顯示指令說明（zero side effects） |
| `整理檔名` | 產生改名計畫（dry-run） |
| `分析 PDF 詳細` | 分析 PDF 詳細報告 |
| `整理資料夾` / `產生搬移計畫` / `分析 PDF 並產生搬移計畫` / `產生資料夾歸檔計畫` | 產生搬移計畫（dry-run） |
| `確認 {approval_id}` | 核准計畫 + dry-run 報告，不動檔案 |
| `取消 {approval_id}` | 取消核准請求 |
| `預覽回滾改名 {transaction_id}` | 只預覽，不改檔案、不改 log |
| `預覽回滾搬移 {transaction_id}` | 只預覽，不搬檔案、不改 log |

#### Destructive — full match 才生效（會真的改動檔案）

| 指令 | 效果 |
|------|------|
| `確認改名 {approval_id}` | **真的改名**（需已核准 + 通過 preflight） |
| `回滾改名 {transaction_id}` | **真的回滾改名**（once-only） |
| `確認搬移 {approval_id}` | **真的搬移**（需已核准 + 通過 preflight） |
| `回滾搬移 {transaction_id}` | **真的回滾搬移**（once-only） |

---

### Known Limitations

- **console_scripts entry point provided（Phase 17A）** — `poetry install` 後可用 `poetry run rip "…"`；`poetry run python scripts/mock_line.py "…"` 舊用法向下相容保留。
- **JSON persistence only** — transaction log 為 JSON 檔，無資料庫；大量交易時可後續評估 SQLite。
- **pyproject.toml version（0.1.0）未對齊 RIP release version（v0.7.4-alpha）** — 方案 A 決策：packaging metadata 與 release version 分離；版本對齊（例如 0.7.4a0）留待正式 release packaging 流程（16H+）。
- **Not designed for multi-user concurrent production operation** — 無 tenant 隔離；`fcntl.flock` 只保護同機器上的 process 並發，不支援跨機器；適用於個人本機文件整理。詳見 [docs/OPERATOR_DEPLOYMENT.md](OPERATOR_DEPLOYMENT.md)。
- **pyproject version is packaging metadata, not RIP release source of truth** — `pyproject.toml` version（0.1.0）為 packaging metadata；release 版本以 PROJECT_STATUS / CHANGELOG 為準（目前 v0.7.4-alpha）。
- **Help text / command inventory 為靜態維護** — 新增指令時需手動同步 `command_help_text()` 與 README command inventory。
- **Absolute paths not anchored to SAFE_PDF_ROOT** — 相對路徑有 traversal 防護；絕對路徑依既有語意原樣使用（所有現有測試依賴此行為）。

---

### Package Artifact（Phase 16G）

**`poetry check` 結果**：**All set!**（Phase 17E PEP 621 遷移後，0 warnings）

> Phase 17E 已完成 PEP 621 migration（`[tool.poetry]` → `[project]`），消除所有 6 個 deprecation warnings。

**`poetry build` 結果**：成功 ✅

```
Building rex-intelligence-platform (0.1.0)
Built rex_intelligence_platform-0.1.0.tar.gz
Built rex_intelligence_platform-0.1.0-py3-none-any.whl
```

| Artifact | 路徑 | 是否 committed |
|----------|------|----------------|
| sdist | `dist/rex_intelligence_platform-0.1.0.tar.gz` | ❌（dist/ 已 gitignored） |
| wheel | `dist/rex_intelligence_platform-0.1.0-py3-none-any.whl` | ❌（dist/ 已 gitignored） |

**注意**：artifact 版本為 `0.1.0`（pyproject.toml packaging version），非 RIP release version v0.7.4-alpha。版本對齊（例如 `0.7.4a0`）留待正式 release packaging 決策。

---

### Tagging Instructions（Phase 16G）

**本 phase 不自動建立 git tag，亦不自動 push。**

Tag 流程需由人工確認後執行：

#### 前置條件確認

```bash
# 1. 確認 working tree 乾淨
git status --short          # 輸出應為空

# 2. 確認所有測試通過
poetry run pytest -q        # 應顯示 709+ passed

# 3. 確認版本一致（四份文件均含 v0.7.4-alpha）
grep "v0.7.4-alpha" README.md docs/PROJECT_STATUS.md CHANGELOG.md docs/RELEASE_NOTES.md

# 4. 確認 runtime 無 git 追蹤
git ls-files runtime/        # 輸出應為空
```

#### 建立本機 annotated tag

```bash
git tag -a v0.7.4-alpha -m "RIP v0.7.4-alpha"
```

#### 確認 tag

```bash
git show v0.7.4-alpha
```

#### 推送 tag（人工確認後執行）

```bash
git push origin v0.7.4-alpha
```

> **重要**：push tag 為不可逆操作，請確認以上前置條件全數通過後再執行。

---

### Test Count

| Phase | Tests |
|-------|-------|
| 16D 前（Phase 1–16C） | 606 |
| 16D（Packaging smoke） | +22 → 628 |
| 16E（Release readiness） | +20 → 648 |
| 16F（Final regression） | +26 → 674 |
| 16G（Artifact readiness） | +16 → 690 |
| 17A（console_scripts entry point） | +3 → 693 |
| 17B（Runtime Lock / Concurrency Guard） | +16 → 709 |
| 17C（Operator Deployment Runbook） | +0 → 709（純文件）|
| 17D（Operator Preflight Validation） | +17 → 726 |
| 17E（Packaging Metadata Modernization） | +0 → 726（pyproject.toml 格式遷移；1 個斷言更新，非新增）|
| 17F（GitHub Actions CI） | +0 → 726（純 workflow 新增 + 文件）|
| 17G（CI Result Confirmation / Release Checkpoint） | +0 → 726（純文件 checkpoint）|
