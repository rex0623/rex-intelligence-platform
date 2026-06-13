# Rex Intelligence Platform（RIP）Release Notes

---

## v0.7.4-alpha

**Phase 16E–16F — Release Candidate Stabilization / Final Regression**

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

- **Local CLI / Mock LINE only** — operator 入口為 `poetry run python scripts/mock_line.py "…"`；尚無正式 console_scripts entry point。
- **JSON persistence only** — transaction log 為 JSON 檔，無資料庫；大量交易時可後續評估 SQLite。
- **No formal console_scripts entry point yet** — 正式 entry point 留待 release artifact 打包（16G+）。
- **Not designed for multi-user concurrent production operation** — 無 tenant 隔離、無跨 process 鎖；適用於個人本機文件整理。
- **pyproject version is packaging metadata, not RIP release source of truth** — `pyproject.toml` version（0.1.0）為 packaging metadata；release 版本以 PROJECT_STATUS / CHANGELOG 為準（目前 v0.7.4-alpha）。
- **Help text / command inventory 為靜態維護** — 新增指令時需手動同步 `command_help_text()` 與 README command inventory。
- **Absolute paths not anchored to SAFE_PDF_ROOT** — 相對路徑有 traversal 防護；絕對路徑依既有語意原樣使用（所有現有測試依賴此行為）。

---

### Tagging Recommendation

**本 phase 不自動建立 git tag。**

| 項目 | 狀態 |
|------|------|
| Suggested tag candidate | `v0.7.4-alpha` |
| Alternative future RC tag | `v0.8.0-rc1` |
| Tag creation | ⬜ 留待 Phase 16G（人工執行） |
| Tag push | ⬜ 留待 Phase 16G（人工執行） |

建議在以下條件全數滿足後再建立 tag：
1. `git status --short` 輸出為空（working tree clean）
2. `poetry run pytest -q` 全數通過（648+ tests）
3. README / PROJECT_STATUS / CHANGELOG 版本一致
4. runtime/ 無被 git 追蹤的檔案

---

### Test Count

| Phase | Tests |
|-------|-------|
| 16D 前（Phase 1–16C） | 606 |
| 16D（Packaging smoke） | +22 → 628 |
| 16E（Release readiness） | +20 → 648 |
| 16F（Final regression） | +26 → 674 |
