# Changelog — Rex Intelligence Platform (RIP)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v0.7.8-alpha] — Phase 19H / 19J / 19L Release Checkpoint

本 release checkpoint 收斂 Phase 19H（Operator Docs）、Phase 19J（SQLite Migration Script）、Phase 19L（SQLite Prune Implementation）三個 phase 的工作。
JSON backend 仍為預設值（`TRANSACTION_LOG_BACKEND=json`）；SQLite 為 experimental opt-in。
不修改 JSON backend / Protocol / schemas / config / CI / destructive regex。Tag Confirmed（Phase 19N）。

### Added（Phase 19L）

- **`app/core/sqlite_transaction_log.py`**（修改）：
  - `SqliteRenameTransactionLog.prune_transactions(max_transactions, max_age_days, now)` — 實作完整 prune 邏輯；跳過 rollbackable transactions（有 success action）；`ON DELETE CASCADE` 自動清除 actions；回傳 `TransactionLogPruneResult`
  - `SqliteMoveTransactionLog.prune_transactions(older_than_days, dry_run, now)` — 實作完整 prune 邏輯；3-state（protected / retained / pruned）；`dry_run=True` 時不執行 DELETE；`corrupted_count` 恆為 0（SQLite schema 保證 validity）；回傳 `MoveTransactionLogPruneResult`
  - 新增 `from datetime import datetime, timedelta, timezone` import
- **`tests/test_sqlite_transaction_log.py`**（修改）：+25 tests（855 → 878）；移除 2 個 NotImplementedError 測試；新增 10 個 rename prune 測試 + 15 個 move prune 測試
- **`tests/test_transaction_log_factory.py`**（修改）：更新 2 個 factory prune 測試（不再期望 NotImplementedError，改驗證正常執行與正確回傳型別）
- **`docs/OPERATOR_DEPLOYMENT.md`**（修改）：feature 比較表新增 `prune_transactions()` 欄位（✅ JSON / ✅ SQLite Phase 19L）；移除 `⚠️ SQLite prune_transactions 尚未實作` warning section

### Not Changed（Phase 19L）

- `TRANSACTION_LOG_BACKEND` 預設值仍為 `"json"`
- 不修改 JSON backend（`app/filename/transaction_log.py` / `app/folder_intelligence/transaction_log.py`）
- 不修改 Protocol（`app/core/transaction_log_protocol.py`）；`prune_transactions()` 不進 Protocol（簽名相異）
- 不修改 schemas（`app/filename/schemas.py` / `app/folder_intelligence/schemas.py`）
- 不修改 `app/core/config.py` / `app/core/runtime_lock.py`
- 不修改 `scripts/mock_line.py` / destructive command regex
- 不做 Approval SQLite backend
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`
- 不建立 tag

---

### Added（Phase 19J）

- **`app/core/transaction_log_migration.py`**（新增）：
  - `MigrationResult` dataclass（`source_path / kind / dry_run / migrated_count / already_present_count / corrupted_count / skipped_count / missing_source / errors / warnings`）
  - `_load_json_strict(path)` — 嚴格 JSON read；明確區分 `file_not_found` / `corrupt_json` / `invalid_structure`（不使用 `read_json_log()`）
  - `migrate_rename_transactions(rename_json_path, db_path, *, dry_run=True, fail_on_corrupt=False) → MigrationResult`
  - `migrate_move_transactions(move_json_path, db_path, *, dry_run=True, fail_on_corrupt=False) → MigrationResult`
  - `migrate_all(source_json_dir, db_path, *, dry_run=True, backup=False, rename=True, move=True, fail_on_corrupt=False) → dict`
  - Idempotency：`transaction_id` 已存在時 skip（already_present_count++），不覆蓋
  - Validation：使用 Pydantic `model_validate()` 驗證每筆 entry；非法 status / 缺失欄位 → corrupted_count++
  - JSON 原檔永遠不修改（read-only on JSON side）
  - 不使用 `shutil`（符合 AST safety test 限制）
- **`scripts/migrate_transaction_logs.py`**（新增）：
  - `argparse` CLI：`--dry-run`（預設）/ `--apply` / `--backup` / `--source-json-dir` / `--db-path` / `--rename-only` / `--move-only` / `--fail-on-corrupt` / `--json-report`
  - `--apply` 取得 `acquire_runtime_lock()`；lock busy → exit 1
  - Backup（`--backup --apply`）：JSON 備份用 `.bak_YYYYMMDD_HHMMSS` 後綴；DB 備份用 `sqlite3.backup()`（WAL-safe）
  - Exit codes：0 success / 1 lock busy / 2 corrupt + fail_on_corrupt / 3 unexpected error
- **`tests/test_transaction_log_migration.py`**（新增）：39 tests（816 → 855）
- **`docs/OPERATOR_DEPLOYMENT.md`**（修改）：新增 `## JSON → SQLite Migration（Phase 19J）` section；快速參考新增 migration 條目

### Not Changed（Phase 19J）

- `TRANSACTION_LOG_BACKEND` 預設值仍為 `"json"`
- 不修改 `app/core/runtime_lock.py` / `config.py` / `transaction_log_factory.py` / `sqlite_transaction_log.py`
- 不修改 `scripts/mock_line.py` / destructive command regex
- 不做 SQLite prune implementation
- 不做 Approval SQLite migration / backend
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`
- 不建立 tag

---

### Changed（Phase 19H）

- **`docs/OPERATOR_DEPLOYMENT.md`**（修改）：
  - 文件版本更新至 v0.7.7-alpha（Phase 19H）
  - 概覽補充 optional SQLite backend 說明與文件連結
  - `.env` 範例新增 `TRANSACTION_LOG_BACKEND` 設定（含警告注釋）
  - `RUNTIME_DIR 說明` 新增 `rip.db` / `rip.db-wal` / `rip.db-shm`、WSL2 注意事項
  - `runtime/ 目錄說明` tree 補充 `rip.db` / `rip.db-wal` / `rip.db-shm`、sqlite-only 說明
  - 新增 `rip.db / rip.db-wal / rip.db-shm` subsection
  - 備份：新增 SQLite hot backup（`sqlite3 .backup`）、WAL 注意事項、DB integrity check
  - 還原：新增 SQLite restore 流程（保留損壞 DB + restore + WAL 清除 + integrity check）
  - 升級：更新注釋版本
  - 新增 `## Experimental SQLite Transaction Log Backend` section：
    - 啟用方式（`.env` / 臨時覆寫）
    - 影響範圍表（json vs sqlite）
    - ⚠️ No migration warning（舊 JSON history 不可見、操作影響、保留 JSON 說明）
    - ⚠️ SQLite prune_transactions 尚未實作說明（Phase 19L 已移除此 warning）
    - Backup / Fallback to JSON / runtime lock 與 SQLite 關係 / WSL2 注意
  - 快速參考：新增 sqlite backup / integrity check / 啟用 / 切回 / 重建 DB 條目

### Not Changed（Phase 19H）

- 不修改 application code / tests / pyproject.toml / poetry.lock / ci.yml
- 不做 migration script
- 不實作 SQLite prune
- 不修改 `TRANSACTION_LOG_BACKEND` 預設值（仍為 "json"）
- 不建立 runtime/rip.db
- 不建立 tag

---

## [v0.7.7-alpha] — Phase 19G Tag Confirmation

本階段為純文件 tag confirmation。v0.7.7-alpha annotated tag 已建立並 push 至 origin，無程式碼變動、無測試新增。

### Tag Confirmed

| 欄位 | 值 |
|------|----|
| tag | `v0.7.7-alpha` |
| tag object | `80d234676bdacbc8b5dafefa427f59289e471b81` |
| target commit | `86c3b9b3d938b574c5d5bdcda4519604476d0733` |
| remote tag pushed | ✅ yes |

### Changed Files（Phase 19G）

- `CHANGELOG.md`：Phase 19G 條目新增。
- `docs/PROJECT_STATUS.md`：Phase 19G 列；Tag Readiness Checklist 全數完成（[x]）。
- `docs/RELEASE_NOTES.md`：v0.7.7-alpha section 補 Tag Confirmation；Test Count 新增 Phase 19G。
- `README.md`：banner 更新至 Phase 19G；Release Checkpoint Notes 標注 tag confirmed。

---

## [v0.7.7-alpha] — Phase 19F Release Checkpoint

本 release checkpoint 收斂 Phase 19B（Experimental SQLite Backend）與 Phase 19D（Optional Backend Factory / TRANSACTION_LOG_BACKEND integration）兩個 phase 的工作。
JSON backend 仍為預設值，SQLite 為 experimental opt-in。不做 migration、不做 prune、不改 default。

### Added（Phase 19B）

- **`app/core/sqlite_transaction_log.py`**（新增）：
  - `initialize_sqlite_schema(db_path)` — idempotent schema DDL（5 tables + 2 indexes）
  - `SqliteRenameTransactionLog` — 滿足 `RenameTransactionLogProtocol`（Phase 18E）
  - `SqliteMoveTransactionLog` — 滿足 `MoveTransactionLogProtocol`（Phase 18E）
  - connection helper（`_open_connection` / `_connection` context manager）
  - PRAGMA：journal_mode=WAL / foreign_keys=ON / busy_timeout=5000
  - ON DELETE CASCADE / status CHECK constraint / AUTOINCREMENT action order
  - Uses Python stdlib sqlite3 only（no SQLAlchemy, no new pyproject.toml dependencies）
- **`tests/test_sqlite_transaction_log.py`**（新增）：29 tests（765 → 794）

### Added（Phase 19D）

- **`app/core/config.py`**（修改）：
  - `Settings.TRANSACTION_LOG_BACKEND: Literal["json", "sqlite"] = "json"` — 後端選擇旗標（預設 "json"）
  - `get_sqlite_db_path()` — 回傳 `runtime/rip.db` Path（只算路徑，不建立檔案）
- **`app/core/transaction_log_factory.py`**（新增）：
  - `make_rename_transaction_log()` — 依 `TRANSACTION_LOG_BACKEND` 回傳 rename log backend
  - `make_move_transaction_log()` — 依 `TRANSACTION_LOG_BACKEND` 回傳 move log backend
  - 本機 import 設計：backend="json" 時不 import SQLite module
- **`app/folder_intelligence/approval_bridge.py`**（修改）：
  - `default_move_transaction_log()` 改用 `make_move_transaction_log()` 路由
- **`scripts/mock_line.py`**（修改）：
  - 三個 rename log 實例化改用 `make_rename_transaction_log()`
- **`tests/test_transaction_log_factory.py`**（新增）：22 tests（794 → 816）

### Test Delta（v0.7.6-alpha → v0.7.7-alpha）

| 里程碑 | Tests |
|--------|-------|
| v0.7.6-alpha | 765 |
| Phase 19B | 794（+29）|
| Phase 19D | 816（+22）|
| **v0.7.7-alpha** | **816** |

### Not Changed

- JSON backend 仍是 default / production path（`TRANSACTION_LOG_BACKEND` 預設 "json"）
- 不修改 `ApprovalManager` / `JsonApprovalStore`
- 不修改 runtime lock / destructive command regex
- 不做 migration script（JSON → SQLite 歷史 migration 延後至 Phase 19H）
- 不實作 `prune_transactions`（SQLite backend 明確 raise NotImplementedError；延後至 Phase 19I）
- 不實作 `ApprovalStoreProtocol` / `SqliteApprovalStore`
- 不修改 `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml`
- 不建立 runtime/rip.db（除非主動設定 `TRANSACTION_LOG_BACKEND=sqlite`）
- 不修改 runtime JSON schema（approvals.json / rename_transactions.json / move_transactions.json 格式不變）

---

## [v0.7.6-alpha] — Phase 18H Tag Confirmation

本階段為純文件 tag confirmation。v0.7.6-alpha annotated tag 已建立並 push 至 origin，無程式碼變動、無測試新增。

### Tag Confirmed

| 欄位 | 值 |
|------|----|
| tag | `v0.7.6-alpha` |
| tag object | `55d560580433d4026609d33fdd87765a76a73d22` |
| target commit | `8299b9f3cbb3b184671cd885d32ddd8e1d3f8acb` |
| remote tag pushed | ✅ yes |

### Changed Files（Phase 18H）

- `CHANGELOG.md`：Phase 18H 條目新增。
- `docs/PROJECT_STATUS.md`：Phase 18H 列；Tag Readiness Checklist 全數完成（[x]）。
- `docs/RELEASE_NOTES.md`：v0.7.6-alpha section 補 Tag Confirmation；Test Count 新增 Phase 18H。
- `README.md`：banner 更新至 Phase 18H；Release Checkpoint Notes 標注 tag confirmed。

---

## [v0.7.6-alpha] — Phase 18G Release Checkpoint

本階段為純文件 release checkpoint。收斂 Phase 18B / 18C / 18E 的 persistence refactor 工作，無新功能、無 SQLite 導入、不修改任何 application code。

### Release Delta（since v0.7.5-alpha）

| Commit | Phase | 說明 |
|--------|-------|------|
| `47a4128` | 18B | refactor(approvals): extract JSON approval store |
| `31c1037` | 18C | refactor(transactions): extract shared JSON log IO |
| `c5434ff` | 18E | refactor(transactions): define transaction log protocols |

### Highlights
- **Phase 18B**：`JsonApprovalStore` stateless I/O helper 從 `ApprovalManager` 提取；`approvals.json` schema / `self.store_path` / `self._store` 不變。
- **Phase 18C**：`read_json_log` / `write_json_log` / `ensure_utc_aware` 三個 module-level helper 從兩個 transaction log 的重複程式碼提取；`rename_transactions.json` / `move_transactions.json` schema 不變。
- **Phase 18E**：`RenameTransactionLogProtocol` / `MoveTransactionLogProtocol` 兩個 `@runtime_checkable` structural Protocol（PEP 544）；executor / approval_bridge 型別標注更新；JSON backend 仍是唯一 backend。
- **Reconnaissance only（no commit）**：Phase 18A（SQLite Persistence Recon）、Phase 18D（Transaction Log Protocol / SQLite Design）、Phase 18F（SQLite Backend / Migration Design）。

### Final Regression（v0.7.6-alpha readiness）

| 指令 | 結果 |
|------|------|
| `poetry check` | All set! |
| `poetry run pytest -q` | 765 passed |
| `poetry build` | `rex_intelligence_platform-0.1.0.tar.gz` ✅ |
| `poetry run rip "說明"` | 正常回覆指令說明 ✅ |

