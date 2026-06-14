# Rex Intelligence Platform（RIP）Release Notes

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

### Commits Since v0.7.5-alpha

| Commit | Phase | 說明 |
|--------|-------|------|
| `47a4128` | 18B | refactor(approvals): extract JSON approval store |
| `31c1037` | 18C | refactor(transactions): extract shared JSON log IO |
| `c5434ff` | 18E | refactor(transactions): define transaction log protocols |

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
