# Changelog — Rex Intelligence Platform (RIP)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
