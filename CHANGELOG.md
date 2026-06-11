# Changelog — Rex Intelligence Platform (RIP)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
