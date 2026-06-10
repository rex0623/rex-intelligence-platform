# Changelog — Rex Intelligence Platform (RIP)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

### Phase 14C — Persistent Transaction Log & Rollback Audit Trail

- 將 `RenameTransaction` 持久化至 JSON 或 SQLite。
- 每次 execute / rollback 均寫入 audit log。
- 支援重啟後查詢歷史交易並 rollback。