### Safety guarantees
- 不導入 SQLite，不建立 `runtime/rip.db`，不新增 backend flag。
- `approvals.json` / `rename_transactions.json` / `move_transactions.json` schema 不變。
- `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml` / runtime lock 不變。
- Destructive command regex 不變。
- 測試數：726（v0.7.5-alpha）→ 765（v0.7.6-alpha，+39）。

---

## [v0.7.6-alpha] — Phase 18E Transaction Log Protocol Definition

### Added
- `app/core/transaction_log_protocol.py`：新增兩個 `@runtime_checkable` structural Protocol：
  - `RenameTransactionLogProtocol`：`save_transaction` / `load_transaction` / `list_transactions` / `update_transaction` / `mark_transaction_actions`（各方法簽名與現有 JSON 實作完全相符）
  - `MoveTransactionLogProtocol`：同構，使用 `MoveTransaction` / `MoveTransactionAction` 型別
- `tests/test_transaction_log_protocol.py`：8 個新測試，覆蓋 isinstance / prune 排除 / callable / no-sqlite / runtime_checkable。

### Changed
- `app/filename/executor.py`：`execute_rename_plan` 與 `rollback_transaction_by_id` 的 `transaction_log` 參數型別改為 `RenameTransactionLogProtocol`；runtime 行為完全不變。
- `app/filename/approval_bridge.py`：`execute_approved_rename_plan` 與 `execute_approved_rename_by_plan_id` 的 `transaction_log` 參數型別同上。
- `app/folder_intelligence/executor.py`：`execute_move_plan` 與 `rollback_move_transaction_by_id` 的 `transaction_log` 參數型別改為 `MoveTransactionLogProtocol`。
- `app/folder_intelligence/approval_bridge.py`：`execute_approved_move_plan` 與 `execute_approved_move_by_approval_id` 的 `transaction_log` 參數型別同上；`default_move_transaction_log()` 仍回傳 `MoveTransactionLog`。

### Safety guarantees
- `prune_transactions()` 不納入 Protocol：Rename / Move 的 signature 發散（max_transactions/max_age_days vs older_than_days/dry_run），不強制統一。
- `rename_transactions.json` / `move_transactions.json` schema 不變（`{"transactions": [...]}` wrapper）。
- JSON backend 仍是唯一 backend；runtime 行為、constructor API、`self._log_path` 屬性、prune 行為全數不變。
- 不導入 SQLite，不建立 DB 檔案，不修改 runtime lock，不修改 pyproject.toml / poetry.lock。
- `from __future__ import annotations` + `TYPE_CHECKING` 避免循環 import（`transaction_log_protocol` → `folder_intelligence.schemas` → `__init__` → `approval_bridge` → `transaction_log_protocol`）；`isinstance()` 行為不受影響。
- 測試數：757 → 765（+8）。

---

## [v0.7.6-alpha] — Phase 18C Shared JSON Transaction Log I/O Extraction

### Added
- `app/core/json_log_io.py`：新增三個 module-level helper functions：
  - `read_json_log(log_path)` — 安全讀取 `{"transactions": [...]}` JSON log；不存在 / 損毀 / 結構錯誤時回傳空結構，不 raise
  - `write_json_log(log_path, data)` — 寫入 JSON log，自動建立 parent directory，UTF-8 + ensure_ascii=False + indent=2
  - `ensure_utc_aware(dt)` — naive datetime 補 UTC；已 aware 的原樣回傳
- `tests/test_json_log_io.py`：20 個新測試，覆蓋 read/write/roundtrip/ensure_utc_aware/delegate 整合。

### Changed
- `app/filename/transaction_log.py`：`RenameTransactionLog._read()` 和 `_write()` 改為 thin wrapper，委派 `read_json_log` / `write_json_log`；移除重複的 JSON I/O 邏輯；移除不再需要的 `import json`。
- `app/folder_intelligence/transaction_log.py`：`MoveTransactionLog._read()` 和 `_write()` 同上。Move prune 的整檔 corrupt JSON 特殊 early return 邏輯保留，不受影響。

### Safety guarantees
- `rename_transactions.json` / `move_transactions.json` schema 不變（`{"transactions": [...]}` wrapper）。
- `RenameTransactionLog(log_path)` / `MoveTransactionLog(log_path)` constructor API 不變。
- `self._log_path` 仍為各 log class 的普通 Path instance 屬性（現有測試的 `._log_path.read_bytes()` 等存取繼續有效）。
- `prune_transactions()` 的 signature / 行為 / result schema 不變（rename: max_transactions/max_age_days；move: older_than_days/dry_run）。
- rollback safety（success action 永不被 prune）不變。
- 不導入 SQLite，不建立 DB 檔案，不修改 runtime lock。
- AST 安全測試（move prune 不可呼叫 rename/move/replace/mkdir）全數通過。
- 測試數：737 → 757（+20）。

---

## [v0.7.6-alpha] — Phase 18B Approval JSON Store Extraction

### Added
- `app/approvals/store.py`：新增 `JsonApprovalStore` stateless I/O helper，提供 `load(store_path)` 與 `save(store_path, data)` 兩個 static method。
- `tests/test_approval_store.py`：11 個新測試，覆蓋 load/save/roundtrip/schema/corrupted/mark_executed payload 保留。

### Changed
- `app/approvals/manager.py`：`_load_store` 和 `_save_store` 委派給 `JsonApprovalStore`；移除內嵌 JSON I/O 邏輯；`self.store_path` 和 `self._store` 屬性不變。
- `app/approvals/__init__.py`：新增 `JsonApprovalStore` 至 `__all__`。

### Safety guarantees
- `approvals.json` schema 不變（array of approval dicts）。
- `self.store_path` 和 `self._store` 仍為 `ApprovalManager` 的普通 instance 屬性，現有 monkeypatch 測試零改動。
- 不導入 SQLite，不建立任何 DB 檔案。
- `rename_transactions.json` / `move_transactions.json` schema 及對應 log 類別不變。
- `pyproject.toml` / `poetry.lock` / `.github/workflows/ci.yml` / runtime lock 不變。
- 測試數：726 → 737（+11）。

---

## [v0.7.5-alpha] — Phase 17I Tag Confirmation

本階段為純文件 tag confirmation。v0.7.5-alpha tag 已建立並 push 至 origin，無程式碼變動、無測試新增。

### Tag Confirmed

| 項目 | 結果 |
|------|------|
| tag | `v0.7.5-alpha` |
| commit | `d96f657` |
| remote tag pushed | ✅ yes |
| working tree | clean |

### Changed
- `CHANGELOG.md`：本條目（Phase 17I）。
- `docs/PROJECT_STATUS.md`：Phase 17I 列；v0.7.5-alpha tag readiness checklist 全數完成。
- `docs/RELEASE_NOTES.md`：v0.7.5-alpha section 補充 tag confirmed 資訊；Test Count 新增 Phase 17I。
- `README.md`：Phase banner 更新至 Phase 17I；Release Checkpoint Notes 更新。

### Safety guarantees
- 未修改任何 application code / workflow / pyproject.toml / poetry.lock。
- 未建立新 tag（v0.7.5-alpha 已於 Phase 17H 後人工建立並 push）。
- 測試數維持 726（零新增、零移除）。

---

## [v0.7.5-alpha] — Phase 17H Release Tag Readiness

本階段為純文件 release readiness 準備。不新增功能、不新增測試、不修改程式碼、不建立 tag。
v0.7.5-alpha tag 待本階段文件 commit + push 後、確認 GitHub Actions CI run green，再人工建立。

### v0.7.5-alpha 涵蓋範圍

自 `v0.7.4-alpha`（commit 98b4664，Phase 16G）至 HEAD 的 8 commits：

| Commit | 說明 | Phase |
|--------|------|-------|
| `72d9426` | feat(cli): add rip console script entry point | 17A |
| `8ea0b89` | feat(runtime): add operator concurrency guard | 17B |
| `44d91dc` | chore(git): ignore runtime state directory | 17B |
| `247c415` | docs(operator): add deployment and recovery runbook | 17C |
| `11c8d74` | feat(operator): add deployment preflight validation | 17D |
| `afb5237` | chore(packaging): modernize pyproject metadata | 17E |
| `9c0173c` | ci: add GitHub Actions release validation | 17F |
| `c2a980a` | docs(release): record CI checkpoint | 17G |

### Final Regression 結果（Phase 17H 前）

| 指令 | 結果 |
|------|------|
| `poetry check` | All set! |
| `poetry run pytest -q` | 726 passed |
| `poetry build` | `rex_intelligence_platform-0.1.0.tar.gz` ✅ |
| `poetry run rip "說明"` | 正常回覆指令說明 ✅ |

### Changed
- `CHANGELOG.md`：本條目（v0.7.5-alpha）。
- `README.md`：Version banner 更新至 v0.7.5-alpha / Phase 17H；Release Candidate Notes 更新。
- `docs/PROJECT_STATUS.md`：Phase 17H 列；v0.7.5-alpha tag readiness；v0.7.4-alpha stale checklist 修正。
- `docs/RELEASE_NOTES.md`：新增 v0.7.5-alpha section；test count 更新。

### v0.7.5-alpha Tag 指令草案（人工確認 CI green 後才執行）

```bash
# 1. 確認 CI run green（GitHub Actions）
# 2. 確認 working tree 乾淨
git status --short

# 3. 建立 annotated tag
git tag -a v0.7.5-alpha -m "RIP v0.7.5-alpha"

# 4. 確認 tag
git show v0.7.5-alpha

# 5. 推送（不可逆，請再次確認後執行）
git push origin v0.7.5-alpha
```

### Safety guarantees
- 未修改任何 application code / workflow / pyproject.toml / poetry.lock。
- 未建立 tag、未 push tag。
- 測試數維持 726（零新增、零移除）。
- v0.7.4-alpha tag 不重打、不 force-update。

---

## [v0.7.4-alpha] — Phase 17G CI Result Confirmation / Release Checkpoint Notes

本階段為純文件 checkpoint。無程式碼變動、無測試新增、無 workflow 修改、無 dependency 異動。

### CI #1 Run 確認

| 項目 | 結果 |
|------|------|
| Commit | 9c0173c |
| Runner | ubuntu-22.04 / Python 3.12 / Poetry 2.4.1 |
| Duration | 34s |
| poetry check | All set! |
| pytest | 726 passed |
| poetry build | 成功（rex_intelligence_platform-0.1.0）|

GitHub Actions CI 首次在 clean environment 完整驗證：
- PEP 621 `[project]` 格式正確（poetry check All set）
- PyMuPDF（pymupdf 1.27.2.3）可在 ubuntu-22.04 正常安裝與 import
- `poetry run rip "說明"` console_scripts entry point 可用
- packaging artifact 0.1.0 可正常 build

### Changed
- `CHANGELOG.md`：本條目。
- `README.md`：Version banner 更新至 Phase 17G。
- `docs/PROJECT_STATUS.md`：Phase 17G 加入 Completed Phases；CI pipeline checklist 更新；stale 內容修正。
- `docs/RELEASE_NOTES.md`：Phase header 更新；Highlights 補 CI run 確認；test count 表更新。

### Stale 修正清單（PROJECT_STATUS.md）
- `[ ] Production deployment guide completed` → `[x]`（17C 已完成 OPERATOR_DEPLOYMENT.md）
- Version Strategy 節：`poetry check 有 deprecation warnings` → `poetry check: All set!`
- Known Limitations：`v0.7.3-alpha` → `v0.7.4-alpha`；`poetry check warnings` 說明更新
- Recommended Next Phase：`Phase 17B` → `Phase 17H（TBD）`

### Safety guarantees
- 未修改任何 application code / workflow / runtime JSON schema。
- `.github/workflows/ci.yml` / `pyproject.toml` / `poetry.lock` 未異動。
- 測試數維持 726（零新增、零移除）。

### Recommended next phase
- **Phase 17H** — 視需求決定

---

## [v0.7.4-alpha] — Phase 17F GitHub Actions CI / Release Validation

本階段新增 `.github/workflows/ci.yml`，在 push / pull_request to main 時自動執行
`poetry check`、`pytest -q`（726 tests）、`poetry run rip "說明"`（CLI entry point smoke）、
`poetry build`（packaging 驗證）。不修改任何程式邏輯、不修改 pyproject.toml / poetry.lock /
runtime JSON schema。

### Added
- `.github/workflows/ci.yml`：GitHub Actions CI workflow（Python 3.12 / ubuntu-22.04 /
  Poetry 2.4.1；含 virtualenv cache keyed on `poetry.lock`）。

### Changed
- `README.md`：Version banner 更新至 Phase 17F；新增 CI badge。
- `docs/PROJECT_STATUS.md`：Phase 17F 加入 Completed Phases。
- `docs/RELEASE_NOTES.md`：Highlights 補 GitHub Actions CI；test count 表更新。
- `CHANGELOG.md`：本條目。

### CI workflow 說明

| Step | 指令 | 目的 |
|------|------|------|
| checkout | `actions/checkout@v4` | 取得 repo |
| python | `actions/setup-python@v5` (3.12) | 符合 `requires-python = ">=3.12,<4.0"` |
| poetry | `pip install "poetry==2.4.1"` | 對齊本機版本，避免行為差異 |
| venv config | `poetry config virtualenvs.in-project true` | 啟用 `.venv` in-project，方便 cache |
| cache | `actions/cache@v4` (key: `hashFiles('poetry.lock')`) | 避免重複下載 pymupdf 等套件 |
| install | `poetry install` | 安裝全部 locked dependencies |
| poetry check | `poetry check` | 驗證 pyproject.toml 格式（應為 All set!）|
| tests | `poetry run pytest -q` | 726 tests |
| CLI smoke | `poetry run rip "說明"` | 驗證 Phase 17A/17E console_scripts entry point |
| build | `poetry build` | 驗證 packaging 正常（artifact 不 commit）|

### Safety guarantees
- 未修改任何 application code / workflow / runtime JSON schema / transaction log。
- `poetry.lock` 不變（Phase 17F 不改任何 dependency）。
- `dist/` artifacts 仍 gitignored，不 commit。
- 不新增、不修改任何測試（726 不變）。
- 不進行 GitHub Release / publish / push tag 操作。

### Recommended next phase
- **Phase 17G** — 視需求決定

---

## [v0.7.4-alpha] — Phase 17E Packaging Metadata Modernization

本階段將 `pyproject.toml` 從 `[tool.poetry]` 舊格式遷移至 PEP 621 `[project]` 標準欄位，
消除 `poetry check` 所有 6 個 deprecation warning；並正式將 `pymupdf` 納入 `[project.dependencies]`，
確保 fresh install 後 PDF workflow 可正常運作。package version 維持 0.1.0（packaging metadata）；
RIP release version（v0.7.4-alpha）以文件 / git tag 為準。不修改任何程式邏輯。

