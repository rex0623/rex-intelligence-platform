# Rex Intelligence Platform (RIP) — Project Status

## Overview

| Field | Value |
|-------|-------|
| **Project** | Rex Intelligence Platform (RIP) |
| **Current Version** | v0.5.1-alpha |
| **Test Count** | 214 passing |
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

---

## Implemented Modules

| Module | Path | Description |
|--------|------|-------------|
| AI Router | `app/router/ai_router.py` | Routes LINE messages to workers |
| Workflow Engine | `app/workflows/engine.py` | Manages multi-step workflows |
| Approval Engine | `app/approvals/manager.py` | Approval request lifecycle |
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
| Transaction Log | `app/filename/transaction_log.py` | JSON 持久化 RenameTransaction，支援 save/load/list/update/mark |
| Approval Bridge | `app/filename/approval_bridge.py` | 受控 application-layer bridge：approved + validated plan → execute_rename_plan()（14D-1） |
| Mock LINE CLI | `scripts/mock_line.py` | Local CLI simulator for AI Router |

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
8. **Mock LINE 確認流程仍走 dry-run** — 不觸發 `execute_rename_plan()` 或 `rollback_transaction_by_id()`。
9. **Approval Bridge 三重 gate** — `execute_approved_rename_plan()` 要求 `status=="approved"`、`validation_report` 存在、`blocked_count==0`，否則回傳 `executed=False` 且不呼叫 executor。
10. **Bridge 不直接碰檔案系統** — 一律委派 `execute_rename_plan()`，不呼叫 `Path.rename` / `os.rename` / `shutil.move`（測試以 AST 驗證）。
11. **Bridge 未接 Mock LINE** — 明確確認指令是 Phase 14D-2 範疇。

---

## Known Limitations / Not Yet Implemented

- **Transaction log 無 rotation/壓縮** — 大量交易時 JSON 檔案會成長，Phase 14D+ 可加入 TTL 或 SQLite。
- **log_path 由呼叫方指定** — 尚未整合到 settings.py 作為全域預設路徑。
- Only Taipower electricity bills are fully supported for rename.
- No multi-user / tenant isolation.
- No persistent storage (plans live in memory only) — `execute_approved_rename_by_plan_id()` 的 `plan_loader` 由呼叫方注入。
- Mock LINE 確認改名計畫流程仍走 dry-run，不觸發 `execute_rename_plan()`。
- Approval Bridge 尚未接到任何使用者指令入口（Mock LINE 無法觸發真實更名）。
- Rollback 指令尚未對使用者開放（僅有 `rollback_transaction_by_id()` API）。

---

## Recommended Next Phase

**Phase 14D-2 — Explicit Mock LINE Confirm Rename Command**

- 新增明確的 Mock LINE 確認指令（非通用關鍵字），透過 `execute_approved_rename_plan()` 觸發真實更名。
- 確認指令必須帶 approval/plan 識別碼，不可由「產生改名計畫」等通用指令觸發。
- 執行結果（success / failed / skipped counts）回顯到 Mock LINE 輸出。
- 交易寫入 `RenameTransactionLog`，為後續 rollback 指令鋪路（rollback 指令本身屬更後續 phase）。
