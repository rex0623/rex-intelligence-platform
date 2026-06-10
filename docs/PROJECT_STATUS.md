# Rex Intelligence Platform (RIP) — Project Status

## Overview

| Field | Value |
|-------|-------|
| **Project** | Rex Intelligence Platform (RIP) |
| **Current Version** | v0.4.0-alpha |
| **Test Count** | 179 passing |
| **Last Updated** | 2026-06-10 |

---

## Completed Phases

| Phase | Title | Status |
|-------|-------|--------|
| 1–12 | Core Platform Foundation | ✅ Complete |
| 13 | Filename Intelligence / Rename Plan | ✅ Complete |
| 13.5 | Rename Plan Quality Gate | ✅ Complete |
| 14A | Safe Rename Executor Schemas & Preflight | ✅ Complete |
| 14B | Safe Rename Executor | ✅ Complete |

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
| Safe Rename Executor | `app/filename/executor.py` | 真實更名執行、交易建立、rollback（Phase 14B） |
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
7. **Rollback helper exists** — `rollback_rename_transaction()` reverses success actions; transaction not persisted yet.

---

## Known Limitations / Not Yet Implemented

- **RenameTransaction 無持久化** — 交易資料僅存於記憶體，重啟即消失（Phase 14C 範疇）。
- **無 rollback audit trail** — rollback 操作不寫入日誌（Phase 14C 範疇）。
- Only Taipower electricity bills are fully supported for rename.
- No multi-user / tenant isolation.
- No persistent storage (plans live in memory only).
- Mock LINE 確認改名計畫流程仍走 dry-run，不觸發 `execute_rename_plan()`。

---

## Recommended Next Phase

**Phase 14C — Persistent Transaction Log & Rollback Audit Trail**

- 將 `RenameTransaction` 持久化至 JSON 或 SQLite。
- 紀錄每次 execute / rollback 的操作歷史。
- 提供 audit trail 查詢介面。
- 支援重啟後仍可查詢並 rollback 歷史交易。