### Changed
- `pyproject.toml`：
  - 新增 `[project]` section（name / version / description / readme / authors / requires-python / dependencies）。
  - runtime dependencies 從 `[tool.poetry.dependencies]` 遷移至 `[project.dependencies]`，
    caret constraints 轉為 PEP 508 等價範圍（例 `^0.115.0` → `>=0.115.0,<0.116.0`）。
  - **正式新增 `pymupdf>=1.27.2,<1.28.0` 為 runtime dependency**（原為手動安裝，未在 pyproject.toml；
    fresh install 後 `import fitz` / PDF analysis workflow 會因缺少 fitz 而失敗）。
  - `[tool.poetry.scripts]` 遷移至 `[project.scripts]`。
  - 保留 `[tool.poetry]`（packages 宣告）與 `[tool.poetry.group.dev.dependencies]`。
  - `[build-system]` 不變。
- `tests/test_cli_smoke.py`：`[tool.poetry.scripts]` 斷言 → `[project.scripts]`（Phase 17E PEP 621 遷移）。
- `poetry.lock`：新增 pymupdf 1.27.2.3 lock entry；content-hash 更新；既有 6 個套件版本不變。
- `README.md`：Version banner 更新至 Phase 17E；Known Limitations 補 PEP 621 migration 說明。
- `docs/PROJECT_STATUS.md`：Phase 17E 加入 Completed Phases；test count 維持 726。
- `docs/RELEASE_NOTES.md`：Package Artifact 節更新（poetry check now "All set!"）；test count 表更新。
- `CHANGELOG.md`：本條目。

### poetry check 結果（Phase 17E 後）

```
All set!
```

（6 個 deprecation warnings 已全數消除；migration 前為「Poetry 2.x 建議從 [tool.poetry] 遷移」等警告）

### poetry.lock 變動說明

`poetry lock` 新增 pymupdf lock entry（1.27.2.3）；既有 6 個主要 runtime dependency 版本完全不變：

| Package | Version | 異動 |
|---------|---------|------|
| pymupdf | 1.27.2.3 | **新增** |
| fastapi | 0.115.14 | 不變 |
| line-bot-sdk | 3.23.0 | 不變 |
| pydantic | 2.13.4 | 不變 |
| pydantic-settings | 2.14.1 | 不變 |
| python-dotenv | 1.2.2 | 不變 |
| uvicorn | 0.34.3 | 不變 |

### Safety guarantees
- 未修改 scripts/mock_line.py / runtime_lock.py / config.py / preflight.py。
- 未修改 runtime JSON schema。
- 未修改任何指令語意或 workflow 行為。
- `poetry run pytest -q`：726 passed（無新增、無移除測試；`test_cli_smoke.py` 1 個斷言更新）。
- package version 保持 0.1.0（packaging metadata 與 RIP release version 分離策略不變）。

### Recommended next phase
- **Phase 17F** — 視需求決定

---

## [v0.7.4-alpha] — Phase 17D Operator Preflight Validation

本階段新增 `app/core/preflight.py` safe preflight module 與
`tests/test_operator_preflight.py`（17 tests），驗證 operator 本機環境。
不修改任何程式邏輯、不改 runtime 行為、不改 JSON schema。

### Added
- `app/core/preflight.py`：`PreflightItem` dataclass + `run_operator_preflight()` +
  7 個獨立 check function（python_version / fcntl / safe_pdf_root / runtime_dir_writable /
  runtime_not_git_tracked / dist_not_git_tracked / pyproject_console_scripts）。
- `tests/test_operator_preflight.py`：17 個測試（module import / Python version pass+fail /
  fcntl / SAFE_PDF_ROOT 存在 / 不建立目錄 / RUNTIME_DIR 建立 / 無 JSON state /
  不取 lock / 不建 approvals.json / git 追蹤 / pyproject / integration）。

### Changed
- `docs/OPERATOR_DEPLOYMENT.md`：新增「Preflight Validation（Phase 17D）」節
  （7 個 check 說明 / safe preflight 保證 / 執行方式）；快速參考新增 preflight 指令。
- `README.md`：Version banner 更新至 Phase 17D；安全原則補 preflight 一行。
- `docs/PROJECT_STATUS.md`：Phase 17D 加入 Completed Phases；測試數 709 → 726。
- `docs/RELEASE_NOTES.md`：Phase header 更新；test count 更新（+17 → 726）。
- `CHANGELOG.md`：本條目。

### Safety guarantees
- `run_operator_preflight()` 不呼叫 `acquire_runtime_lock()`（測試驗證不建立 rip.lock）。
- 不建立 approvals.json / rename_transactions.json / move_transactions.json（測試驗證）。
- SAFE_PDF_ROOT 不存在時只回報，不自動建立（測試驗證）。
- 所有測試使用 tmp_path / 參數 override；runtime 零污染。
- 未修改 scripts/mock_line.py / runtime_lock.py / config.py。

### Recommended next phase
- **Phase 17E** — 視需求決定

---

## [v0.7.4-alpha] — Phase 17C Operator Deployment / Backup / Restore Runbook

本階段新增 `docs/OPERATOR_DEPLOYMENT.md`，涵蓋 operator 安裝、設定、smoke test、runtime 目錄說明、
備份、還原、升級、runtime_lock_busy 處理、Git hygiene。
純文件異動，不改任何程式、不改 runtime 行為、不改 JSON schema。

### Added
- `docs/OPERATOR_DEPLOYMENT.md` — Operator 完整 Runbook（安裝 / 設定 / smoke test /
  runtime 目錄 / 備份 / 還原 / 升級 / runtime_lock_busy / Git hygiene）。

### Changed
- `README.md`：Version banner 更新至 Phase 17C；安全原則新增 Operator Runbook 參照。
- `docs/PROJECT_STATUS.md`：Phase 17C 加入 Completed Phases；
  Release Readiness Checklist 勾選「Production deployment guide」。
- `docs/RELEASE_NOTES.md`：Phase header 更新至 17C；Highlights 補 Operator Runbook；
  Known Limitations 更新。
- `CHANGELOG.md`：本條目。

### Safety guarantees
- 未修改任何程式（scripts/、app/、tests/ 均無異動）。
- 未新增任何 Mock LINE 指令、未改變 runtime 行為、未改 JSON schema。
- 測試數維持 709 passed（無新增 tests）。

### Recommended next phase
- **Phase 17D** — 視需求決定

---

## [v0.7.4-alpha] — Phase 17B Runtime Lock / Concurrency Guard

本階段新增 `app/core/runtime_lock.py`（`fcntl.flock` 非阻塞 advisory lock），
防止多個 operator process 同時執行會修改 runtime state 或實體檔案的操作。
不新增任何 Mock LINE 指令、不改變指令語意、不修改 command dispatch / regex / full-match 規則。

### Added
- `app/core/runtime_lock.py`：`RuntimeLockBusy`（RuntimeError）、`acquire_runtime_lock()`
  context manager（`fcntl.LOCK_EX | LOCK_NB` on `runtime/rip.lock`）。
- `scripts/mock_line.py`：`_LOCK_BUSY_REPLY` 常數；六個會寫入 runtime state 的指令路徑（確認改名、
  回滾改名、確認搬移、回滾搬移、planning keywords path、generic router path）以 `acquire_runtime_lock()` 保護。
- `tests/test_runtime_lock.py`：16 個測試，涵蓋 lock 建立 / 釋放 / busy 時拋例外、_LOCK_BUSY_REPLY 內容、
  help / preview 在 lock busy 時仍正常回覆、planning / approval / destructive / rollback 在 lock busy 時回傳 runtime_lock_busy。

### Changed
- `README.md`：Version banner 更新至 Phase 17B；安全原則新增「Concurrent access guard」。
- `docs/PROJECT_STATUS.md`：Phase 17B 加入 Completed Phases；✅ Multi-user concurrency guard；
  測試數更新（693 → 709）；Release Readiness Checklist 勾選 concurrency guard。
- `docs/RELEASE_NOTES.md`：Test Count 表更新（+16 → 709）；Safety Guarantees 新增 runtime lock 一行。
- `CHANGELOG.md`：本條目。

### Safety guarantees
- 未新增任何 destructive action、未新增任何 Mock LINE 指令、未改變既有指令語意。
- `mock_line.py` command dispatch、regex、full-match 規則完全未修改。
- Preview 指令（預覽回滾改名 / 預覽回滾搬移）維持純讀取，不走 lock 路徑。
- Help 指令不走 lock 路徑，零 side effects。
- Transaction log schema / runtime JSON schema / approval ID format 完全不變。
- Lock file `runtime/rip.lock` 已由 `runtime/` gitignore 覆蓋，不納入 Git。
- 所有測試使用 tmp_path / monkeypatch；runtime 零污染。

### Recommended next phase
- **Phase 17C** — 視需求決定（pyproject.toml 現代化 / 功能擴充 / 正式 release）

---

## [v0.7.4-alpha] — Phase 17A console_scripts Entry Point

本階段新增正式 `rip` console_scripts entry point，使 `poetry run rip "..."` 可替代
`poetry run python scripts/mock_line.py "..."`。舊用法保留（向下相容）。
不新增任何 Mock LINE 指令、不改變指令語意、不修改 command dispatch / regex / destructive command 規則。

### Added
- `pyproject.toml`：`packages` 加入 `{ include = "scripts" }`；新增 `[tool.poetry.scripts]` 區塊，
  定義 `rip = "scripts.mock_line:main"`。
- `tests/test_cli_smoke.py`：新增 3 個測試（`test_pyproject_defines_rip_console_script`、
  `test_rip_entry_point_callable`、`test_readme_documents_rip_entry_point`）。

### Changed
- `README.md`
  - Version banner 更新至 Phase 17A。
  - Mock LINE 使用方式新增 `poetry run rip "..."` 為主要入口；舊 `poetry run python scripts/mock_line.py "..."` 保留。
  - 目前限制更新：`rip` console_scripts entry point 已提供（Phase 17A），舊用法向下相容。
- `tests/test_cli_smoke.py`：
  - `test_pyproject_exists_with_poetry_and_pytest` 更新 packages 斷言（同時驗證 app / scripts）。
  - `test_readme_documents_known_limitations` 更新 assert 說明文字。
- `docs/PROJECT_STATUS.md`：Phase 17A 加入 Completed Phases；✅ Formal console_scripts entry point；
  測試數更新（690 → 693）；Recommended Next Phase 更新。
- `docs/RELEASE_NOTES.md`：Test Count 表更新（+3 → 693）。
- `CHANGELOG.md`：本條目。

### Safety guarantees
- 未新增任何 destructive action、未新增任何 Mock LINE 指令、未改變既有指令語意。
- `mock_line.py` command dispatch、regex、full-match 規則完全未修改。
- Transaction log / rename / move / rollback / cleanup workflow 行為完全不變。
- `scripts/__init__.py` 已存在，不需要新增。
- 所有測試使用 tmp_path / monkeypatch；runtime JSON 持續 gitignored。

### Recommended next phase
- **Phase 17B** — 視需求決定（pyproject.toml 現代化 / 功能擴充 / 正式 release）

---

## [v0.7.4-alpha] — Phase 16G Git Tagging / Release Artifact Preparation

本階段完成 v0.7.4-alpha 的 release artifact preparation：tagging instructions 文件化、
package artifact 建置驗證、pyproject version strategy 最終確認。
不新增核心功能、不新增 destructive action、不改變既有指令語意、
不自動建立 git tag、不自動 push。

### Added
- `tests/test_release_artifact_readiness.py` — 16 個 artifact readiness 驗收測試（詳見下）。

### Changed
- `docs/RELEASE_NOTES.md`
  - Phase 標題更新至 Phase 16E–16G。
  - Highlights 補「Tag readiness preparation completed（16G）」。
  - Known Limitations 補 pyproject version 未對齊說明與 console_scripts limitation 更新。
  - 新增「Package Artifact（Phase 16G）」— `poetry check` 結果（warnings 非 errors）、
    `poetry build` 成功（sdist + wheel，0.1.0）、artifact 路徑與 gitignored 狀態。
  - 「Tagging Recommendation」改寫為「Tagging Instructions（Phase 16G）」— 前置條件確認
    指令、annotated tag 建立指令、`git show` 確認指令、人工 push 指令；明確聲明不自動 push。
  - Test Count 補 16G（+16 → 690）。
- `docs/PROJECT_STATUS.md`
  - 16G 加入 Completed Phases 表。
  - Release Readiness Checklist 補三項 ✅（artifact built / tagging instructions / version decision）。
  - Tag Readiness Checklist 更新：補「Tagging instructions documented」「Package artifact built」✅；
    「Git tag created」「Tag pushed」仍為 ⬜（含人工執行指令說明）。
  - Version Strategy 區塊更新為 16G 最終確認（方案 A 確認、artifact 版本說明、poetry check warnings）。
  - Known Limitations 補 artifact 與 tag 狀態說明。
  - Recommended Next Phase 更新為 Phase 16H。
  - 測試數更新（674 → 690）。

### pyproject version strategy final decision（Task 2，方案 A 確認）
- **保守維持方案 A**：`pyproject.toml` version（0.1.0）不修改。
- `poetry build` 產生 `rex_intelligence_platform-0.1.0.tar.gz` / `.whl`（dist/，已 gitignored）。
- `poetry check` 顯示 deprecation warnings（`[tool.poetry]` 舊格式），非 errors，不影響 build。
- 版本對齊（0.1.0 → 0.7.4a0）留待正式 release packaging 決策（16H+）。

### Release artifact status（Task 3）
- `poetry build` 成功；`dist/` 已 gitignored；dist artifacts 未 commit；working tree 保持乾淨。
- `poetry check` 通過（有 deprecation warnings，需未來遷移至 `[project]` 標準格式）。

### Tag decision（Task 5，保守方案）
- **不自動建立 git tag**。
- Tagging Instructions 已文件化於 `docs/RELEASE_NOTES.md`（前置條件 / annotated tag / git show / push）。
- 人工 tag 指令：`git tag -a v0.7.4-alpha -m "RIP v0.7.4-alpha"` && `git push origin v0.7.4-alpha`。

### Safety guarantees
- 未新增任何 destructive action、未新增任何 Mock LINE 指令、未改變既有指令語意。
- 未建立任何 git tag、未執行任何 git push。
- dist/ 已 gitignored；runtime/ 無 git 追蹤。
- 所有測試使用 tmp_path / monkeypatch；runtime JSON 持續 gitignored。

