# Rex Intelligence Platform（RIP）Release Notes

---

## v0.7.4-alpha

**Phase 16E–17C — Release Candidate Stabilization / Final Regression / Tag Readiness / console_scripts Entry Point / Runtime Lock / Operator Runbook**

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

**`poetry check` 結果**：通過（有 deprecation warnings，非 errors）

> Poetry 2.x 建議從 `[tool.poetry]` 遷移至 `[project]` 標準欄位；目前使用 `[tool.poetry]` 為舊格式 warnings，不影響 build 功能。

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
