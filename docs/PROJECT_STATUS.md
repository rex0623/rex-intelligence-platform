# Rex Intelligence Platform (RIP) — Project Status

## Overview

| Field | Value |
|-------|-------|
| **Project** | Rex Intelligence Platform (RIP) |
| **Current Version** | v0.7.4-alpha |
| **Test Count** | 709 passing |
| **Last Updated** | 2026-06-13 |

---

## Completed Phases

| Phase | Title | Status |
|-------|-------|--------|
| 1–12 | Core Platform Foundation | ✅ Complete |
| 13 | Filename Intelligence / Rename Plan | ✅ Complete |
| 13.5 | Rename Plan Quality Gate | ✅ Complete |
| 14A | Safe Rename Executor Schemas & Preflight | ✅ Complete |
| 14B | Safe Rename Executor | ✅ Complete |
| 14C | Persistent Transaction Log & Rollback Audit Trail | ✅ Complete |
| 14D-1 | Approval-to-Execution Bridge | ✅ Complete |
| 14D-2 | Explicit Mock LINE Confirm Rename Command | ✅ Complete |
| 14D-3A | Mock LINE Rollback Preview Command | ✅ Complete |
| 14D-3B | Explicit Mock LINE Rollback Execution Command | ✅ Complete |
| 14E | Rename Execution Hardening / Once-only Guard | ✅ Complete |
| 14F | Rename Transaction Log Rotation / Cleanup | ✅ Complete |
| 15A | Folder Intelligence / Move Plan Design | ✅ Complete |
| 15B | MovePlan Approval + Dry-run Workflow Integration | ✅ Complete |
| 15C | MovePlan Quality Gate / Preflight Design | ✅ Complete |
| 15D | Safe Move Executor Design | ✅ Complete |
| 15E | Move Transaction Log / Rollback Foundation | ✅ Complete |
| 15F | Move Approval-to-Execution Bridge | ✅ Complete |
| 15G | Explicit Mock LINE Confirm Move Command | ✅ Complete |
| 15H | Move Rollback Preview Command | ✅ Complete |
| 15I | Explicit Mock LINE Move Rollback Command | ✅ Complete |
| 15J | Move Transaction Log Rotation / Cleanup | ✅ Complete |
| 16A | Production Hardening / End-to-End Workflow Audit | ✅ Complete |
| 16B | Runtime Settings Consolidation | ✅ Complete |
| 16C | Operator UX / Command Help Text | ✅ Complete |
| 16D | Packaging / CLI Smoke Test | ✅ Complete |
| 16E | Release Candidate Stabilization | ✅ Complete |
| 16F | Release Candidate Tagging / Final Regression | ✅ Complete |
| 16G | Git Tagging / Release Artifact Preparation | ✅ Complete |
| 17A | console_scripts Entry Point | ✅ Complete |
| 17B | Runtime Lock / Concurrency Guard | ✅ Complete |
| 17C | Operator Deployment / Backup / Restore Runbook | ✅ Complete |

---

## Release Readiness Checklist（v0.7.4-alpha）

- [x] RenamePlan workflow completed
- [x] Rename safe execution completed
- [x] Rename rollback preview completed
- [x] Rename rollback execution completed
- [x] Rename transaction cleanup completed
- [x] MovePlan workflow completed
- [x] Move safe execution completed
- [x] Move rollback preview completed
- [x] Move rollback execution completed
- [x] Move transaction cleanup completed
- [x] Operator help text completed
- [x] Runtime settings consolidated
- [x] CLI smoke tests completed
- [x] E2E audit tests completed
- [x] Runtime files gitignored
- [x] Release readiness checklist completed（16E）
- [x] Command inventory documented（16E）
- [x] Version strategy documented（16E）
- [x] RELEASE_NOTES.md completed（16F）
- [x] Final regression audit completed（16F）
- [x] Tag readiness checklist completed（16F）
- [x] Package artifact built and verified（16G）
- [x] Tagging instructions documented（16G）
- [x] pyproject version strategy final decision confirmed（16G，方案 A）
- [x] Formal console_scripts entry point（17A）
- [x] Runtime lock / concurrent access guard（17B）
- [x] Production deployment guide / Operator Runbook（17C）
- [ ] Packaged release artifact
- [ ] SQLite / DB persistence option

---

## Version Strategy（16E 決策，16G 最終確認，方案 A）

- **pyproject.toml version（0.1.0）維持不變** — 僅為 packaging metadata，非 release version source of truth。
- **Release 版本以 PROJECT_STATUS / CHANGELOG / README / RELEASE_NOTES 的 RIP version 為準** — 目前 v0.7.4-alpha。
- **`poetry build` 產生的 artifact 版本為 0.1.0**（來自 pyproject.toml），非 RIP release version；artifact 名稱 `rex_intelligence_platform-0.1.0.tar.gz`。
- 版本對齊（例如 0.7.4a0）留待正式 release packaging（16H+）；`poetry check` 有 deprecation warnings（`[tool.poetry]` 遷移），但非 errors，不影響目前 build。