### Recommended next phase
- **Phase 16H — Manual Tag Confirmation / Release Freeze**（人工執行 tag push，或視為最後 release step）

---

## [v0.7.4-alpha] — Phase 16F Release Candidate Tagging / Final Regression

本階段完成 v0.7.4-alpha release candidate 前的最後穩定化檢查：final regression audit、
release notes 整理、tag readiness checklist。不新增核心功能、不新增 destructive action、
不改變既有指令語意、不自動建立 git tag。

### Added
- `docs/RELEASE_NOTES.md` — v0.7.4-alpha 完整 release notes：
  - **Highlights**（Rename / Move / Approval / Transaction log / Runtime settings /
    Help text / CLI smoke / Release readiness checklist / Final regression audit）。
  - **Safety Guarantees** 表（planning non-destructive、preview read-only、destructive full match、
    logs separated、runtime gitignored、SAFE_PDF_ROOT 錨定、once-only guard、bridge not direct）。
  - **Operator Commands** 表（Non-destructive 8 指令 / Destructive full-match only 4 指令）。
  - **Known Limitations**（local CLI only、JSON persistence、no console_scripts、
    不適合多人/生產、pyproject version 為 packaging metadata）。
  - **Tagging Recommendation**（不自動 tag；建議條件：clean working tree + all tests pass
    + 版本一致 + runtime 無追蹤；tag 留待 Phase 16G 人工執行）。
  - **Test Count** 歷程（16D +22 / 16E +20 / 16F +26 → 674）。
- `tests/test_final_regression_release_candidate.py` — 26 個最終回歸稽核測試：
  - **Destructive command invariants（2）**：四個指令仍 ^…$ full match；無 approved list 以外的危險 pattern。
  - **Preview command invariants（1）**：preview 指令 full match regex 存在。
  - **Non-destructive smoke（3）**：planning 指令不動檔案、不寫 log；generic 確認未知 id 安全回覆；rename/move logs 互不干擾（2 個分離測試）。
  - **Runtime / git（1）**：runtime JSON 無 git 追蹤。
  - **Docs consistency（5）**：version 一致（README/PROJECT_STATUS/CHANGELOG）、
    README command inventory、PROJECT_STATUS checklist、CHANGELOG 16F 條目、pyproject 策略。
  - **Help regression（1）**：help 指令仍可用。
  - **RELEASE_NOTES 稽核（6）**：RELEASE_NOTES 存在、版本、safety guarantees、
    operator commands、known limitations、no-auto-tag 聲明。
  - **Tag readiness（2）**：PROJECT_STATUS 含 Tag Readiness Checklist、git tag 項目標記未完成（[ ]）。
  - **README links（1）**：README 含 RELEASE_NOTES 連結。
  - **Command inventory final（3）**：destructive inventory 不變（4 個）、
    mock_line no new regex、RELEASE_NOTES 含完整指令。

### Changed
- `README.md`
  - 版本橫幅 phase 參照更新為 Phase 16F — Final Regression。
  - 新增 RELEASE_NOTES.md 連結。
  - Release Candidate Notes 區塊補 Release Notes 連結與 git tag 尚未建立聲明。
- `docs/PROJECT_STATUS.md`
  - 16F 加入 Completed Phases 表。
  - Release Readiness Checklist 補 RELEASE_NOTES / final regression / tag readiness 三項 ✅。
  - 新增「Tag Readiness Checklist（v0.7.4-alpha）」— ✅ 9 項已完成、⬜ 4 項待完成。
  - Version Strategy 區塊更新（pyproject 版本對齊移至 16G+）。
  - Known Limitations 補 16F RELEASE_NOTES 靜態維護與 Tag Readiness 說明。
  - Recommended Next Phase 更新為 Phase 16G。
  - 測試數更新（648 → 673）。
- `tests/test_cli_smoke.py`（無更動）— 16D 版本字串已在 16E 更新，16F 維持不變。

### Safety guarantees
- 未新增任何 destructive action、未新增任何 Mock LINE 指令、未改變既有指令語意。
- 四個 destructive regex 仍全數 ^…$ 全錨定（test_final_regression_release_candidate.py 鎖定驗證）。
- 未建立任何 git tag、未執行任何 git push。
- 所有測試使用 tmp_path / monkeypatch；runtime JSON 持續 gitignored。

### Recommended next phase
- **Phase 16G — Git Tagging / Release Artifact Preparation**

---

## [v0.7.4-alpha] — Phase 16E Release Candidate Stabilization

本階段以 release candidate 穩定化為主：不新增核心功能、不新增 destructive action、
不改變既有指令語意；補強文件一致性（README / PROJECT_STATUS / CHANGELOG 版本對齊）、
release readiness checklist、command inventory snapshot、pyproject version strategy 說明、
release candidate notes、release smoke tests。

### Added
- `tests/test_release_readiness.py` — 17 個新測試（release readiness 驗收）：
  - **README 稽核（4）**：v0.7.4-alpha 版本存在、Release Candidate Notes 存在、
    local CLI / Mock LINE 介面說明、不適用多人 / production 場景記載。
  - **PROJECT_STATUS checklist（4）**：Release Readiness Checklist 存在、
    Rename workflow / Move workflow / runtime settings 已完成標記。
  - **CHANGELOG（1）**：v0.7.4-alpha Phase 16E 段落存在。
  - **版本策略（1）**：pyproject.toml 版本策略已文件化。
  - **Runtime / git（1）**：runtime JSON 無 git 追蹤。
  - **Destructive command 稽核（2）**：無新增 approved list 以外的 destructive 指令；
    四個 destructive regex 保持 ^…$ 全錨定。
  - **Help 功能回歸（1）**：說明 / help / /help / 指令說明 仍正常。
  - **Test file 存在（2）**：test_cli_smoke.py 與 test_end_to_end_workflow_audit.py 存在。
  - **Command Inventory（3）**：README 含 Command Inventory / 完整指令一覽、
    Non-destructive / Destructive 分類存在、四個 destructive 指令與多個 non-destructive 均列出。

### Changed
- `README.md`
  - 版本推進 v0.7.4-alpha（Phase 16E）。
  - 新增「完整指令一覽（Command Inventory）」— Non-destructive（8 指令）/
    Destructive full-match only（4 指令）明確分類。
  - 新增「Release Candidate Notes」— 目前版本與狀態、適用 / 不適用場景、安全提醒。
  - 「目前限制」補 pyproject.toml 版本策略說明（方案 A：0.1.0 為 packaging metadata，
    非 release version source of truth）。
- `docs/PROJECT_STATUS.md`
  - 版本推進 v0.7.4-alpha，測試數更新（628 → 648）。
  - 16E 加入 Completed Phases 表。
  - 新增「Release Readiness Checklist（v0.7.4-alpha）」— ✅ 18 項已完成、⬜ 5 項待完成。
  - 新增「Version Strategy（16E 決策，方案 A）」說明區塊。
  - Capability Snapshot 標題更新至 v0.7.4-alpha。
  - Safety Rule 58（Command Inventory / RC Notes 靜態文件）新增。
  - Known Limitations 補 16E release candidate 狀態說明。
  - Recommended Next Phase 更新為 16F。
- `tests/test_cli_smoke.py`
  - `test_readme_documents_version_and_positioning`：版本字串更新為 v0.7.4-alpha。

### Version strategy decision（Task 1，方案 A）
- **pyproject.toml version（0.1.0）維持不變** — 僅為 packaging metadata，非 release version source of truth。
- **Release 版本以 PROJECT_STATUS / CHANGELOG 的 RIP version 為準** — 目前 v0.7.4-alpha。
- 版本策略已在 README 目前限制區塊與 PROJECT_STATUS Version Strategy 區塊明確記載。

### Safety guarantees
- 未新增任何 destructive action、未新增任何 Mock LINE 指令、未改變既有指令語意。
- 四個 destructive regex（確認改名 / 回滾改名 / 確認搬移 / 回滾搬移）仍全數 ^…$ 全錨定（test_release_readiness.py 鎖定驗證）。
- 所有測試使用 tmp_path / monkeypatch；runtime JSON 持續 gitignored。

### Recommended next phase
- **Phase 16F — Release Candidate Tagging / Final Regression**

---

## [v0.7.3-alpha] — Phase 16D Packaging / CLI Smoke Test

本階段以 packaging、README、CLI smoke test、最小可交付檢查為主：
不改變任何核心功能；未新增 destructive action、未新增真實執行指令、
未改變既有 Mock LINE 指令語意、未修改 transaction log 行為。

### Added
- `README.md` — 開頭新增「Operator 快速上手」區塊：
  - 一句話定位（PDF intelligence / Approval workflow / Rename·Move safe execution
    本機文件智慧整理平台）與目前版本（v0.7.3-alpha）。
  - 主要能力九項（PDF / Document Intelligence、RenamePlan、MovePlan、Approval
    workflow、safe rename / safe move、transaction log、rollback preview /
    execution、runtime settings、Mock LINE operator interface）。
  - 安裝與測試（`poetry install`、`poetry run pytest -q`）。
  - Mock LINE 使用方式（說明 / 整理檔名 / 分析 PDF 詳細 / 整理資料夾 /
    產生搬移計畫）。
  - 安全操作指令表（確認 / 確認改名 / 預覽回滾改名 / 回滾改名 / 確認搬移 /
    預覽回滾搬移 / 回滾搬移，明確標示哪些會真的動檔案）。
  - 安全原則（planning 不改檔案、preview read-only、destructive full match、
    模糊文字不觸發、runtime JSON gitignored、相對路徑錨定 SAFE_PDF_ROOT）。
  - Runtime files 清單與目前限制（JSON persistence、本機 CLI 入口、
    help text 靜態維護、絕對路徑語意）。
- `tests/test_cli_smoke.py` — 22 個新測試：
  - **README 稽核（10）**：存在、版本與定位、install / pytest 指令、mock_line
    用法、planning 安全、destructive 指令與 full match、preview read-only、
    runtime files gitignored、SAFE_PDF_ROOT、known limitations（console_scripts）。
  - **Packaging 稽核（3）**：pyproject.toml 存在（poetry + pytest dev dep +
    packages include app）、`scripts/mock_line.py` 入口存在、module import 成功。
  - **CLI smoke（7）**：「說明」「/help」回覆 help、help 含六個 rename / move
    指令、help 零副作用（不建 approval、不建 log）、未知指令安全回覆不 crash、
    「整理檔名」對空 SAFE_PDF_ROOT 不 crash 且不動檔案、subprocess 真實 CLI
    跑「說明」exit 0 且 runtime JSON byte-level 零污染。
  - **Runtime / gitignore smoke（2）**：三個 runtime JSON 在 .gitignore、
    `git ls-files runtime/` 為空。

### Changed
- `docs/PROJECT_STATUS.md` — 版本推進 v0.7.3-alpha、測試數 628、16D 完成列表、
  capability snapshot 補 packaging 行、known limitations 補 console_scripts
  未提供與 pyproject version（0.1.0）未同步、Recommended Next Phase 改為 16E。
- 核心程式碼（app/、scripts/）零變更。

### Safety guarantees
- 未新增 destructive action、未新增真實執行指令；指令語意與 full match 規則
  零變更。
- Smoke 測試只透過無副作用路徑（help / 未知指令 / 空資料夾 planning）與
  read-only git 查詢；subprocess 僅限「說明」。
- 所有測試使用 tmp_path / monkeypatch；runtime JSON 持續 gitignored 且
  byte-level 驗證零污染。

### Recommended next phase
- **Phase 16E — Release Candidate Stabilization**。

---

## [v0.7.2-alpha] — Phase 16C Operator UX / Command Help Text

本階段只改善人機互動文字（help、錯誤訊息、下一步提示）：
未新增任何 destructive action、未新增真實執行指令、未改變既有 Mock LINE 指令語意、
未放寬 full match 規則、未修改 transaction log 行為。

### Added
- `scripts/mock_line.py`
  - Help 指令：「說明」「指令說明」「help」「/help」（full match 才生效；`_HELP_PATTERN`）。
    `command_help_text()` 純文字回覆，列出 Planning / Approval / Rename execution /
    Rename rollback / Move execution / Move rollback / 安全提醒七大分類，
    明確標示哪些指令會動檔案、哪些只是 dry-run / preview；零副作用
    （不建立 approval、不讀寫 transaction log、不碰任何檔案、不進 router）。
  - `humanize_reason(reason)`：17 個 reason code（approval_not_found、
    approval_not_approved、not_move_plan、not_rename_plan、already_executed、
    transaction_not_found、no_rollbackable_actions、already_fully_rolled_back、
    target_file_already_exists、original_file_not_found、rollback_source_not_found、
    rollback_target_already_exists、validation_has_blocked_candidates、
    path_escapes_safe_root、plan_not_approved、missing_validation_report、
    invalid_move_plan_payload）附中文說明與建議下一步；保留原始 code 方便 debug；
    未知 code 安全顯示不 raise。
- `tests/test_operator_help_text.py` — 16 個新測試（四種 help 指令 full match、
  模糊文字不觸發 help、七大分類涵蓋、destructive / non-destructive 標示、
  help 零副作用：不建 approval、不碰 transaction log、不改名不搬移檔案）。
- `tests/test_operator_error_messages.py` — 20 個新測試（reason code 中文說明
  與未知 code 安全顯示、錯誤回覆同時帶 code 與中文（整合）、execution 成功回覆
  的 preview / rollback 下一步提示、preview 回覆 read-only 明示、rollback 成功
  回覆 once-only 提示、「確認 {id}」核准回覆明示不會改名 / 搬移並提示明確執行
  指令、MovePlan 產生回覆維持「不直接提示確認搬移」不變式）。

### Changed（只改回覆文字，不改執行流程）
- `scripts/mock_line.py`
  - 錯誤回覆統一附「- 原因：{reason}：{中文說明}」（找不到 approval / 尚未核准 /
    已執行過 / 非對應計畫 / bridge gate 拒絕 / 找不到 transaction / 無可回滾 /
    已全部回滾）；檔案結果列的 reason 一律經 `humanize_reason()`。
  - 「確認改名」「確認搬移」成功回覆附下一步提示：「預覽回滾改名/搬移 {tx}」
    （只預覽，不會動檔案）與「回滾改名/搬移 {tx}」（會真的復原）。
  - 「預覽回滾改名」「預覽回滾搬移」回覆加註「預覽不會修改任何檔案或 transaction
    log」與 full match 提醒。
  - 「回滾改名」「回滾搬移」成功回覆加註「已完成回滾」與「同一 transaction_id
    不會重複回滾（once-only）」。
  - RenamePlan / MovePlan 產生回覆明示「確認 {id}」只核准 + dry-run、不會動檔案，
    並導引「指令說明」；MovePlan 回覆維持 15B 不變式（不直接出現「確認搬移」）。
