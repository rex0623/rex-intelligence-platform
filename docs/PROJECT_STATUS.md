# Rex Intelligence Platform (RIP) — Project Status

## Overview

| Field | Value |
|-------|-------|
| **Project** | Rex Intelligence Platform (RIP) |
| **Current Version** | v0.6.2-alpha |
| **Test Count** | 347 passing |
| **Last Updated** | 2026-06-11 |

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
| Mock LINE CLI | `scripts/mock_line.py` | Local CLI simulator for AI Router；含明確「確認改名 {approval_id}」（14D-2）、「預覽回滾改名 {transaction_id}」（14D-3A）、「回滾改名 {transaction_id}」（14D-3B）指令 |
| Folder Intelligence | `app/folder_intelligence/` | MovePlan 產生（planner/template/validator/formatter）；planning only，無 executor（15A）；已接 router/worker/approval/dry-run（15B）；read-only preflight 與 execution schemas（15C） |

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
30. **沒有「確認搬移」指令（15B）** — Mock LINE 無任何真實搬移入口；無 move executor。
31. **Move preflight 純資料驗證（15C）** — `preflight_move_plan()` 永遠回傳 `executed=False`、`dry_run=True`、`success_count=0`、`rollback_available=False`；不搬移、不建資料夾、不檢查真實 filesystem（AST 驗證不得 import os/shutil/pathlib、不得呼叫 rename/move/replace/mkdir/makedirs）。
32. **Move preflight 三重 plan gate（15C）** — `plan_not_approved` / `missing_validation_report` / `validation_has_blocked_candidates`；candidate-level 依序檢查 missing paths（failed）、blocked（blocked）、same_path（skipped）、high risk（skipped）、low/medium（skipped，`preflight_passed_no_execution_in_phase_15c`）。

---

## Known Limitations / Not Yet Implemented

- **Transaction log 無 rotation/壓縮** — 大量交易時 JSON 檔案會成長，Phase 14D+ 可加入 TTL 或 SQLite。
- **log_path 由呼叫方指定** — 尚未整合到 settings.py 作為全域預設路徑。
- Only Taipower electricity bills are fully supported for rename.
- No multi-user / tenant isolation.
- RenamePlan 透過 approval payload（JSON）持久化，無獨立 plan 儲存系統。
- Rollback 預覽不檢查實際檔案是否存在；可回滾與否僅依 log 中 action status 判斷，實際可行性由執行時的 safety check 把關（來源/目標檢查）。
- Once-only guard 以「至少一筆 rename 成功」為標記條件；部分成功（如 2 成功 1 失敗）即標記 executed，失敗的候選項無法透過同一 approval 重試。
- Approval 執行狀態存於 payload dict（非 schema 欄位），仰賴 JSON store 持久化；無跨 process 鎖，極端並發下仍可能 race（單人 CLI 情境可接受）。
- Log prune 為手動維運 API，無自動排程；何時呼叫由維運方決定。
- Prune 條件以 transaction 為單位（created_at / 筆數），不支援以 plan_id 或 action 層級篩選。
- MovePlan 僅支援 Taipower bill folder template；其他 document type 一律進「未分類」。
- MovePlan 已接 approval workflow 與 Mock LINE planning 指令（15B），但無任何 executor。
- Move preflight（15C）刻意不檢查真實 filesystem（來源存在、目標 collision、資料夾存在與否留待 15D safe executor 的執行期檢查，模式同 rename 的 14A→14B）。
- Move dry-run 顯示尚未掛 preflight summary：approval payload 的 plan status 不會隨核准同步（核准狀態在 Approval Engine），需待 15D execution bridge 處理狀態同步後再整合。
- MovePlan approval 沒有 once-only guard（因為沒有執行路徑，核准只產生 dry-run 報告）。

---

## Recommended Next Phase

**Phase 15D — Safe Move Executor Design**

- 仿照 Phase 14B 設計 safe move executor：preflight gate → 執行期檢查（來源存在、目標 collision、資料夾建立）→ 真實搬移 → rollback 資訊。
- 仿照 14D-1 設計 approval-to-execution bridge（含 plan status 同步），執行入口仍須明確指令。