---

## Tag Readiness Checklist（v0.7.4-alpha）

- [x] Final regression tests passed（test_final_regression_release_candidate.py，16F）
- [x] README updated（v0.7.4-alpha、Command Inventory、Release Candidate Notes、RELEASE_NOTES 連結）
- [x] CHANGELOG updated（16E + 16F + 16G 條目）
- [x] RELEASE_NOTES updated（docs/RELEASE_NOTES.md，v0.7.4-alpha，含 Tagging Instructions）
- [x] PROJECT_STATUS updated（Tag Readiness Checklist、16G 完成）
- [x] Runtime files gitignored（runtime/ 三個 JSON，git ls-files 驗證）
- [x] Command inventory documented（README 完整指令一覽）
- [x] Release readiness checklist completed（21 項 ✅）
- [x] Tagging instructions documented（RELEASE_NOTES Tagging Instructions，16G）
- [x] Package artifact built（dist/，gitignored，未 commit；poetry build 成功，16G）
- [x] Working tree clean before tag（git status --short 為空確認）
- [ ] Git tag created（人工執行：`git tag -a v0.7.4-alpha -m "RIP v0.7.4-alpha"`）
- [ ] Tag pushed（人工執行：`git push origin v0.7.4-alpha`）
- [ ] Production deployment guide completed
- [ ] pyproject version aligned（選做：0.1.0 → 0.7.4a0，留待 16H+）

---

## Current Capability Snapshot（v0.7.4-alpha）

**Rename capabilities**：RenamePlan → Approval → Confirm rename（「確認改名」）→ Transaction log → Rollback preview（「預覽回滾改名」）→ Rollback execution（「回滾改名」）→ Log cleanup（`prune_transactions`，14F）

**Move capabilities**：MovePlan → Approval → Confirm move（「確認搬移」）→ Transaction log → Rollback preview（「預覽回滾搬移」）→ Rollback execution（「回滾搬移」）→ Log cleanup（`prune_transactions`，15J）

**Safety rules（核心不變式，均有 E2E / AST / regex 稽核測試，16A）**：
- Destructive commands require full match — 六個指令 regex 全數 `^…$` 錨定。
- Dry-run planning commands never mutate files — 「整理檔名」「整理資料夾」純產生計畫。
- Preview commands never mutate files or logs — byte-level 驗證。
- Cleanup never touches filesystem — 只動 log JSON，且不接 Mock LINE。
- Runtime logs are gitignored — `runtime/approvals.json`、`runtime/rename_transactions.json`、`runtime/move_transactions.json` 均不被 git 追蹤。
- Runtime paths are consolidated（16B）— 所有 runtime 路徑由 `app/core/config.py` 的 settings helpers 單一來源提供；相對路徑由 executor 層錨定 SAFE_PDF_ROOT，path traversal 以 `path_escapes_safe_root` fail-safe 拒絕。
- Operator UX（16C）— 「說明 / 指令說明 / help / /help」回覆完整指令分類；錯誤 reason code 一律附中文說明與建議下一步（`humanize_reason()`）；execution / rollback / 核准回覆附下一步提示。
- Packaging / 可交付性（16D）— README 開頭含 Operator 快速上手（安裝 / 測試 / Mock LINE 用法 / 安全指令表 / 安全原則 / runtime files / 目前限制）；`tests/test_cli_smoke.py` 鎖定 README 文件內容、pyproject metadata、CLI 入口可用性與 runtime / gitignore 行為。

---

## Operator Commands Snapshot（Mock LINE，16C）

| 分類 | 指令 | 動檔案？ |
|------|------|---------|
| Help | `說明` / `指令說明` / `help` / `/help` | ❌ 純文字回覆 |
| Planning / Dry-run | `整理檔名` / `產生改名計畫` / `分析 PDF 並產生改名計畫` | ❌ 只產生計畫 |
| Planning / Dry-run | `分析 PDF` / `分析 PDF 詳細` | ❌ 只讀取分析 |
| Planning / Dry-run | `整理資料夾` / `產生搬移計畫` / `分析 PDF 並產生搬移計畫` / `產生資料夾歸檔計畫` | ❌ 只產生計畫 |
| Approval | `確認 {approval_id}` | ❌ 只核准 + dry-run 報告 |
| Approval | `取消 {approval_id}` | ❌ 取消 approval |
| Rename execution | `確認改名 {approval_id}` | ✅ 真實改名（full match） |
| Rename rollback | `預覽回滾改名 {transaction_id}` | ❌ 只預覽，不改檔案、不改 log |
| Rename rollback | `回滾改名 {transaction_id}` | ✅ 真實回滾改名（full match、once-only） |
| Move execution | `確認搬移 {approval_id}` | ✅ 真實搬移（full match） |
| Move rollback | `預覽回滾搬移 {transaction_id}` | ❌ 只預覽，不搬檔案、不改 log |
| Move rollback | `回滾搬移 {transaction_id}` | ✅ 真實回滾搬移（full match、once-only） |