- `app/router/ai_router.py` — 「確認 {approval_id}」的 dry-run 報告附帶
  `approval_id`（純顯示用途），讓核准回覆能提示「確認改名 {id}」「確認搬移 {id}」
  明確執行指令；dry-run 報告內容與核准流程不變。

### Safety guarantees
- 未新增 destructive action、未新增真實執行指令；六個 destructive / preview
  regex 與 full match 規則零變更（16A 稽核測試持續鎖定）。
- Help 指令零副作用（測試以 approval store / transaction log / filesystem
  snapshot 驗證）。
- 底層 result reason code 完全不變，只改輸出文字。
- 所有測試使用 tmp_path / monkeypatch，runtime JSON 持續 gitignored。

### Recommended next phase
- **Phase 16D — Packaging / CLI Smoke Test**。

---

## [v0.7.1-alpha] — Phase 16B Runtime Settings Consolidation

### Added
- `app/core/config.py`（沿用既有 pydantic Settings，未新增平行架構）—
  - `Settings.RUNTIME_DIR`（預設 `<repo>/runtime`）。
  - Runtime path helpers（動態讀 settings，monkeypatch `settings.RUNTIME_DIR` 即全面生效）：`get_runtime_dir()`、`get_approval_store_path()`、`get_rename_transaction_log_path()`、`get_move_transaction_log_path()`、`get_safe_pdf_root()`。
  - `resolve_under_safe_root(path, root=None)`：絕對路徑原樣回傳（既有語意不變）；相對路徑錨定 SAFE_PDF_ROOT（os.path.normpath 純字串正規化，不碰 filesystem、檔案不存在不 throw）；相對路徑逃出 root（path traversal）→ `ValueError("path_escapes_safe_root")`。
- `tests/test_runtime_settings.py` — 12 個新測試（四個預設路徑、monkeypatch 覆寫、approval manager / rename log / move log 預設改走 settings、gitignore 與 git 追蹤稽核、app//scripts/ 不再 hardcode runtime 路徑）。
- `tests/test_path_resolution.py` — 14 個新測試（絕對路徑不變、相對路徑錨定、不碰 filesystem、explicit root、traversal blocked（`../`、`a/../../`）、root 內 `..` 允許、rename/move execute 與 rollback 均可在相對路徑下運作且無需 chdir、executor 層 traversal fail-safe（`path_escapes_safe_root` failed result，不動任何檔案）、絕對路徑行為回歸）。

### Changed
- `app/approvals/manager.py` — 預設 store path 改用 `get_approval_store_path()`（行為相容：仍為 runtime/approvals.json）。
- `scripts/mock_line.py` — 移除 `_DEFAULT_TRANSACTION_LOG_PATH` 常數，三個使用點改 `get_rename_transaction_log_path()`；指令語意完全不變。
- `app/folder_intelligence/approval_bridge.py` — `default_move_transaction_log()` 改用 `get_move_transaction_log_path()`。
- `app/filename/executor.py`、`app/folder_intelligence/executor.py` — execute 與 rollback 的路徑建構改經 `resolve_under_safe_root()`：相對路徑錨定 SAFE_PDF_ROOT（修正 16A 稽核發現的 CWD 相依）；traversal → failed reason `path_escapes_safe_root`（fail-safe，不操作檔案）。
- `tests/test_end_to_end_workflow_audit.py` — Rename / Move E2E 移除 `monkeypatch.chdir`（錨定生效後不再需要）。
- `tests/test_mock_line_confirm_rename.py` — default log path 測試改 monkeypatch `settings.RUNTIME_DIR`。

### Safety guarantees
- 預設路徑與 16B 前完全相容；Mock LINE 指令集與語意零變更。
- 絕對路徑行為不變（既有測試與呼叫端的主要用法）；錨定只影響相對路徑。
- Path traversal 防護：相對路徑不可逃出 SAFE_PDF_ROOT，executor 以 failed result fail-safe 處理。
- runtime JSON 持續 gitignored 且不被 git 追蹤（測試固定稽核）。

### Recommended next phase
- **Phase 16C — Operator UX / Command Help Text**。

---

## [v0.7.0-alpha] — Phase 16A Production Hardening / End-to-End Workflow Audit

里程碑版本：Rename 與 Move 兩條主流程均完成安全閉環（planning → approval →
明確執行指令 → transaction log → read-only 預覽 → 明確回滾指令 → log cleanup），
本階段不新增功能，對全平台做生產化前稽核。

### Added
- `tests/test_end_to_end_workflow_audit.py` — 20 個稽核測試：
  - **Rename full E2E happy path**：「整理檔名」→ RenamePlan + approval →（模糊文字/未核准均被擋）→「確認 {id}」dry-run →「確認改名 {id}」真實改名 → rename transaction log →「預覽回滾改名」read-only（byte-level）→「回滾改名」復原 → 第二次回滾不重複執行。
  - **Move full E2E happy path**：「整理資料夾」→ MovePlan + approval →（模糊文字/未核准均被擋）→「確認 {id}」僅 dry-run →「確認搬移 {id}」真實搬移 → move transaction log →「預覽回滾搬移」read-only →「回滾搬移」復原 → 第二次回滾 `already_fully_rolled_back`。
  - **指令邊界稽核**：「確認改名」不執行 move plan、「確認搬移」不執行 rename plan、preview / rollback 指令各自只作用對應 log（rename log 與 move log 完全分離）、「整理檔名」「整理資料夾」非破壞性（filesystem 快照）、6 種模糊指令（請幫我確認改名/確認搬移/回滾改名/回滾搬移、回滾一下、確認一下）絕不動檔案或 log。
  - **Safety invariants**：mock_line destructive path 只經 bridge / by_id safe API（不可直接呼叫 low-level executors）；preview functions 不呼叫 rollback execution；prune functions 不呼叫 rename/move/rollback/filesystem API（AST）；六個指令 regex（確認改名/回滾改名/預覽回滾改名/確認搬移/回滾搬移/預覽回滾搬移）全數 `^…$` full match；cleanup 不接 Mock LINE。
  - **Runtime 稽核**：三個 runtime JSON 均在 .gitignore；`git ls-files runtime/` 必須為空（測試汙染不會進入版本控制）。

### Changed / Fixed
- `.gitignore` + git index — **稽核發現並修正**：`runtime/approvals.json` 先前被 git 追蹤且未列入 .gitignore，導致每次跑測試後 approval store 出現未提交變更；已加入 .gitignore 並自 git index 移除（`git rm --cached`，本機檔案保留）。自此 runtime/ 三個 JSON 全數 gitignored 且不被追蹤。

### Audit findings（記錄於 PROJECT_STATUS Known Limitations，留待 16B）
- Rename 計畫以純檔名存放、Move 計畫的 `proposed_path` 為相對路徑，executor 以 CWD 解析：CWD ≠ SAFE_PDF_ROOT 時執行會以 `original_file_not_found` fail-safe 拒絕（不會誤改檔案），但路徑解析未錨定 SAFE_PDF_ROOT。
- runtime log 路徑（rename / move transaction log、approval store）為各模組 hardcoded 預設，未整合 settings。

### Recommended next phase
- **Phase 16B — Runtime Settings Consolidation**（路徑錨定 + settings 整合）。

---

## [v0.6.9-alpha] — Phase 15J Move Transaction Log Rotation / Cleanup

### Added
- `app/folder_intelligence/schemas.py` — `MoveTransactionLogPruneResult`（before_count / after_count / pruned_count / retained_count / protected_count / corrupted_count / dry_run / pruned_transaction_ids / retained_transaction_ids / protected_transaction_ids / corrupted_entries）；語意：protected = 仍可回滾永不刪、retained = 未達清理條件、corrupted = 無法解析必須保留、pruned = 已清除。
- `app/folder_intelligence/transaction_log.py` —
  - `MoveTransactionLog.prune_transactions(older_than_days=30, dry_run=False, now=None)`：維運 API（鏡像 14F）。log 不存在 → 安全 no-op（不建立 log、不建資料夾）；整檔 invalid JSON / 結構錯誤 → 不刪不覆寫、corrupted 計數 ≥ 1；無法解析的 entry → 原樣保留（corrupted_entries）；任一 success action（rollbackable）→ 永不刪除（protected，即使過期）；全部 rolled_back 或只有 failed/pending/skipped → 超過 older_than_days 才刪，未過期保留（retained）；dry_run=True 只回報將刪除清單、不重寫 log；pruned_count == 0 不重寫 log；以 raw entry 過濾重寫，保留的 entry（含 corrupted 與未知欄位）原樣保留。
  - `prune_move_transactions(transaction_log, older_than_days=30, dry_run=False)`：module-level 便利 wrapper。
- `tests/test_move_transaction_log_rotation.py` — 25 個新測試（missing log no-op 不建檔不建資料夾、invalid JSON 不覆寫、corrupted entry 原樣保留、rollbackable 過期仍保留、old/recent × rolled_back/failed/pending 六種組合、dry_run 不重寫、no-op 不重寫（byte + mtime）、混合情境計數與三組 id 清單、corrupted_entries 回報、不搬移檔案不建資料夾（filesystem 快照）、rollback API monkeypatch guard、不改 action status、未知欄位原樣保留、Mock LINE 無 prune 接線、AST 驗證 prune functions 不碰 filesystem/rollback API、wrapper 委派與 dry_run）。

### Safety guarantees
- 仍可回滾的 transaction（任一 success action）永不刪除，即使符合過期條件。
- Corrupted / 無法解析 entry 永不刪除、原樣保留（不重新序列化、不丟失未知欄位）。
- Cleanup 只修改 log JSON：不檢查 filesystem、不搬移、不回滾、不建立或刪除實體檔案、不改變 action status。
- 僅為底層維運 API：未接任何 Mock LINE 指令（測試驗證 mock_line 原始碼不含 prune）。
- 「確認搬移」「預覽回滾搬移」「回滾搬移」行為完全不變。

### Recommended next phase
- **Phase 16A — Production Hardening / End-to-End Workflow Audit**。

---

## [v0.6.8-alpha] — Phase 15I Explicit Mock LINE Move Rollback Command

### Added
- `scripts/mock_line.py` — 明確「回滾搬移 {transaction_id}」指令（唯一可觸發真實 move rollback 的 Mock LINE 入口）：
  - `_ROLLBACK_MOVE_PATTERN = ^回滾搬移\s+([A-Za-z0-9_-]+)$`：full match 才生效；「回滾搬移」「回滾搬移一下 …」「請幫我回滾搬移 …」「預覽回滾搬移 …」「預覽搬移回滾 …」「回滾改名 …」「預覽回滾改名 …」「確認搬移 …」「確認改名 …」均不觸發。
  - `rollback_move(transaction_id, move_transaction_log=None)`：預設使用 `default_move_transaction_log()`；once-only guard（仿 14E）先以 read-only `preview_move_rollback_transaction_by_id()` 判斷 —— 找不到 → `transaction_not_found`、全部已回滾 → `already_fully_rolled_back`（不重複回滾）、無可回滾 → `no_rollbackable_actions`，三者皆不進入執行路徑；通過後一律透過 `rollback_move_transaction_by_id()` 執行並同步 log（成功 → `rolled_back`，失敗保持 `success`）。
  - `_format_move_rollback_execution_response()`：標題「搬移回滾結果」、transaction_id、executed/dry_run、總數/成功/失敗/跳過/blocked、每筆 original_path → proposed_path / status / reason / rollback_from / rollback_to；成功時附「已完成回滾搬移。」。
- `tests/test_mock_line_move_rollback_execution.py` — 27 個新測試（明確指令觸發 rollback spy、tmp_path 真實搬回檔案、log 標記 rolled_back、response 標題/flags/counts/rollback 路徑/「已完成回滾搬移」、transaction_not_found、無可回滾不進入執行路徑、once-only guard 不重複搬移/不破壞 log/不誤報 source missing、來源缺失與目標佔用 fail-safe（不覆寫、不標記 rolled_back）、部分回滾只更新成功 action、4 種模糊文字不觸發、「預覽回滾搬移」仍 read-only 不觸發 rollback、「回滾改名」「預覽回滾改名」不碰 move log、「確認搬移」「確認改名」不觸發 rollback、default_move_transaction_log() 預設路徑、AST 驗證 mock_line 不直接呼叫 rename/replace/move、不 import os/shutil）。

### Changed
- `scripts/mock_line.py` — 「確認搬移」成功回覆與「預覽回滾搬移」回覆中的「尚未開放回滾指令」提示更新為實際可用指令提示（「如需復原，請輸入：預覽回滾搬移 {tx}」「或輸入：回滾搬移 {tx}」/「若要執行回滾，請輸入：回滾搬移 {tx}」），比照 rename 流程（14D-3B 後的「確認改名」回覆）。
- `tests/test_move_transaction_log.py`、`tests/test_move_approval_bridge.py`、`tests/test_mock_line_confirm_move.py`、`tests/test_mock_line_move_rollback_preview.py` — 15H 時代「不可有『回滾搬移』指令 regex」「不可 import rollback_move_transaction_by_id」的不變式更新為 15I 現實：「回滾搬移」regex 必須存在且 full match（^…$）；`rollback_move_transaction_by_id` 為唯一允許的 rollback import（exact-name 比對，非 by_id 低階 API 與 executor 仍禁止）；「回滾搬移 {tx}」觸發測試改為模糊文字變形測試。

### Safety guarantees
- 真實 move rollback 唯一入口：「回滾搬移 {transaction_id}」full match；一律走 `rollback_move_transaction_by_id()`，Mock LINE 不直接操作 filesystem（AST 驗證）。
- Once-only guard：已全部回滾 → `already_fully_rolled_back`，不進入執行路徑、不動檔案、不寫 log、不誤報 `rollback_source_not_found`。
- Fail-safe：來源缺失 → `rollback_source_not_found`、原位置被佔用 → `rollback_target_already_exists`（不覆寫）；失敗的 action 保持 `success`，log 不被破壞；部分回滾只標記成功的 action。
- 「預覽回滾搬移」仍純讀取；rename 與 move 的 rollback 指令／transaction log 完全分離（互不影響，測試驗證）。
- 所有真實 rollback 測試使用 pytest tmp_path。

### Recommended next phase
- **Phase 15J — Move Transaction Log Rotation / Cleanup**。

---

## [v0.6.7-alpha] — Phase 15H Move Rollback Preview Command

### Added
- `app/folder_intelligence/schemas.py` — `MoveRollbackPreviewAction`（original_path / new_path / rollback_from / rollback_to / status / rollbackable / reason）與 `MoveRollbackPreview`（transaction_id / total / rollbackable_count / already_rolled_back_count / failed_count / actions；property：`has_rollbackable_actions`、`is_fully_rolled_back`）。
- `app/folder_intelligence/transaction_log.py` —
  - `preview_move_rollback_transaction(transaction)`：read-only preview；success + rollback 路徑存在 → rollbackable；rolled_back → `already_rolled_back`；failed → `action_failed`；success 缺路徑 → `missing_rollback_paths`；pending → `action_pending`。
  - `preview_move_rollback_transaction_by_id(transaction_id, transaction_log)`：載入持久化 transaction 後 preview；找不到 → None；不搬移、不建資料夾、不修改 transaction、不更新 log。
- `scripts/mock_line.py` — read-only「預覽回滾搬移 {transaction_id}」指令：
  - `_PREVIEW_MOVE_ROLLBACK_PATTERN = ^預覽回滾搬移\s+([A-Za-z0-9_-]+)$`：full match 才生效；「回滾搬移 …」「預覽搬移回滾 …」「請幫我預覽回滾搬移 …」「預覽回滾搬移」「預覽回滾搬移一下 …」「預覽回滾改名」「回滾改名」均不觸發。
  - `preview_move_rollback()`：使用 `default_move_transaction_log()`，只呼叫 `preview_move_rollback_transaction_by_id()`；不呼叫任何 rollback API。
  - `_format_move_rollback_preview_response()`：標題「搬移回滾預覽」、transaction_id、total/rollbackable_count/already_rolled_back_count/failed_count、每筆 original_path/new_path/rollback_from/rollback_to/status/rollbackable/reason、「這只是預覽，尚未實際回滾任何檔案。」；transaction 不存在 → `transaction_not_found`。
- `tests/test_move_rollback_preview.py` — 10 個新測試（success/rolled_back/failed/missing paths 語意、混合計數、by_id None/載入、log byte-level 不變、不搬移不建資料夾、AST 驗證 preview functions 不碰 filesystem）。
- `tests/test_mock_line_move_rollback_preview.py` — 16 個新測試（明確指令回傳 preview、response 標題/counts/rollback 路徑/「尚未實際回滾」提示、transaction_not_found、「回滾搬移」不觸發 rollback 或 preview（含 rollback API monkeypatch guard）、4 種模糊文字不觸發、「預覽回滾改名」「回滾改名」仍只作用 rename log、重複 preview log 不變、import 掃描（必須有 preview helper、不可 import executor/rollback API）、regex 掃描（須有 preview regex、不可有真實「回滾搬移」regex））。

### Changed
- `tests/test_move_transaction_log.py`、`tests/test_move_approval_bridge.py`、`tests/test_mock_line_confirm_move.py` — regex 不變式由「compiled pattern 不含『回滾搬移』」更新為「不可有以『回滾搬移』開頭的可執行指令 regex」（15H 的「預覽回滾搬移」read-only regex 為允許）。

### Safety guarantees
- Preview 純讀取：不 rollback、不搬移檔案、不建資料夾、不寫 transaction log（byte-level 測試 + AST 驗證）。
- 「回滾搬移 {transaction_id}」不是指令，不觸發任何 rollback 或 preview（rollback API monkeypatch guard 驗證）。
- 真實 move rollback 仍只能透過底層 API `rollback_move_transaction_by_id()` 在測試/程式中直接呼叫；Mock LINE 不 import、不呼叫。
- 所有測試使用 pytest tmp_path，不污染 runtime/。

### Recommended next phase
- **Phase 15I — Explicit Mock LINE Move Rollback Command**。

---

## [v0.6.6-alpha] — Phase 15G Explicit Mock LINE Confirm Move Command

### Added
- `scripts/mock_line.py` — 明確「確認搬移 {approval_id}」指令（唯一可觸發真實搬移的 Mock LINE 入口）：
  - `_CONFIRM_MOVE_PATTERN = ^確認搬移\s+([A-Za-z0-9_-]+)$`：full match 才生效；「確認」「搬移」「確認搬移」「確認搬移一下 …」「請幫我確認搬移 …」「整理資料夾」「產生搬移計畫」「確認改名」「回滾搬移」「預覽回滾搬移」均不觸發。
  - `confirm_move(approval_id, move_transaction_log=None)`：一律透過 `execute_approved_move_by_approval_id()`（15F move approval bridge，含 approval gates + once-only guard + `mark_executed()` 回寫）；不直接呼叫 move executor；預設使用 `default_move_transaction_log()`（`runtime/move_transactions.json`）。
  - `_format_move_execution_response()`：標題「搬移執行結果」、executed/dry_run、總數/成功/失敗/跳過/blocked、transaction_id（如有）、每筆 original_path → proposed_path / status / reason / rollback_from / rollback_to；`rollback_available=True` 時提示「已建立 rollback 資訊，但目前尚未開放 Mock LINE 回滾搬移指令」；未執行時顯示明確原因（approval_not_found / not_move_plan / approval_not_approved / already_executed / validation_has_blocked_candidates / target_file_already_exists / original_file_not_found 等）。
  - `mock_line_payload(text, transaction_log=None, move_transaction_log=None)`：新增可選 move log 注入（測試用 tmp_path）。
- `tests/test_mock_line_confirm_move.py` — 26 個新測試（明確指令觸發 bridge spy、tmp_path 真實搬移、transaction log 建立、response 標題/flags/counts/transaction_id/rollback 路徑/尚未開放提示、4 種模糊指令 + 「確認」不觸發搬移、planning 指令仍只 dry-run、「確認改名」拒絕 move plan、「回滾搬移」「預覽回滾搬移」不存在且不動檔案與 log、once-only guard 不重複搬移/不新增 transaction、approval_not_approved / approval_not_found / not_move_plan 回覆、目標 collision 不覆寫、high risk 跳過、blocked 不執行、import 掃描（必須有 bridge + default log、不可 import executor/rollback API）、AST 驗證無 move rollback 指令 regex）。

### Changed
- `tests/test_move_plan_workflow.py`、`tests/test_safe_move_executor.py`、`tests/test_move_transaction_log.py`、`tests/test_move_approval_bridge.py` — 15D/15E/15F 時代「Mock LINE 不可含『確認搬移』」的不變式更新為 15G 現實：「確認搬移」存在但必須走 bridge（`execute_approved_move_by_approval_id` in source、`execute_move_plan` not in source）；「回滾搬移」檢查由 raw substring 改為「不可存在可執行指令 regex」（提示訊息可提及尚未開放）。

### Safety guarantees
- 真實搬移唯一入口：「確認搬移 {approval_id}」full match；一律走 approval bridge（once-only guard 生效，同一 approval_id 不會重複搬移、不會新增第二筆 transaction）。
- 「確認 {approval_id}」仍只核准並顯示 move dry-run 報告，不搬移。
- Mock LINE 不直接呼叫 `execute_move_plan` / `rollback_move_transaction` / `rollback_move_transaction_by_id` / `MoveTransactionLog`（測試驗證）。
- 沒有任何 move rollback 指令（「回滾搬移」「預覽回滾搬移」不存在）。
- 所有真實搬移測試使用 pytest tmp_path；approval store 與 move log 均隔離。

### Recommended next phase
- **Phase 15H — Move Rollback Preview Command**。

---

## [v0.6.5-alpha] — Phase 15F Move Approval-to-Execution Bridge

### Added
- `app/folder_intelligence/approval_bridge.py` — 受控 approval-to-execution bridge（仿照 rename 的 14D-1），底層 API、未接 Mock LINE：
  - `execute_approved_move_plan(approval_payload, transaction_log=None) -> MoveExecutionResult`：驗證 payload 為 move plan（`plan_type == "move_plan"` 或 `type == "move_plan"`，否則 `not_move_plan`）→ 還原 MovePlan（支援 nested plan dict 與 15B 扁平 payload 兩種格式，無法還原 → `invalid_move_plan_payload`）→ 將 plan.status 同步為 `"approved"`（保留 validation_report、不破壞 candidates）→ 委派 `execute_move_plan(plan, transaction_log=...)`；提供 log 時持久化 MoveTransaction，未提供時行為不變。
  - `execute_approved_move_by_approval_id(approval_id, approval_manager, transaction_log=None) -> MoveExecutionResult`：approval-level gates 依序為 `approval_not_found` → `not_move_plan` → `approval_not_approved` → `already_executed`（once-only guard：payload 已有 `execution_status == "executed"` 即拒絕，不重複搬移）；通過後委派 `execute_approved_move_plan()`；至少一筆搬移成功才透過既有 `approval_manager.mark_executed()`（14E 機制）回寫 `execution_status="executed"` / `executed_at` / `execution_transaction_id`（有提供 log 時）；全數失敗（檔案未動）不標記，允許重試。
  - `default_move_transaction_log() -> MoveTransactionLog`：預設路徑 `runtime/move_transactions.json`（已列入 .gitignore）；測試一律使用 tmp_path。
- `app/folder_intelligence/__init__.py` — 匯出 `execute_approved_move_plan`、`execute_approved_move_by_approval_id`、`default_move_transaction_log`。
- `tests/test_move_approval_bridge.py` — 24 個新測試（non-move payload 拒絕、invalid payload 拒絕、nested/flattened payload 還原、status 同步為 approved 且不破壞 candidates/validation_report、low-risk tmp_path 真實搬移、有/無 transaction_log 行為、approval_not_found、非 move approval 拒絕、未核准拒絕、核准後執行、execution_status / executed_at / execution_transaction_id 回寫、once-only guard 不重複執行、重複呼叫不再搬移檔案且不新增 transaction、high risk 仍跳過且不標記 executed、blocked validation 仍拒絕、目標 collision 仍拒絕且不覆寫、Mock LINE 不含任何 move bridge/executor/rollback 引用、無「確認搬移」、無 move rollback 指令、AST 驗證 bridge 不直接碰 filesystem）。

### Safety guarantees
- Bridge 不直接碰檔案系統 — 一律委派 `execute_move_plan()`（AST 測試驗證無 rename/move/replace/mkdir 呼叫）。
- Once-only guard：同一 approval_id 成功執行後不可重複搬移（`already_executed`）。
- Mock LINE 仍不可觸發真實搬移或 move rollback：沒有「確認搬移」、沒有 move rollback 指令，原始碼不含 `execute_approved_move_plan` / `execute_approved_move_by_approval_id` / `execute_move_plan` / `rollback_move_transaction` / `MoveTransactionLog`（測試驗證）。
- 所有真實 move 測試使用 pytest tmp_path；approval store 與 transaction log 均隔離，不污染 runtime/。

### Recommended next phase
- **Phase 15G — Explicit Mock LINE Confirm Move Command**。

---

## [v0.6.4-alpha] — Phase 15E Move Transaction Log / Rollback Foundation

### Added
- `app/folder_intelligence/schemas.py` — `MoveTransactionAction`（original_path / new_path / status / rollback_from / rollback_to）與 `MoveTransaction`（transaction_id / plan_id / created_at / actions）；語意與 MoveFileResult 一致：`rollback_from` = 搬移後新位置、`rollback_to` = 原位置。
- `app/folder_intelligence/transaction_log.py` — `MoveTransactionLog`：JSON 持久化（鏡像 14C rename log），支援 `save_transaction`（upsert、自動建 parent dir）、`load_transaction`、`list_transactions`（log 缺失/壞損回 `[]`）、`update_transaction`、`mark_transaction_actions`（依 original_path 或 new_path 比對）；datetime 以 ISO 8601 序列化；無資料庫依賴。
- `app/folder_intelligence/executor.py` —
  - `execute_move_plan(plan, transaction_log=None)`：未提供 log 時行為與 15D 完全相同；提供 log 時執行前 save pending transaction、執行後標記 action success/failed。
  - `build_move_transaction(plan)`：只收 low/medium 可執行候選（排除 high/blocked/same_path/missing paths），action status="pending"。
  - `rollback_move_transaction(tx)`：只回滾 success action；`rollback_source_not_found` / `rollback_target_already_exists`（不覆蓋）；需要時自動重建原資料夾。
  - `rollback_move_transaction_by_id(transaction_id, transaction_log)`：找不到 → `transaction_not_found`；成功回滾標記 `rolled_back`；失敗保持 `success`、不破壞 log。
- `tests/test_move_transaction_log.py` — 28 個新測試（log CRUD、upsert 不覆蓋其他 transaction、datetime roundtrip、invalid JSON、mark by original/new path、build_move_transaction 過濾、execute 整合與 status 更新、無 log 行為不變、rollback 成功/來源缺失/目標佔用/重建資料夾/忽略非 success、by_id 全流程、failed rollback 不破壞 log、Mock LINE 無 move rollback 接線、「回滾改名」只作用 rename log、AST 驗證、plan gate 失敗不建 log、rename/move log 互不干擾）。
- `.gitignore` — 排除 `runtime/move_transactions.json`（建議的未來預設路徑；本階段未實際產生）。

### Safety guarantees
- 真實 move / rollback 只存在於 `app/folder_intelligence/executor.py`（AST 測試掃描 app/ 與 scripts/）。
- Mock LINE 不可觸發真實搬移或 move rollback：沒有「確認搬移」、沒有 move rollback 指令，原始碼不含 `execute_move_plan` / `rollback_move_transaction` / `MoveTransactionLog`（測試驗證）。
- 所有真實 move / rollback 測試使用 pytest tmp_path。

### Recommended next phase
- **Phase 15F — Move Approval-to-Execution Bridge**。

---

## [v0.6.3-alpha] — Phase 15D Safe Move Executor Design

### Added
- `app/folder_intelligence/executor.py` — `execute_move_plan(plan) -> MoveExecutionResult`，唯一可真實搬移檔案的模組（底層 API，未接 Mock LINE）。
  - Plan-level gates（先呼叫 `preflight_move_plan()`）：`plan_not_approved`、`missing_validation_report`、`validation_has_blocked_candidates` → `executed=False`，不搬移。
  - Candidate-level：blocked → blocked（`blocked_by_validation`，永不搬移）；high → skipped（`high_risk_requires_manual_review`）；same_path → skipped；missing paths → failed；來源不存在 → failed（`original_file_not_found`）；目標已存在 → failed（`target_file_already_exists`，不覆蓋）。
  - low / medium 通過檢查後：`mkdir(parents=True)` 建立目標資料夾 → `Path.rename()` 搬移。
  - 成功結果含 `rollback_from`（新位置）/ `rollback_to`（原位置）；`rollback_available=True` if 至少一筆成功；`dry_run=False`、`executed=True` if 至少一筆進入 filesystem 檢查。