所有 ✅ 指令 regex 均 `^…$` 全錨定；模糊文字一律不觸發 destructive action（16A 稽核測試鎖定）。

---

## Implemented Modules

| Module | Path | Description |
|--------|------|-------------|
| AI Router | `app/router/ai_router.py` | Routes LINE messages to workers |
| Workflow Engine | `app/workflows/engine.py` | Manages multi-step workflows |
| Approval Engine | `app/approvals/manager.py` | Approval request lifecycle；含 `mark_executed()` 執行狀態標記（14E） |
| Dry-run Executor | `app/workflows/executor.py` | Executes workflows in dry-run mode |
| PDF Intelligence | `app/workers/pdf_worker.py` | Reads and classifies PDF files |
| Document Intelligence | `app/document/` | Classifies and extracts document fields |
| Taipower Bill Extraction | `app/document/extractor.py` | Extracts electricity bill fields |
| Filename Intelligence | `app/filename/` | Proposes normalized rename targets |
| RenamePlan | `app/filename/planner.py` | Builds RenamePlan from PDF summaries |
| RenamePlan Validator | `app/filename/validator.py` | Assigns risk levels to candidates |
| Preflight Validator | `app/filename/preflight.py` | Pre-execution safety checks (Phase 14A) |
| Execution Schemas | `app/filename/schemas.py` | RenameFileResult, RenameExecutionResult, RenameTransaction |
| Safe Rename Executor | `app/filename/executor.py` | 真實更名執行、交易建立、rollback、rollback_by_id（14B/14C） |
| Transaction Log | `app/filename/transaction_log.py` | JSON 持久化 RenameTransaction，支援 save/load/list/update/mark；含 read-only `preview_rollback_transaction()`（14D-3A）與 `prune_transactions()` 維運清理 API（14F） |
| Approval Bridge | `app/filename/approval_bridge.py` | 受控 application-layer bridge：approved + validated plan → execute_rename_plan()（14D-1） |
| Mock LINE CLI | `scripts/mock_line.py` | Local CLI simulator for AI Router；含明確「確認改名 {approval_id}」（14D-2）、「預覽回滾改名 {transaction_id}」（14D-3A）、「回滾改名 {transaction_id}」（14D-3B）、「確認搬移 {approval_id}」（15G，唯一真實搬移入口，走 move approval bridge）、「預覽回滾搬移 {transaction_id}」（15H，read-only）、「回滾搬移 {transaction_id}」（15I，唯一真實 move rollback 入口，走 `rollback_move_transaction_by_id()`）指令；16C 起含「說明 / 指令說明 / help / /help」純文字 help 指令、`humanize_reason()` 錯誤 reason 中文說明、execution / rollback / 核准回覆下一步提示 |
| Folder Intelligence | `app/folder_intelligence/` | MovePlan 產生（planner/template/validator/formatter）；planning 不碰 filesystem（15A）；已接 router/worker/approval/dry-run（15B）；read-only preflight 與 execution schemas（15C） |
| Safe Move Executor | `app/folder_intelligence/executor.py` | `execute_move_plan(plan, transaction_log=None)` — 唯一可真實搬移檔案的入口；preflight gate → 執行期檢查 → mkdir + move → rollback_from/rollback_to（15D）；可選持久化 transaction、`build_move_transaction()`、`rollback_move_transaction()`、`rollback_move_transaction_by_id()`（15E）；未接 Mock LINE |
| Move Transaction Log | `app/folder_intelligence/transaction_log.py` | JSON 持久化 MoveTransaction，支援 save/load/list/update/mark（15E）；建議路徑 `runtime/move_transactions.json`（已列入 .gitignore）；含 read-only `preview_move_rollback_transaction()` / `preview_move_rollback_transaction_by_id()`（15H，接 Mock LINE「預覽回滾搬移」）與 `prune_transactions()` / `prune_move_transactions()` 維運清理 API（15J，未接 Mock LINE） |
| Move Approval Bridge | `app/folder_intelligence/approval_bridge.py` | 受控 application-layer bridge（15F）：`execute_approved_move_plan()`（payload → MovePlan 還原 + status 同步 → `execute_move_plan()`）、`execute_approved_move_by_approval_id()`（approval gates + once-only guard + `mark_executed()` 回寫）、`default_move_transaction_log()`；15G 起由 Mock LINE「確認搬移 {approval_id}」明確指令呼叫 |