- `app/folder_intelligence/__init__.py` — 匯出 `execute_move_plan`，docstring 標明 executor 為唯一搬移入口。
- `tests/test_safe_move_executor.py` — 22 個新測試（plan gates ×3、high/blocked 永不搬移、same_path、missing paths、來源不存在、目標 collision 不覆蓋、low/medium tmp_path 真實搬移、自動建立目標資料夾、source 移除、rollback_from/rollback_to、混合計數、Mock LINE 無「確認搬移」且不含 `execute_move_plan`、move planning 指令不觸發真實搬移、AST 驗證 app//scripts/ 真實 rename/move 只存在於兩個 executor module、preflight/workflow/rename 模組回歸）。

### Changed
- `tests/test_move_plan_workflow.py` — `test_no_real_move_executor_exists`（15B 時代不變式「executor.py 不可存在」）更新為 `test_move_executor_not_wired_to_mock_line`：executor.py 已存在（15D），但 Mock LINE 不可有「確認搬移」、不可引用 `execute_move_plan`。

### Safety guarantees
- 真實 move 只存在於 `app/folder_intelligence/executor.py`（AST 測試掃描 app/ 與 scripts/ 全部 .py）。
- Mock LINE 仍不支援真實搬移；沒有「確認搬移」指令。
- 所有真實搬移測試使用 pytest tmp_path，不碰真實 project files。

### Not yet implemented
- Move Transaction Log（成功搬移不持久化交易紀錄）。
- Move rollback（無 rollback function、無 rollback 指令）。

### Recommended next phase
- **Phase 15E — Move Transaction Log / Rollback Foundation**。

---

## [v0.6.2-alpha] — Phase 15C MovePlan Quality Gate / Preflight Design

### Added
- `app/folder_intelligence/schemas.py` — `MoveFileResult` / `MoveExecutionResult` execution schemas（目前僅供 read-only preflight 使用）。
- `app/folder_intelligence/preflight.py` — `preflight_move_plan(plan) -> MoveExecutionResult`。
  - 永遠回傳 `executed=False`、`dry_run=True`、`success_count=0`、`rollback_available=False`。
  - Plan-level gates：`plan_not_approved`、`missing_validation_report`、`validation_has_blocked_candidates`。
  - Candidate-level：missing original_path / proposed_folder / proposed_path → failed；blocked → blocked（`blocked_by_validation`）；same_path → skipped；high risk → skipped（`high_risk_requires_manual_review`）；low/medium → skipped（`preflight_passed_no_execution_in_phase_15c`）。
  - 不搬移檔案、不建立資料夾、不檢查真實 filesystem。
- `tests/test_move_preflight.py` — 15 個新測試（plan gates、各 candidate 狀態、混合計數、空計畫、tmp_path 驗證不建資料夾不搬移、AST 驗證無 os/shutil/pathlib import 與 rename/move/replace/mkdir 呼叫、executed/dry_run/success/rollback 不變式）。

### Safety guarantees
- **本階段沒有任何真實 move / rename / mkdir**：仍無 move executor、無「確認搬移」指令。
- Phase 15C 不可能出現 `success_count > 0`（每個測試都驗證不變式）。
- 既有 rename / rollback / MovePlan workflow 行為完全不變。

### Notes
- Task 4（dry-run 顯示掛 preflight summary）刻意略過：approval payload 的 plan status 不隨核准同步，直接掛 preflight 會永遠回 `plan_not_approved`；狀態同步屬 15D execution bridge 範疇（模式同 14D-1）。

### Recommended next phase
- **Phase 15D — Safe Move Executor Design**。

---

## [v0.6.1-alpha] — Phase 15B MovePlan Approval + Dry-run Workflow Integration

### Added
- `app/router/ai_router.py` — `move_planning` intent（關鍵字：「整理資料夾」「產生搬移計畫」「分析 PDF 並產生搬移計畫」「產生資料夾歸檔計畫」），route 至 pdf_worker `generate_move_plan`，建立 approval 並在 payload 標記 `plan_type="move_plan"`。
- `app/workers/pdf_worker.py` — `generate_move_plan` action：分析 PDF → 沿用 filename intelligence 建議檔名 → `build_move_plan()` → `validate_move_plan()` → 掛 validation_report → 回傳 dry-run move_plan。
- `app/workflows/executor.py` — `_execute_move_dry_run()`：「確認 {approval_id}」核准 move plan 後顯示 dry-run 報告（建議搬移目標、風險摘要、「本次沒有實際搬移任何檔案」），依 `plan_type` 與 RenamePlan payload 分流。
- `scripts/mock_line.py` — move planning 關鍵字 + `_format_move_plan_response()`（整合 `format_move_plan_for_cli()`，輸出標題、風險摘要、每筆建議、approval_id、「尚未實際搬移」提示）。
- `tests/test_move_plan_workflow.py` — 15 個新測試。

### Safety
- `_payload_to_rename_plan()` 防護：`plan_type=="move_plan"` 的 approval 不可被「確認改名」當成 RenamePlan 執行（有測試）。
- **仍無任何真實搬移**：沒有 move executor、沒有「確認搬移」指令（輸出與原始碼均有測試驗證）；核准 move plan 只產生 dry-run 報告。
- 既有 rename_planning intent、「整理檔名」「整理 Downloads」行為不變（有測試）；整合模組經 AST 驗證無 rename/move/replace 呼叫。

### Recommended next phase
- **Phase 15C — MovePlan Quality Gate / Preflight Design**。

---

## [v0.6.0-alpha] — Phase 15A Folder Intelligence / Move Plan Design