---

## Architecture Summary

```
LINE Message
    │
    ▼
AIRouter  ──────────────────────────────────────────────────────────────────┐
    │                                                                        │
    ▼                                                                        │
WorkerRequest                                                               │
    │                                                                        │
    ├── PDFWorker.analyze_pdfs()                                            │
    │       └── DocumentIntelligence (classify + extract)                   │
    │               └── TaipowerBillExtractor                               │
    │                                                                        │
    ├── PDFWorker.generate_rename_plan()                                     │
    │       ├── PDFWorker.analyze_pdfs()                                    │
    │       ├── build_rename_plan()  →  RenamePlan                          │
    │       ├── validate_rename_plan()  →  ValidationReport                 │
    │       └── ApprovalManager.create_approval()                           │
    │                                                                        │
    └── WorkflowExecutor.execute_dry_run()  (on approval)                  │
            └── Returns dry-run report (no filesystem mutation)            ◄┘
```

---

## Safety Rules

1. **RenamePlan is dry-run by default** — `dry_run=True` on every plan.
2. **RenamePlan requires approval** — `requires_approval=True` on every plan.
3. **Unknown document type is blocked** — validator assigns `risk_level="blocked"`.
4. **High-risk candidates are not auto-executed** — skipped in preflight and executor.
5. **Actual file rename only through `execute_rename_plan()`** — Mock LINE generic commands never trigger real rename.
6. **Rename requires approved plan + valid validation_report + preflight pass.**
7. **Rollback by transaction ID** — `rollback_transaction_by_id()` loads from JSON log and reverses success actions.
8. **「確認 {approval_id}」仍走 dry-run** — 核准 approval 並產生 dry-run 報告，不觸發真實更名。
9. **Approval Bridge 三重 gate** — `execute_approved_rename_plan()` 要求 `status=="approved"`、`validation_report` 存在、`blocked_count==0`，否則回傳 `executed=False` 且不呼叫 executor。
10. **Bridge 不直接碰檔案系統** — 一律委派 `execute_rename_plan()`，不呼叫 `Path.rename` / `os.rename` / `shutil.move`（測試以 AST 驗證）。
11. **真實更名唯一入口：「確認改名 {approval_id}」** — 必須完全符合格式（regex 全比對）；「確認」「確認改名」「好」「OK」「執行」或附加多餘文字均不觸發。
12. **確認改名要求 approval 已核准** — pending/rejected/expired approval 一律拒絕並提示先輸入「確認 {approval_id}」。
13. **非 rename plan 的 approval 不支援確認改名** — payload 缺少 plan_id/candidates 即拒絕。
14. **真實更名一律寫入 RenameTransactionLog** — 預設路徑 `runtime/rename_transactions.json`（已加入 .gitignore，目錄不存在時自動建立）。
15. **Mock LINE 不直接呼叫 Path.rename** — 測試以 AST 驗證；執行僅透過 approval bridge → safe executor。
16. **「預覽回滾改名 {transaction_id}」純讀取** — 只查詢 transaction log 並回覆摘要，不 rollback、不更名檔案、不寫 log（測試驗證 log 檔 byte-level 不變）。
17. **真實 rollback 唯一入口：「回滾改名 {transaction_id}」** — 完全比對才生效；「回滾」「回滾改名」「確認」「好」「OK」「執行」或附加多餘文字均不觸發。
18. **Rollbackable 判斷** — 只有 action status == "success" 可回滾；rolled_back / failed / pending 不會被動到。
19. **Rollback 一律透過 `rollback_transaction_by_id()`** — Mock LINE 不直接呼叫 `Path.rename` / `os.rename` / `shutil.move`（AST 驗證）；成功回滾的 action 在 log 中更新為 `rolled_back`，失敗的維持 `success`。
20. **Rollback 安全檢查** — 來源不存在 → `rollback_source_not_found`；目標已被佔用 → `rollback_target_already_exists`，不覆寫任何檔案。
21. **Approval once-only guard（14E）** — 同一 approval_id 成功執行（至少一筆 rename 成功）後，payload 記錄 `execution_status` / `executed_at` / `execution_transaction_id`；重複「確認改名」直接回覆「已執行過」+ transaction_id + 復原提示，不呼叫 bridge、不動檔案、不新增 transaction。全數失敗（檔案未動）時不標記，允許重試。舊 approval 無 `execution_status` 視為尚未執行（backward compatible）。
22. **Rollback once-only guard（14E）** — 「回滾改名」先以 read-only preview 判斷；無可回滾 action 時完全不進入執行路徑（不動檔案、不寫 log）。全部已回滾 → 回覆「此交易已回滾完成」；部分 rolled_back 仍可回滾剩餘 success action。
23. **預覽提示可回滾狀態（14E）** — 「預覽回滾改名」在無可回滾項目時明確提示，全部回滾完成時顯示「此交易已全部回滾」。
24. **Log prune 永不刪除可回滾交易（14F）** — `prune_transactions()` 對含 success action 的交易一律保留（即使符合刪除條件）；無法解析的 entry 永不刪除；只動 log 檔、不動實體檔案；無變更時不重寫檔案。
25. **Log prune 僅為維運 API（14F）** — 未接任何 Mock LINE 指令，rename / rollback 指令行為完全不變。
26. **MovePlan 僅為計畫（15A）** — `dry_run=True`、`requires_approval=True` by default；沒有 move executor、沒有任何 Mock LINE 搬移指令；planner / validator / formatter 不碰真實 filesystem（AST 驗證不得出現 rename/move/replace/mkdir 呼叫）。
27. **Folder segment 防護（15A）** — `sanitize_folder_segment()` 排除 `/`、`\`、`:` 等非法字元與相對路徑點號；business_id / billing_period 缺失時使用 `unknown-business` / `unknown-period` fallback（validator 標為 high）；unknown 文件對應 `未分類/unknown-document/`（validator 標為 blocked）。
28. **Move planning 指令僅產生計畫（15B）** — 「整理資料夾」「產生搬移計畫」等指令只產生 MovePlan + approval + dry-run summary；「確認 {approval_id}」核准後也只顯示 move dry-run 報告，不搬移檔案。
29. **MovePlan payload 標記 `plan_type="move_plan"`（15B）** — dry-run executor 據此分流；「確認改名」對 move plan approval 一律拒絕（不可被當成 RenamePlan 執行）。
30. **沒有「確認搬移」指令（15B；已被 15G 取代）** — 15B–15F 期間 Mock LINE 無任何真實搬移入口；15G 起新增唯一明確入口「確認搬移 {approval_id}」（見規則 43–45）。
31. **Move preflight 純資料驗證（15C）** — `preflight_move_plan()` 永遠回傳 `executed=False`、`dry_run=True`、`success_count=0`、`rollback_available=False`；不搬移、不建資料夾、不檢查真實 filesystem（AST 驗證不得 import os/shutil/pathlib、不得呼叫 rename/move/replace/mkdir/makedirs）。
32. **Move preflight 三重 plan gate（15C）** — `plan_not_approved` / `missing_validation_report` / `validation_has_blocked_candidates`；candidate-level 依序檢查 missing paths（failed）、blocked（blocked）、same_path（skipped）、high risk（skipped）、low/medium（skipped，`preflight_passed_no_execution_in_phase_15c`）。
33. **真實 move 唯一入口：`execute_move_plan()`（15D）** — 僅限 `app/folder_intelligence/executor.py`（AST 驗證 app/ 與 scripts/ 其他模組無 rename/move 呼叫、無 shutil import）；只接受 approved + validation_report + `blocked_count == 0` 的 MovePlan；blocked 永不搬移、high risk 預設跳過、low/medium 才執行；執行期檢查來源存在與目標 collision（`original_file_not_found` / `target_file_already_exists`），成功前先 `mkdir(parents=True)` 建立目標資料夾。
34. **Move 成功結果含 rollback 資訊（15D）** — 每筆成功搬移回傳 `rollback_from`（新位置）/ `rollback_to`（原位置），`rollback_available=True`；但 Move rollback 執行與 Move Transaction Log 留待 15E。
35. **Mock LINE 不直接接 move executor（15D；15G 更新）** — Mock LINE 原始碼不含 `execute_move_plan`（測試驗證）；15G 起「確認搬移」一律透過 approval bridge，executor 仍只能由 bridge 呼叫。
36. **Move transaction log 為可選且不影響執行行為（15E）** — `execute_move_plan(plan, transaction_log=None)` 未提供 log 時行為與 15D 完全相同；提供 log 時先 save pending transaction（只含 low/medium 可執行 action），執行後標記 success/failed；plan gate 失敗時不建立 log。
37. **Move rollback 只回滾 success action（15E）** — `rollback_move_transaction()` 不碰 pending/failed/rolled_back action；來源不存在 → `rollback_source_not_found`、原位置被佔用 → `rollback_target_already_exists`（不覆蓋）；需要時自動重建原資料夾。
38. **Move rollback by id 與 log 同步（15E）** — `rollback_move_transaction_by_id()` 成功回滾的 action 標記 `rolled_back`；回滾失敗的 action 保持 `success`（檔案仍在新位置），log 不會被破壞；找不到 id 回傳 `transaction_not_found`。
39. **Mock LINE 無任何 move rollback 入口（15E）** — 沒有 move rollback 指令；Mock LINE 原始碼不含 `rollback_move_transaction` / `MoveTransactionLog`（測試驗證）；既有「回滾改名」只作用於 rename transaction log。
40. **Move Approval Bridge 不直接碰檔案系統（15F）** — `execute_approved_move_plan()` 一律委派 `execute_move_plan()`，不呼叫 rename/move/replace/mkdir（AST 驗證）；payload 必須標記 `plan_type == "move_plan"`（或 `type`），否則 `not_move_plan`；無法還原 MovePlan → `invalid_move_plan_payload`。
41. **Move approval once-only guard（15F）** — `execute_approved_move_by_approval_id()` gates 依序為 `approval_not_found` → `not_move_plan` → `approval_not_approved` → `already_executed`；至少一筆搬移成功才透過既有 `mark_executed()`（14E 機制）回寫 `execution_status` / `executed_at` / `execution_transaction_id`；全數失敗（檔案未動）不標記，允許重試；同一 approval_id 不會重複搬移。
42. **Move bridge 未接 Mock LINE（15F；已被 15G 取代）** — 15F 時 bridge 只能在測試或程式中明確呼叫；15G 起由「確認搬移 {approval_id}」明確指令呼叫 `execute_approved_move_by_approval_id()`（`execute_approved_move_plan` 仍不直接接 Mock LINE）。
43. **真實搬移唯一入口：「確認搬移 {approval_id}」（15G）** — regex `^確認搬移\s+([A-Za-z0-9_-]+)$` full match 才觸發；「確認」「搬移」「確認搬移」「確認搬移一下 …」「請幫我確認搬移 …」「整理資料夾」「產生搬移計畫」「確認改名」均不觸發；「確認 {approval_id}」核准 move plan 後仍只顯示 dry-run 報告。
44. **「確認搬移」一律走 move approval bridge（15G）** — 透過 `execute_approved_move_by_approval_id()`（approval gates + once-only guard + `mark_executed()` 回寫）；預設 transaction log 為 `default_move_transaction_log()`（`runtime/move_transactions.json`）；Mock LINE 不直接呼叫 executor / rollback API（import 與 AST 測試驗證）；回覆含執行摘要、transaction_id、rollback_from/rollback_to 與明確拒絕原因。
45. **Move rollback 指令演進（15G→15I）** — 15G 時「回滾搬移」「預覽回滾搬移」均不存在；15H 新增 read-only「預覽回滾搬移」（規則 46–47）；15I 起新增真實「回滾搬移 {transaction_id}」執行指令（規則 49–51）。
46. **「預覽回滾搬移 {transaction_id}」純讀取（15H）** — regex `^預覽回滾搬移\s+([A-Za-z0-9_-]+)$` full match 才觸發；只透過 `preview_move_rollback_transaction_by_id()` 查詢 move transaction log 並回覆摘要，不 rollback、不搬移檔案、不建資料夾、不寫 log（byte-level 測試 + AST 驗證）；transaction 不存在 → `transaction_not_found`。
47. **Preview rollbackable 語意（15H）** — success + rollback_from/rollback_to 存在 → rollbackable；rolled_back → `already_rolled_back`；failed → `action_failed`；success 缺路徑 → `missing_rollback_paths`；pending → `action_pending`；回覆一律附「這只是預覽，尚未實際回滾任何檔案。」。
48. **真實 move rollback 只在底層 API（15H；已被 15I 取代）** — 15H 時「回滾搬移」不是指令；15I 起為合法指令但僅透過 `rollback_move_transaction_by_id()` 執行（見規則 49）。
49. **真實 move rollback 唯一入口：「回滾搬移 {transaction_id}」（15I）** — regex `^回滾搬移\s+([A-Za-z0-9_-]+)$` full match 才觸發（測試驗證 regex 必須 ^…$ 錨定）；「回滾搬移」「回滾搬移一下 …」「請幫我回滾搬移 …」「預覽回滾搬移 …」「回滾改名 …」「確認搬移 …」均不觸發；一律透過 `rollback_move_transaction_by_id()` 執行並同步 log，Mock LINE 不直接呼叫 rename/replace/move、不 import os/shutil、不可用非 by_id 低階 rollback API（AST + import 掃描驗證）。
50. **Move rollback once-only guard（15I）** — 執行前先以 read-only preview 判斷：找不到 → `transaction_not_found`、全部已回滾 → `already_fully_rolled_back`（不重複回滾、不動檔案、不寫 log、不誤報 source missing）、無可回滾 → `no_rollbackable_actions`；三者皆不進入執行路徑。部分 rolled_back 的交易仍可回滾剩餘 success action。
51. **Move rollback fail-safe 與 log 分離（15I）** — 來源缺失 → `rollback_source_not_found`、原位置被佔用 → `rollback_target_already_exists`（不覆寫任何檔案）；失敗的 action 保持 `success`、不標記 `rolled_back`、log 不被破壞；「回滾搬移」只作用 move transaction log、「回滾改名」「預覽回滾改名」只作用 rename transaction log（互不影響，測試驗證）。
52. **Move log prune 永不刪除可回滾交易（15J）** — `prune_transactions()` 對含 success action 的交易一律保留（protected，即使過期）；無法解析的 entry / 整檔 invalid JSON 永不刪除且不覆寫；只動 log JSON、不檢查 filesystem、不搬移、不回滾、不建資料夾、不改 action status；dry_run 與無可刪項目時不重寫檔案；保留的 entry 以 raw 形式原樣保留（未知欄位不丟失）。
53. **Move log prune 僅為維運 API（15J）** — 未接任何 Mock LINE 指令（測試驗證原始碼不含 prune）；「確認搬移」「預覽回滾搬移」「回滾搬移」行為完全不變。
54. **Runtime 路徑單一來源 + SAFE_PDF_ROOT 錨定（16B）** — runtime 路徑（approval store、rename / move transaction log）只定義在 `app/core/config.py`（測試掃描 app/ 與 scripts/ 不得 hardcode）；executor 層相對路徑一律經 `resolve_under_safe_root()` 錨定 SAFE_PDF_ROOT（純字串正規化、不碰 filesystem）；相對路徑逃出 root → executor 以 failed reason `path_escapes_safe_root` fail-safe 拒絕，不操作任何檔案；絕對路徑語意不變。
55. **Help 指令純文字（16C）** — 「說明」「指令說明」「help」「/help」full match 才觸發；只回覆指令說明文字，不建立 approval、不讀寫 transaction log、不碰任何檔案、不進入 router / planning / execution / rollback 任何路徑（零副作用，測試驗證）。
56. **錯誤訊息只改文字、不改 reason（16C）** — `humanize_reason()` 在輸出層為 reason code 附中文說明與建議下一步，原始 code 一律保留方便 debug；底層 result reason、bridge gates、once-only guard 行為完全不變；未知 code 安全顯示不 raise。
57. **下一步提示不改變流程（16C）** — execution 成功回覆附「預覽回滾改名/搬移」「回滾改名/搬移」提示；preview 回覆明示 read-only；核准（「確認 {approval_id}」）回覆明示不會改名/搬移並提示明確執行指令；MovePlan 產生回覆維持 15B 不變式（不直接提示「確認搬移」，改以「指令說明」導引）。
58. **Command Inventory 與 Release Candidate Notes 靜態文件（16E）** — README 新增「完整指令一覽」（Non-destructive 8 指令 / Destructive full-match only 4 指令）與「Release Candidate Notes」；`tests/test_release_readiness.py` 稽核文件內容、version、checklist、command inventory 分類；未新增任何 destructive action、未改變指令語意。

---

## Known Limitations / Not Yet Implemented

- ~~路徑解析依賴 CWD（16A 稽核發現）~~ — **已於 16B 修正**：executor 層以 `resolve_under_safe_root()` 錨定 SAFE_PDF_ROOT，E2E 不再需要 chdir。
- ~~log_path 散落各模組 hardcoded~~ — **已於 16B 修正**：runtime 路徑集中於 `app/core/config.py` settings helpers。
- **絕對路徑不受 safe root 限制（16B 設計決策）** — 計畫/transaction 中的絕對路徑原樣使用（既有語意，所有測試與呼叫端依賴此行為）；safe root 錨定與 traversal 防護僅針對相對路徑。
- **Transaction log 內的相對路徑與 SAFE_PDF_ROOT 綁定** — 若執行與回滾之間變更 SAFE_PDF_ROOT 設定，相對路徑會解析到新 root（罕見情境，單人 CLI 可接受）。
- **Transaction log 無壓縮 / SQLite** — JSON persistence；大量交易時可於後續階段評估 TTL 進階策略或 SQLite。
- Only Taipower electricity bills are fully supported for rename.
- No multi-user / tenant isolation.
- RenamePlan 透過 approval payload（JSON）持久化，無獨立 plan 儲存系統。
- Rollback 預覽不檢查實際檔案是否存在；可回滾與否僅依 log 中 action status 判斷，實際可行性由執行時的 safety check 把關（來源/目標檢查）。
- Once-only guard 以「至少一筆 rename 成功」為標記條件；部分成功（如 2 成功 1 失敗）即標記 executed，失敗的候選項無法透過同一 approval 重試。
- Approval 執行狀態存於 payload dict（非 schema 欄位），仰賴 JSON store 持久化；無跨 process 鎖，極端並發下仍可能 race（單人 CLI 情境可接受）。
- Log prune 為手動維運 API，無自動排程；何時呼叫由維運方決定。
- Prune 條件以 transaction 為單位（created_at / 筆數），不支援以 plan_id 或 action 層級篩選。
- MovePlan 僅支援 Taipower bill folder template；其他 document type 一律進「未分類」。
- MovePlan 已接 approval workflow、Mock LINE planning 指令（15B）與「確認搬移」執行指令（15G）；`execute_move_plan()` 與 `execute_approved_move_plan()` 仍為底層 API，不直接接 Mock LINE。
- Move preflight（15C）刻意不檢查真實 filesystem；執行期檢查（來源存在、目標 collision、資料夾建立）由 15D executor 負責。
- Move transaction log 為 function-level API：`execute_move_plan()` 須明確傳入 `transaction_log` 才會持久化；log_path 由呼叫方指定，尚未整合 settings 全域預設。
- Move rollback 預覽不檢查實際檔案是否存在；可回滾與否僅依 log 中 action status 與 rollback 路徑判斷，實際可行性由執行時的 safety check 把關（來源/目標檢查，15I）。
- Move rollback once-only 以 preview 的可回滾狀態判斷：部分回滾失敗的 action 保持 `success`，可重試；但若檔案已被外部移走，重試仍會以 `rollback_source_not_found` 失敗（需人工處理）。
- Move log prune（15J）為手動維運 API，無自動排程；條件以 transaction 為單位（created_at），不支援 plan_id 或 action 層級篩選、不支援 max_transactions 上限（rename 14F 有）。
- Move dry-run 顯示尚未掛 preflight summary：approval payload 內序列化的 plan status 仍為 `pending_approval`（核准狀態在 Approval Engine）；move bridge 在執行時同步 status，但 dry-run 顯示整合仍未做。
- 「產生搬移計畫」的回覆仍不直接提示「確認搬移」指令（15B 測試不變式）；16C 起改以「指令說明」導引，且核准後的 dry-run 報告會明確提示「確認搬移 {approval_id}」。
- Help text 為靜態維護文字（16C）：新增指令時需手動同步 `command_help_text()`，無自動由 regex 清單產生。
- `rip` console_scripts entry point 已提供（17A）：`poetry install` 後可用 `poetry run rip "…"`；`poetry run python scripts/mock_line.py "…"` 舊用法向下相容保留。
- `pyproject.toml` 的 package version（0.1.0）與文件版本（v0.7.3-alpha）未同步（16D 記錄）：版本演進目前以 CHANGELOG / PROJECT_STATUS 為準，packaging version 留待正式 release 階段對齊。
- README operator 文件為靜態維護（16D）：指令清單與安全原則由 `tests/test_cli_smoke.py` 以子字串稽核鎖定，新增指令時需同步更新。
- Move once-only guard 沿用 14E 語意：部分成功即標記 executed，失敗候選無法以同一 approval 重試。
- Release candidate 狀態（16E）：不適用於多人同時操作、長期高併發、真正 production daemon；適用於本機文件整理與安全流程驗證。
- Command Inventory 與 Release Candidate Notes 為靜態維護（16E）：新增指令時需同步更新 README 對應區塊，`tests/test_release_readiness.py` 會稽核關鍵子字串。
- RELEASE_NOTES.md 為靜態維護（16F）：新增指令或版本更新時需同步；`tests/test_final_regression_release_candidate.py` 稽核內容存在與關鍵子字串。
- Tag Readiness Checklist（16F–16G）：Git tag 與 push 尚未執行，留待人工確認後執行（詳見 RELEASE_NOTES Tagging Instructions）。
- Package artifact（16G）：`dist/` 已 gitignored；artifact 版本為 0.1.0（pyproject packaging version），非 RIP release version；`poetry check` 有 deprecation warnings 但不影響 build。

---

## Recommended Next Phase

**Phase 17B** — 視需求決定（pyproject.toml 現代化 / 功能擴充 / 正式 release）

可選方向：
- `pyproject.toml` 現代化：從 `[tool.poetry]` 遷移至 `[project]` 標準格式（解決 `poetry check` deprecation warnings）。
- pyproject version 對齊：0.1.0 → 0.7.4a0（PEP 440）。
- 人工建立 git tag：`git tag -a v0.7.4-alpha -m "RIP v0.7.4-alpha"` && `git push origin v0.7.4-alpha`。
- 功能擴充：multi-user 支援、SQLite persistence、production deployment guide。