### Added
- `app/folder_intelligence/` — 新的 domain module（planning only，獨立於 `app/workers/folder_worker.py`，未推翻既有 worker）。
  - `schemas.py` — `MoveCandidate` / `MovePlan` / `MoveCandidateValidation` / `MoveValidationReport`。
    - MovePlan `dry_run=True`、`status="pending_approval"`、`requires_approval=True` by default。
  - `template.py` — deterministic folder template 規則。
    - Taipower bill → `電費單/{business_id}/{billing_period}/`（例：`電費單/24581234/2026-05/`）。
    - `sanitize_folder_segment()` 排除 `/`、`\`、`:` 等非法字元與相對路徑點號。
    - business_id / billing_period 缺失 → `unknown-business` / `unknown-period`。
    - unknown 文件 → `未分類/unknown-document/`。
  - `planner.py` — `build_move_plan(documents)`：支援 `extracted_fields` dict 與 rename pipeline 的 `document_object.fields` 結構；`proposed_filename` 優先於 original filename；不檢查真實 filesystem、不建立資料夾、不搬移檔案。
  - `validator.py` — `validate_move_plan(plan)` 風險分級：blocked（空計畫項目/缺路徑/缺資料夾/unknown 類型）、high（confidence < 0.7、fallback segment、同計畫 proposed_path 重複）、medium（confidence 0.7–0.9、目標與原路徑相同）、low（confidence ≥ 0.9 且無問題）。
  - `formatter.py` — `format_move_plan_for_cli(plan)` dry-run 輸出（原始檔、建議資料夾、目標路徑、confidence、risk、issues、「尚未實際搬移」提醒）。
- `tests/test_folder_intelligence_plan.py` — 20 個新測試。

### Safety guarantees
- **本階段只產生 MovePlan，無任何真實 move / rename**：沒有 move executor、沒有 Mock LINE 搬移指令（planning 指令整合留待 15B）。
- folder_intelligence 模組經 AST 驗證不得出現 `.rename()` / `.move()` / `.replace()` / `.mkdir()` 呼叫、不得 import os / shutil。
- 既有 rename / rollback pipeline 完全未改動，297 個既有測試原樣通過。

### Recommended next phase
- **Phase 15B — MovePlan Approval + Dry-run Workflow Integration**。

---

## [v0.5.6-alpha] — Phase 14F Rename Transaction Log Rotation / Cleanup

### Added
- `app/filename/transaction_log.py` — `RenameTransactionLog.prune_transactions(max_transactions=None, max_age_days=None, now=None)` 維運清理 API。
  - `max_age_days`：刪除建立超過 N 天的交易。
  - `max_transactions`：保留最新 N 筆，超額的舊交易刪除。
  - 兩條件可併用；皆未指定時為 no-op。
  - `now` 可注入（測試用），預設 UTC 現在時間。
- `app/filename/schemas.py` — `TransactionLogPruneResult` schema（total_before / total_after / pruned_count / kept_rollbackable_count / pruned_transaction_ids）。
- `tests/test_transaction_log_rotation.py` — 13 個新測試（依天數/筆數清理、可回滾交易保留、混合狀態保留、條件併用、no-op 不重寫檔案、損壞 entry 保留、不動實體檔案、prune 後 rollback 照常、rolled_back 後變為可清理的完整生命週期、空/不存在 log 安全處理）。

### Safety guarantees
- **永不刪除仍可回滾的交易** — 含任何 `success` action 的交易即使符合刪除條件也保留（計入 `kept_rollbackable_count`），rollback audit trail 不會遺失。
- 無法解析的 log entry 永不刪除。
- 只動 log 檔，不動任何實體檔案；無變更時不重寫檔案。
- **未新增任何 Mock LINE 指令** — prune 僅為維運 API；「確認改名」「預覽回滾改名」「回滾改名」與所有 rename / rollback 行為完全不變。

### Recommended next phase
- **Phase 15A — Folder Intelligence / Move Plan Design**。

---

## [v0.5.5-alpha] — Phase 14E Rename Execution Hardening / Once-only Guard

### Added
- **Approval once-only guard** — 同一 approval_id 不會重複執行真實 rename。
  - `app/approvals/manager.py` — 新增 `mark_executed(approval_id, transaction_id)`：在既有 payload dict 記錄 `execution_status="executed"` / `executed_at` / `execution_transaction_id` 並持久化（backward compatible：舊 approval 無 `execution_status` 視為尚未執行）。
  - `scripts/mock_line.py` — 「確認改名」執行前檢查 `execution_status`；已執行過則回覆「此改名計畫已執行過」+ transaction_id +「預覽回滾改名 / 回滾改名」復原提示，不呼叫 `execute_approved_rename_plan()`、不動檔案、不新增 transaction。
  - 標記條件：至少一筆 rename 成功；全數失敗（檔案未動）不標記，允許重試。
- **Rollback once-only guard** — 已無可回滾 action 時不進入 rollback 執行路徑。
  - `scripts/mock_line.py` — 「回滾改名」先以 read-only `preview_rollback_transaction()` 判斷；無可回滾 action 時不呼叫 `rollback_transaction_by_id()`、不動檔案、不寫 log。全部已回滾 → 「此交易已回滾完成（已回滾 N 筆）」；其餘 → 「沒有可回滾項目」。部分 rolled_back 仍可回滾剩餘 success action。
- `app/filename/schemas.py` — `RollbackPreview` 新增 `has_rollbackable_actions` / `is_fully_rolled_back` properties（重用 preview，未新增重複邏輯）。
- 「預覽回滾改名」回覆強化：無可回滾項目時提示「目前沒有可回滾項目」，全部回滾完成時顯示「此交易已全部回滾」。
- `tests/test_once_only_guard.py` — 16 個新測試（含 parametrize 展開；首次執行、重複確認擋下（monkeypatch 驗證不呼叫 bridge）、execution_status 持久化、全敗可重試、重複回滾擋下（log byte-level 不變）、部分回滾、預覽 fully rolled_back、狀態 properties、模糊文字不觸發）。

### Changed
- `tests/test_mock_line_confirm_rename.py` — 重複確認測試改驗證 once-only guard（原 14D-2 行為：第二次回報 original_file_not_found；14E 起：直接回覆已執行過且不新增 transaction）。

### Safety guarantees
- 明確指令格式不變：「確認改名 {approval_id}」「預覽回滾改名 {transaction_id}」「回滾改名 {transaction_id}」。
- 模糊文字仍不觸發任何真實 rename / rollback。
- Dry-run 行為不變；Mock LINE 仍不直接呼叫 `Path.rename`。
- 所有檔案異動測試使用 `pytest tmp_path`；approval store 與 transaction log 均隔離。

### Recommended next phase
- **Phase 15A — Folder Intelligence / Move Plan Design**（或 Phase 14F — Rename Transaction Log Rotation / Cleanup）。

---

## [v0.5.4-alpha] — Phase 14D-3B Explicit Mock LINE Rollback Execution Command

### Added
- `scripts/mock_line.py` — 明確 rollback 執行指令「回滾改名 {transaction_id}」。
  - regex 完全比對（`^回滾改名\s+(\S+)$`）；「回滾」「回滾改名」（無 id）、「請回滾改名 {id}」「回滾改名 {id} 謝謝」「回滾改名{id}」均不觸發。
  - 一律透過 `rollback_transaction_by_id(transaction_id, transaction_log)` 執行；Mock LINE 不直接呼叫 `Path.rename`（AST 驗證）。
  - 成功回滾的 action 在 transaction log 中更新為 `rolled_back`；失敗的維持 `success`。
  - 回覆內容：transaction_id、成功/失敗/跳過/blocked 統計、每筆檔案結果與原因。
  - 失敗回覆：找不到 transaction、`rollback_source_not_found`、`rollback_target_already_exists`、沒有可回滾項目。
  - 預設 transaction log 路徑沿用 `runtime/rename_transactions.json`。
- `tests/test_rollback_execution.py` — 16 個新測試（含 parametrize 展開；執行回滾與檔案復原、log 狀態更新、找不到 transaction、來源不存在、目標被佔用、沒有可回滾項目、模糊文字/不完全格式不觸發、preview 仍不 rollback、AST 驗證、monkeypatch 驗證委派 `rollback_transaction_by_id()`、混合 action 與重複回滾）。

### Changed
- `tests/test_rollback_preview.py` — 兩處配合 14D-3B 設計更新：
  - 「回滾改名 {id} 不執行」測試改為驗證格式不完全符合的變體不觸發（完全比對的執行行為移至新測試檔）。
  - preview 隔離測試加入對 `mock_line.rollback_transaction_by_id` 的 monkeypatch 防護，原始碼檢查改限定 transaction_log 模組。

### Safety guarantees
- 「預覽回滾改名 {transaction_id}」仍只預覽：不改檔案、不寫 log、不呼叫 `rollback_transaction_by_id()`（monkeypatch + byte-level 驗證）。
- 「確認改名 {approval_id}」維持 14D-2 行為不變；一般 rename planning 指令仍不觸發任何真實檔案異動。
- Rollback 不覆寫檔案：目標被佔用即回報失敗。
- 所有檔案異動測試使用 `pytest tmp_path`，transaction log 一律注入隔離路徑。

### Recommended next phase
- **Phase 14E — Rename Execution Hardening / Once-only Guard**。

---

## [v0.5.3-alpha] — Phase 14D-3A Mock LINE Rollback Preview Command

### Added
- `scripts/mock_line.py` — 明確預覽指令「預覽回滾改名 {transaction_id}」。
  - regex 完全比對（`^預覽回滾改名\s+(\S+)$`）；無空白、附加多餘文字均不觸發。
  - 純讀取：查詢 transaction log → 回覆交易摘要，不 rollback、不更名、不寫 log。
  - 回覆內容：交易 ID、Plan ID、可回滾/已回滾/失敗/pending 統計、每筆 action 路徑與狀態、「目前僅預覽，尚未執行回滾」提醒。
  - transaction_id 不存在 → 回覆「找不到 transaction：{id}」。
- `app/filename/transaction_log.py` — `preview_rollback_transaction(transaction_id, transaction_log)` read-only helper。
  - 找不到 transaction 回傳 None。
  - rollbackable 判斷：status == "success" 才可回滾；rolled_back / failed / pending 不可。
- `app/filename/schemas.py` — `RollbackPreview` / `RollbackPreviewAction` schemas。
- `tests/test_rollback_preview.py` — 20 個新測試（含 parametrize 展開；查詢、找不到、模糊文字/不完全格式不觸發、「回滾改名 {id}」不真實 rollback、log byte-level 不變、不呼叫 rollback 函式（monkeypatch + 原始碼驗證）、不動檔案、AST 驗證無 rename 呼叫、各狀態 rollbackable 判斷、混合統計）。

### Safety guarantees
- 本階段**沒有任何指令會真實 rollback** — 「回滾」「回滾改名 {id}」「預覽回滾」「預覽回滾改名」（無 id）均不觸發任何 rollback 或 preview 以外的行為。
- Preview 不呼叫 `rollback_transaction_by_id()` / `rollback_rename_transaction()` / `Path.rename`。
- Preview 不更新 transaction log（測試驗證檔案 bytes 不變）。
- 「確認改名 {approval_id}」維持 Phase 14D-2 行為，仍是唯一可觸發真實更名的指令。

### Recommended next phase
- **Phase 14D-3B — Explicit Mock LINE Rollback Execution Command**。

---

## [v0.5.2-alpha] — Phase 14D-2 Explicit Mock LINE Confirm Rename Command

### Added
- `scripts/mock_line.py` — 明確確認改名指令「確認改名 {approval_id}」。
  - 唯一可觸發真實更名的 Mock LINE 指令；regex 完全比對（`^確認改名\s+(\S+)$`），附加任何多餘文字均不觸發。
  - 流程：查詢 approval → 驗證已核准 → payload 轉回 `RenamePlan`（最小 adapter）→ `execute_approved_rename_plan()` → 寫入 `RenameTransactionLog` → 回覆執行摘要。
  - 回覆內容：成功/失敗/跳過/blocked 統計、transaction_id、每筆檔案結果與原因。
  - 失敗回覆：找不到 approval、approval 尚未核准（提示先輸入「確認 {approval_id}」）、payload 不是改名計畫、缺 validation_report、含 blocked candidate。
  - 改名計畫輸出新增提示行：「核准後若要實際執行改名，請輸入：確認改名 {approval_id}」。
- Transaction log 預設路徑：`runtime/rename_transactions.json`（目錄不存在自動建立）。
- `.gitignore` 排除 `runtime/rename_transactions.json`。
- `tests/test_mock_line_confirm_rename.py` — 18 個新測試（含 parametrize 展開；模糊文字不觸發、未核准/非 rename plan/blocked/缺 validation_report 拒絕、低風險執行、高風險跳過、目標已存在失敗、重複執行不覆寫、預設 log 路徑、AST 驗證不直接 rename，approval store 隔離至 tmp_path）。

### Changed
- `tests/test_approval_bridge.py` — Mock LINE 隔離測試改為驗證「真實更名僅限明確確認指令格式」（14D-1 時 bridge 尚未接入 Mock LINE，14D-2 起刻意接入）。

### Safety guarantees
- 「整理檔名」「產生改名計畫」「分析 PDF 並產生改名計畫」等通用指令仍**不會**觸發真實更名。
- 「確認」「確認改名」（無 id）、「好」「OK」「執行」等模糊文字**不會**觸發真實更名。
- 「確認 {approval_id}」維持原行為：核准 + dry-run 報告，不觸發真實更名。
- Rollback 指令仍未開放（Phase 14D-3 範疇）。
- Mock LINE 不直接呼叫 `Path.rename`；真實更名僅透過 approval bridge → safe rename executor。
- 所有真實更名測試使用 `pytest tmp_path`，approval store 與 transaction log 均隔離。

### Recommended next phase
- **Phase 14D-3 — Explicit Mock LINE Rollback Command**。

---

## [v0.5.1-alpha] — Phase 14D-1 Approval-to-Execution Bridge

### Added
- `app/filename/approval_bridge.py` — 受控 application-layer bridge。
  - `execute_approved_rename_plan(plan, transaction_log=None)` — 接收已核准、已驗證的 RenamePlan，透過既有 Safe Rename Executor 安全執行。
    - Gate 1：`plan.status != "approved"` → `executed=False`、`dry_run=False`、reason `"plan_not_approved"`，不呼叫 executor。
    - Gate 2：`validation_report` 缺失 → reason `"missing_validation_report"`，不呼叫 executor。
    - Gate 3：`validation_report.blocked_count > 0` → reason `"validation_has_blocked_candidates"`，不呼叫 executor。
    - 通過後委派 `execute_rename_plan(plan, transaction_log=...)`，保留 preflight 與所有 per-candidate 安全規則。
  - `execute_approved_rename_by_plan_id(plan_id, plan_loader, transaction_log=None)` — 以注入式 `plan_loader` 載入 plan；找不到 → reason `"plan_not_found"`，找到則委派 `execute_approved_rename_plan()`。
- `tests/test_approval_bridge.py` — 15 個新測試（gate 拒絕、低/中風險執行、高風險跳過、transaction log 整合、AST 驗證 bridge 不直接 rename、Mock LINE 隔離、plan_id helper）。

### Safety guarantees
- Mock LINE 仍**不會**觸發真實更名 — bridge 未接到任何 Mock LINE 指令（Phase 14D-2 才加入明確確認指令）。
- Rollback 指令仍未對使用者開放。
- Bridge 不直接呼叫 `Path.rename` / `os.rename` / `shutil.move`，真實更名僅透過 `execute_rename_plan()`。
- 所有檔案系統測試使用 `pytest tmp_path`。

### Recommended next phase
- **Phase 14D-2 — Explicit Mock LINE Confirm Rename Command**。

---

## [v0.5.0-alpha] — Phase 14C Persistent Transaction Log & Rollback Audit Trail

### Added
- `app/filename/transaction_log.py` — `RenameTransactionLog` 類別。
  - `save_transaction(tx)` — 新增或 upsert transaction（依 transaction_id）。
  - `load_transaction(id)` — 依 id 讀取；找不到回傳 None。
  - `list_transactions()` — 回傳所有 transaction；log 不存在或損壞時回傳空 list。
  - `update_transaction(tx)` — 取代既有 transaction 或新增。
  - `mark_transaction_actions(id, updates)` — 以 original_path 或 new_path 為 key 更新 action status。
- `execute_rename_plan(plan, transaction_log=None)` — 新增可選 `transaction_log` 參數。
  - 若提供，執行前建立 transaction 並寫入 log，執行後更新 action 狀態（success/failed）。
  - 不提供時行為與 Phase 14B 完全相同（零破壞）。
- `rollback_transaction_by_id(transaction_id, transaction_log)` — 從 log 載入並 rollback。
  - 找不到 id → 回傳 `reason="transaction_not_found"`。
  - 成功 rollback → 將 action 狀態更新為 `"rolled_back"`。
  - rollback 失敗 → action 狀態維持 `"success"`（檔案仍在更名位置）。

### Storage
- JSON 格式，`{"transactions": [...]}` 結構。
- datetime 以 ISO 8601 字串存入，Pydantic `model_validate()` 自動反序列化。
- 損壞的 JSON 被安全忽略（回傳空 list / None），不拋出例外。
- 父目錄不存在時自動建立。

### Safety guarantees
- Mock LINE 通用改名指令及確認流程仍走 dry-run，不觸發 `execute_rename_plan()` 或 `rollback_transaction_by_id()`。
- 所有檔案系統測試使用 `pytest tmp_path`。

---

## [v0.4.0-alpha] — Phase 14B Safe Rename Executor

### Added
- `app/filename/executor.py` — Phase 14B 唯一可執行真實更名的模組。
- `execute_rename_plan(plan)` — 安全執行已核准 RenamePlan。
  - 先呼叫 `preflight_rename_plan()` 作為計畫層級 gate。
  - 逐一檢查候選項：missing path → failed、blocked → blocked、same filename → skipped、high risk → skipped。
  - 實際更名前再檢查：原始檔不存在 → failed、目標已存在 → failed。
  - 成功更名記錄 `rollback_from` / `rollback_to`。
  - `executed=True` 當有任何候選項進入檔案系統檢查階段。
  - `rollback_available=True` 當有至少一個成功更名。
- `build_rename_transaction(plan)` — 建立只含 low/medium 候選項的 in-memory `RenameTransaction`。
- `rollback_rename_transaction(transaction)` — 回滾所有 `status=="success"` 的 action。
  - rollback 來源不存在 → failed (`rollback_source_not_found`)。
  - rollback 目標已存在 → failed (`rollback_target_already_exists`)。

### Safety guarantees
- Mock LINE 通用改名指令（`產生改名計畫`、`整理檔名` 等）**不觸發** `execute_rename_plan()`，仍走 dry-run。
- Blocked / high-risk 候選項永遠不會被更名。
- 真實更名僅限 `app/filename/executor.py`，其他模組不呼叫 `Path.rename()`。
- 所有更名測試使用 `pytest tmp_path`，不修改任何真實專案檔案。

### Known limitations
- `RenameTransaction` 僅存於記憶體，不持久化（Phase 14C 範疇）。
- rollback audit trail 尚未實作。

---

## [v0.2.1-alpha] — Phase 13.5 Rename Plan Quality Gate

### Added
- `ValidationReport` schema with per-candidate risk level and issue list.
- `validate_rename_plan()` function in `app/filename/validator.py`.
  - Risk levels: `low`, `medium`, `high`, `blocked`.
  - Blocked conditions: unknown document type, missing proposed filename, confidence < 0.5.
  - High-risk condition: duplicate proposed filename across candidates.
  - Medium-risk condition: confidence between 0.5 and 0.9, or proposed equals original.
- Mock LINE CLI now displays risk summary (low / medium / high / blocked counts).
- Dry-run confirmation output includes risk summary.
- `RenamePlan.validation_report` field stores the ValidationReport inline.

### Changed
- `PDFWorker.generate_rename_plan()` now calls `validate_rename_plan()` automatically.

### Safety
- No actual file rename implemented.
- Blocked and high-risk candidates are surfaced in the report but never executed.

---

## [v0.2.0-alpha] — Phase 13 Filename Intelligence / Rename Plan

### Added
- `RenameCandidate` and `RenamePlan` schemas (`app/filename/schemas.py`).
- `build_rename_plan()` in `app/filename/planner.py` — converts PDF summaries to a plan.
- `build_taipower_filename()` in `app/filename/template.py` — constructs normalized filenames.
- `sanitize_filename()` in `app/filename/normalizer.py` — strips invalid characters, enforces length limits.
- Mock LINE CLI commands: `產生改名計畫`, `整理檔名`, `分析 PDF 並產生改名計畫`.
- Mock LINE CLI rename approval flow (`確認 <approval_id>`).
- Collision resolution: appends `_2`, `_3`, … when two files would share a proposed name.
- `PDFWorker` action `generate_rename_plan` integrated into AI Router.

### Safety
- `RenamePlan.dry_run=True` and `requires_approval=True` by default.
- No actual file rename implemented.

---

## [v0.1.x-alpha] — Phases 1–12 Core Platform Foundation

### Added
- AI Router with intent detection for LINE messages.
- Workflow Engine and multi-step workflow support.
- Approval Engine (create / confirm / cancel approvals).
- Dry-run Executor with step-level reporting.
- PDF Intelligence: read, classify, and extract fields from PDF files.
- Document Intelligence: `DocumentType` classifier and field extractor.
- Taipower electricity bill field extraction (account number, billing period, payable amount).
- Mock LINE CLI for local end-to-end testing.
- Docker / docker-compose setup.
- Folder worker for folder analysis.

---

---

## [v0.3.0-alpha] — Phase 14A Safe Rename Executor Schemas & Preflight

### Added
- `RenameFileResult` schema — per-file execution result with status, reason, risk_level, and optional rollback fields.
- `RenameExecutionResult` schema — plan-level execution summary with counts (success/failed/skipped/blocked).
- `RenameTransactionAction` schema — single rename action with lifecycle status.
- `RenameTransaction` schema — groups actions for a plan with a transaction ID and timestamp.
- `preflight_rename_plan()` in `app/filename/preflight.py` — validates a RenamePlan before any execution attempt.

### Preflight rules
- Non-approved plans: all candidates blocked (`plan_not_approved`).
- Missing `validation_report`: all candidates blocked (`missing_validation_report`).
- Any `blocked_count > 0` in report: all candidates blocked (`validation_has_blocked_candidates`).
- Blocked candidates: status `blocked`.
- High-risk candidates: status `skipped` (`high_risk_requires_manual_review`).
- Missing `original_path`: status `failed`.
- Missing `proposed_path`: status `failed`.
- Same filename: status `skipped` (`same_filename`).
- Low/medium candidates: status `skipped` (`preflight_passed_no_execution_in_phase_14a`).

### Safety guarantees
- `executed` is always `False`.
- `dry_run` is always `True`.
- `rollback_available` is always `False`.
- `success_count` is always `0`.
- No `os.rename`, `Path.rename`, or `shutil.move` calls anywhere in Phase 14A.

---

## Upcoming

### Phase 14D — Controlled User Confirmation Path for Safe Rename

- 將 `execute_rename_plan()` 整合進 Mock LINE 確認流程。
- 使用者輸入「確認 {approval_id}」後觸發真實更名並寫入 transaction log。
- 提供「回滾 {transaction_id}」指令讓使用者撤銷更名。
- 更新 Mock LINE 輸出顯示執行結果（success / failed / skipped counts）。
