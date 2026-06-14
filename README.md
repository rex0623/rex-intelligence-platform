# RIP - Rex Intelligence Platform

本專案是一個以 PDF intelligence、Approval workflow、Rename/Move safe execution 為核心的本機文件智慧整理平台。

> **目前版本：v0.7.7-alpha**（Phase 19G — Tag Confirmed；詳見 [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) ｜ [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) ｜ [CHANGELOG.md](CHANGELOG.md)）

[![CI](https://github.com/rex0623/rex-intelligence-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/rex0623/rex-intelligence-platform/actions/workflows/ci.yml)

---

## 🧭 Operator 快速上手

### 主要能力

- **PDF / Document Intelligence** — 讀取、分類 PDF 並抽取欄位（台電電費單完整支援）
- **Filename Intelligence / RenamePlan** — 產生標準化改名計畫（dry-run）
- **Folder Intelligence / MovePlan** — 產生資料夾歸檔搬移計畫（dry-run）
- **Approval workflow** — 計畫一律先核准，核准本身不動檔案
- **Safe rename / safe move** — 真實執行只走 approval bridge + safe executor
- **Transaction log** — 每次真實執行寫入交易紀錄（JSON）
- **Rollback preview / rollback execution** — 先 read-only 預覽，再明確指令回滾
- **Runtime settings** — runtime 路徑單一來源（`app/core/config.py`），相對路徑錨定 SAFE_PDF_ROOT
- **Mock LINE operator interface** — 本機 CLI 模擬 LINE 操作入口

### 安裝與測試

```bash
poetry install
poetry run pytest -q
```

### Mock LINE 使用方式

```bash
# 操作入口：先看指令說明（也可用「指令說明」「help」「/help」）
poetry run rip "說明"

# Planning / Dry-run（只產生計畫，不會動任何檔案）
poetry run rip "整理檔名"
poetry run rip "分析 PDF 詳細"
poetry run rip "整理資料夾"
poetry run rip "產生搬移計畫"
```

> `rip` 為 console_scripts entry point（Phase 17A），需先執行 `poetry install`。
> 舊用法仍然有效（向下相容）：
>
> ```bash
> poetry run python scripts/mock_line.py "說明"
> poetry run python scripts/mock_line.py "整理檔名"
> poetry run python scripts/mock_line.py "分析 PDF 詳細"
> poetry run python scripts/mock_line.py "整理資料夾"
> poetry run python scripts/mock_line.py "產生搬移計畫"
> ```

### 安全操作指令

| 指令 | 效果 |
|------|------|
| `確認 {approval_id}` | 只核准 / dry-run 報告，不會動檔案 |
| `確認改名 {approval_id}` | **真的改名** |
| `預覽回滾改名 {transaction_id}` | 只預覽，不改檔案、不改 log |
| `回滾改名 {transaction_id}` | **真的回滾改名** |
| `確認搬移 {approval_id}` | **真的搬移** |
| `預覽回滾搬移 {transaction_id}` | 只預覽，不搬檔案、不改 log |
| `回滾搬移 {transaction_id}` | **真的回滾搬移** |

### 完整指令一覽（Command Inventory）

**Non-destructive（不會改動任何檔案）**

| 指令 | 說明 |
|------|------|
| `說明` / `指令說明` / `help` / `/help` | 顯示指令說明 |
| `整理檔名` | 產生改名計畫（dry-run） |
| `分析 PDF 詳細` | 分析 PDF 詳細報告 |
| `整理資料夾` / `產生搬移計畫` / `分析 PDF 並產生搬移計畫` / `產生資料夾歸檔計畫` | 產生搬移計畫（dry-run） |
| `確認 {approval_id}` | 核准計畫 + dry-run 報告，不動檔案 |
| `取消 {approval_id}` | 取消核准請求 |
| `預覽回滾改名 {transaction_id}` | 只預覽，不改檔案、不改 log |
| `預覽回滾搬移 {transaction_id}` | 只預覽，不搬檔案、不改 log |

**Destructive — full match 才生效（會真的改動檔案）**

| 指令 | 效果 |
|------|------|
| `確認改名 {approval_id}` | **真的改名** |
| `回滾改名 {transaction_id}` | **真的回滾改名** |
| `確認搬移 {approval_id}` | **真的搬移** |
| `回滾搬移 {transaction_id}` | **真的回滾搬移** |

### 安全原則

- **Planning 指令不會改檔案** — 「整理檔名」「整理資料夾」等只產生計畫。
- **Preview 指令不會改檔案、不改 log** — 「預覽回滾改名」「預覽回滾搬移」純讀取（read-only）。
- **Destructive 指令必須 full match** — 六個執行 / 回滾指令 regex 全數 `^…$` 錨定，格式不符不會執行。
- **模糊文字不會觸發 destructive action** — 「請幫我確認改名」「回滾一下」等一律不執行。
- **Concurrent access guard（Phase 17B）** — `fcntl.flock` advisory lock 防止多個 process 同時寫入 runtime state；lock busy 時立即回覆提示，不會等待。
- **Runtime JSON 不納入 Git** — 均已 gitignored（含 `runtime/rip.lock`）。
- **相對路徑錨定 SAFE_PDF_ROOT** — path traversal 以 `path_escapes_safe_root` fail-safe 拒絕；絕對路徑依既有語意原樣使用。
- **Operator Runbook** — 安裝 / 設定 / 備份 / 還原 / 升級 / lock 處理詳見 [docs/OPERATOR_DEPLOYMENT.md](docs/OPERATOR_DEPLOYMENT.md)。
- **Operator Preflight（Phase 17D）** — `app/core/preflight.run_operator_preflight()` 提供 safe preflight 驗證（Python 版本 / fcntl / SAFE_PDF_ROOT / RUNTIME_DIR / git hygiene）；不取 lock、不建 JSON state。

### Runtime files（本機 runtime state，已 gitignored）

- `runtime/approvals.json`
- `runtime/rename_transactions.json`
- `runtime/move_transactions.json`

### 目前限制

- JSON persistence，非資料庫。
- `rip` console_scripts entry point 透過 Poetry 提供（Phase 17A，需先 `poetry install`）；`poetry run python scripts/mock_line.py "..."` 舊用法仍然有效（向下相容）。
- Help text 為靜態維護（新增指令需手動同步 `command_help_text()`）。
- 絕對路徑仍依既有語意原樣使用，不受 SAFE_PDF_ROOT 錨定限制。
- **版本策略**：`pyproject.toml` package version（0.1.0）為 packaging metadata，非 release version source of truth；RIP release source of truth 為 git tag / release docs；目前準備 **v0.7.6-alpha**。

### Release Checkpoint Notes

**目前版本**：v0.7.7-alpha（Phase 19G — Tag Confirmed）

**Release Notes**：[docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md)

**v0.7.7-alpha** 收斂 Phase 19B / 19D 的 optional SQLite transaction log backend 工作，包含：
- Phase 19B：`SqliteRenameTransactionLog` / `SqliteMoveTransactionLog` SQLite backend 實作（`app/core/sqlite_transaction_log.py`）
- Phase 19D：`TRANSACTION_LOG_BACKEND` 旗標接入 production runtime；`app/core/transaction_log_factory.py` factory；`default_move_transaction_log()` 與三個 mock_line rename 實例化改用 factory 路由

**SQLite backend 重要說明**：
- `TRANSACTION_LOG_BACKEND=json`（預設）→ JSON flat-file backend，production-safe，行為與 v0.7.6-alpha 完全相同
- `TRANSACTION_LOG_BACKEND=sqlite`（experimental opt-in）→ SQLite backend，不建立 `runtime/rip.db` 除非主動設定
- **現有 JSON transaction 歷史不會自動 migrate**：切換到 sqlite 後，舊 JSON history 在 SQLite backend 下不可見（rollback / preview 查不到舊 transaction）；Migration 延後至 Phase 19H
- `prune_transactions()` 在 SQLite backend 下 raise `NotImplementedError`；SQLite prune 延後至 Phase 19I

**Final regression**（Phase 19F）：
- `poetry check`：All set!
- `poetry run pytest -q`：816 passed（+51 since v0.7.6-alpha tag）
- `poetry build`：rex_intelligence_platform-0.1.0 ✅
- `poetry run rip "說明"`：正常 ✅

**package artifact 版本**（0.1.0）為 packaging metadata，RIP release source of truth 為 git tag / release docs。

**歷史紀錄**：v0.7.5-alpha（commit d96f657，Phase 17I）包含 Phase 17A–17G 工作（console_scripts / runtime lock / operator runbook / preflight / packaging / CI）；726 tests。v0.7.4-alpha（Phase 16）包含 approval workflow、rollback 完整流程與 PDF intelligence 核心功能。

**適用場景**：
- 本機文件整理與安全流程驗證
- 個人工作台 PDF 改名 / 搬移操作
- 開發者功能測試與 E2E 流程驗證

**不適用場景**：
- 多人同時操作（無多使用者 / tenant 隔離）
- 長期高併發任務（JSON persistence，無資料庫，非 production daemon）
- 未受控資料夾大批次自動操作（每筆 destructive action 需人工確認）

**安全提醒**：
- Destructive action 需 full match — 指令格式不符不會執行
- Planning / preview 不會改檔案 — 只有「確認改名」「回滾改名」「確認搬移」「回滾搬移」會真的動檔案
- Runtime logs 不進 Git — `runtime/` 目錄已 gitignored
- 建議先在測試資料夾操作，確認計畫正確後再執行 destructive action

---

## 🎯 願景

通過模塊化的 AI Worker 架構，提供一個統一、靈活、可擴展的 AI 平台，使企業能夠輕松集成多個 AI 模型和外部服務。

## 🏗️ 系統架構

RIP 採用四層架構設計：

```
┌─────────────────────────────┐
│    LINE Gateway (入口)       │
├─────────────────────────────┤
│    AI Router (大腦)          │
├─────────────────────────────┤
│    Worker Layer (執行層)     │
│  ├─ AI Workers (Claude...)  │
│  ├─ Data Workers (PDF...)   │
│  └─ Cloud Workers (AWS...)  │
├─────────────────────────────┤
│    External Services         │
└─────────────────────────────┘
```

### 核心特性

✅ **模塊化架構**
- LINE 只是 Gateway，不是核心
- AI Router 作為智能調度器
- Workers 完全獨立，可插拔

✅ **多 AI 模型支持**
- Claude（高質量分析）
- GPT（多模態處理）
- Gemini（低成本快速）

✅ **豐富的數據源**
- PDF 文檔處理
- 本地文件管理
- GitHub 代碼庫
- AWS 雲服務
- Google Calendar

✅ **企業級特性**
- 敏感操作二次確認
- 完整的成本追蹤
- 詳細的執行日誌
- 高可用部署

✅ **預留未來擴展**
- RAG（檢索增強生成）
- MCP（模型上下文協議）
- Agent（自主代理）
- Task Queue（任務隊列）

## 📚 文檔結構

| 文檔 | 內容 | 閱讀時間 |
|------|------|---------|
| [01-PROJECT_STRUCTURE.md](docs/01-PROJECT_STRUCTURE.md) | 項目目錄設計 | 10 min |
| [02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) | 系統架構圖 | 20 min |
| [03-WORKER_DESIGN.md](docs/03-WORKER_DESIGN.md) | Worker 分工 | 30 min |
| [04-AI_ROUTER.md](docs/04-AI_ROUTER.md) | Router 設計 | 30 min |
| [05-DEPLOYMENT.md](docs/05-DEPLOYMENT.md) | 部署架構 | 25 min |
| [06-ROADMAP.md](docs/06-ROADMAP.md) | 開發 Roadmap | 20 min |

## 🚀 快速開始

### 前置要求

- Docker & Docker Compose（推薦）
- 或 Python 3.11+ + PostgreSQL + Redis（本地開發）
- Git

### 方式 1: 使用 Docker Compose（推薦）

```bash
# 1. 克隆項目
git clone https://github.com/xxx/rex-intelligence-platform.git
cd rex-intelligence-platform

# 2. 複製環境配置
cp .env.example .env

# 3. 編輯 .env，添加你的 API Key（可選，Phase 1 使用模擬數據）
# 需要配置:
#   - LINE_CHANNEL_ID
#   - LINE_CHANNEL_SECRET
#   - LINE_ACCESS_TOKEN
#   - ANTHROPIC_API_KEY
#   - OPENAI_API_KEY
#   - GOOGLE_API_KEY
#   - GITHUB_TOKEN
#   - AWS_* (可選)

# 4. 啟動所有服務
docker-compose up -d

# 5. 驗證服務
docker-compose ps
curl http://localhost:8000/health

# 6. 查看日誌
docker-compose logs -f rip-api

# 7. 停止服務
docker-compose down
```

### 方式 2: 本地開發（使用 Python 虛擬環境）

```bash
# 1. 克隆項目
git clone https://github.com/xxx/rex-intelligence-platform.git
cd rex-intelligence-platform

# 2. 創建 Python 虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 3. 複製環境配置
cp .env.example .env

# 4. 編輯 .env
# 確保以下設置指向本地服務：
#   - DATABASE_URL=postgresql://postgres:password@localhost:5432/rip_dev
#   - REDIS_URL=redis://localhost:6379/0

# 5. 啟動 PostgreSQL 和 Redis（需在另外兩個終端機運行）
# 終端 1: Docker 啟動 PostgreSQL 和 Redis
docker run --name rip-postgres -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=rip_dev -p 5432:5432 -d postgres:15-alpine
docker run --name rip-redis -p 6379:6379 -d redis:7-alpine

# 6. 安裝依賴
pip install -e ".[dev]"

# 7. 啟動開發服務器
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 8. 驗證服務
curl http://localhost:8000/health

# 9. 運行測試
pytest tests/ -v

# 10. 停止服務
# Ctrl+C 停止 uvicorn
docker stop rip-postgres rip-redis
docker rm rip-postgres rip-redis
deactivate  # 退出虛擬環境
```

### 測試 Gateway

```bash
# 發送測試消息到 Gateway
curl -X POST http://localhost:8000/line/webhook \
  -H "Content-Type: application/json" \
  -H "X-Line-Signature: test" \
  -d '{
    "events": [{
      "type": "message",
      "message": {
        "type": "text",
        "text": "Hello, RIP!"
      }
    }]
  }'
```

### 本機 Mock LINE CLI

```bash
# 使用本機 CLI 測試 AI Router
python scripts/mock_line.py "處理電費單"

# 預期輸出
小雷收到：我判斷這是 PDF 任務
```

支援測試句子：
- 處理電費單
- 整理 Downloads
- 幫我寫 API
- 幫我整理需求
- 你好

對應輸出會依據 AI Router intent 分流。

## Phase 10 本機執行方式

如果你使用 Poetry：

```bash
poetry run pytest -q
poetry run python scripts/mock_line.py "處理電費單"
```

如果你使用本地虛擬環境 `.venv`：

```bash
source .venv/bin/activate
python -m pytest -q
python scripts/mock_line.py "處理電費單"
```

要測試 PDF Intelligence Engine，請把 PDF 檔案放到：

```bash
workspace/sandbox/pdf_inbox
```

這個流程目前仍屬 dry-run，不會更名或修改 PDF。PDF 分析只會掃描檔案、擷取第一頁文字、判斷類型和回傳報告。

目前測試狀態：`35 tests passed`

### 安全資料夾分析

`整理 Downloads` 會在安全根目錄中分析 `Downloads` 資料夾，預設安全根目錄為：

```bash
workspace/sandbox/inbox
```

你也可以在 `.env` 中覆寫：

```bash
SAFE_FOLDER_ROOT=/path/to/your/sandbox/inbox
```

此操作為 dry-run，僅做分析，不會搬移或刪除檔案。

## � 成本管理

RIP 提供完整的成本追蹤：

```
每個 API 調用都被記錄：
├─ API 提供商 (OpenAI, Anthropic, Google)
├─ 模型名稱 (GPT-4, Claude 3, Gemini)
├─ Token 數量 (input, output)
├─ 成本估算

用戶可以查詢:
└─ /cost/user/<user_id>           # 個人成本
   /cost/provider/<provider>      # 按服務商成本
   /cost/day/<date>               # 按日期成本
```

## 🧪 API 測試

### 健康檢查

```bash
# 基本健康檢查
curl http://localhost:8000/health

# 詳細健康檢查（包含 Worker 狀態）
curl http://localhost:8000/health/detailed
```

### LINE Webhook 測試

```bash
# 發送測試消息 - PDF 處理
curl -X POST http://localhost:8000/line/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "type": "message",
      "message": {
        "type": "text",
        "text": "請幫我分析電費單",
        "id": "100001"
      },
      "timestamp": 1262304000000,
      "mode": "active",
      "replyToken": "nHuyWiB7yP5Zw52FIkcQT",
      "source": {
        "type": "user",
        "userId": "U1234567890abcdef1234567890abcdef"
      }
    }]
  }'

# 發送測試消息 - 文件夾操作
curl -X POST http://localhost:8000/line/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "type": "message",
      "message": {
        "type": "text",
        "text": "幫我整理資料夾",
        "id": "100002"
      },
      "timestamp": 1262304000000,
      "mode": "active",
      "replyToken": "nHuyWiB7yP5Zw52FIkcQT",
      "source": {
        "type": "user",
        "userId": "U1234567890abcdef1234567890abcdef"
      }
    }]
  }'

# 發送測試消息 - 代碼生成
curl -X POST http://localhost:8000/line/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "type": "message",
      "message": {
        "type": "text",
        "text": "幫我寫 Python 函數計算費波那契數列",
        "id": "100003"
      },
      "timestamp": 1262304000000,
      "mode": "active",
      "replyToken": "nHuyWiB7yP5Zw52FIkcQT",
      "source": {
        "type": "user",
        "userId": "U1234567890abcdef1234567890abcdef"
      }
    }]
  }'
```

## �📖 使用示例

### 示例 1: 簡單文本生成

```
用戶: "幫我寫個 Python 函數來計算費波那契數列"

→ AI Router 檢測意圖: "code_generation"
→ 選擇 Worker: Claude Worker
→ 調用 API 生成代碼
→ 返回結果給用戶
```

### 示例 2: 複雜多步驟任務

```
用戶: "分析 GitHub repo 代碼並生成優化報告，保存到 S3"

→ AI Router 分解為多步驟工作流:
   1. GitHub Worker: 克隆 repo
   2. Claude Worker: 分析代碼
   3. PDF Worker: 生成報告
   4. AWS Worker: 上傳到 S3

→ 按依賴關係順序執行
→ 返回最終結果
```

### 示例 3: 敏感操作確認

```
用戶: "刪除我 GitHub 上的 repo"

→ AI Router 檢測: 敏感操作
→ 發送確認消息: "確認要刪除 xxx 嗎？"
→ 等待用戶確認
→ 收到確認後執行刪除
```

## 🏗️ 項目結構

```
rex-intelligence-platform/
├── docs/                          # 設計文檔
├── src/
│   ├── core/                      # 核心 (Router, Message Bus)
│   ├── gateway/                   # LINE Gateway
│   ├── workers/                   # Worker 實現
│   │   ├── ai/                    # AI Workers
│   │   ├── data/                  # Data Workers
│   │   └── cloud/                 # Cloud Workers
│   ├── rag/                       # RAG (預留)
│   ├── mcp/                       # MCP (預留)
│   ├── agent/                     # Agent (預留)
│   ├── task/                      # Task Queue (預留)
│   └── utils/                     # 工具函數
├── tests/                         # 測試
├── config/
│   ├── docker-compose.yml
│   └── .env.example
└── pyproject.toml                 # Python 依賴
```

## 🔧 配置管理

所有敏感信息都通過環境變量管理：

```bash
# .env 文件示例
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# LINE Configuration
LINE_CHANNEL_ID=your_channel_id
LINE_CHANNEL_SECRET=your_secret
LINE_ACCESS_TOKEN=your_token

# API Keys
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
GOOGLE_API_KEY=xxx
GITHUB_TOKEN=ghp_xxx

# AWS (optional)
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=xxx
AWS_REGION=us-east-1
```

**重要**: 不要提交 .env 文件到 Git！

## 📊 成本管理

RIP 提供完整的成本追蹤：

```
每個 API 調用都被記錄：
├─ API 提供商 (OpenAI, Anthropic, Google)
├─ 模型名稱 (GPT-4, Claude 3, Gemini)
├─ Token 數量 (input, output)
├─ 成本估算

用戶可以查詢:
└─ /cost/user/<user_id>           # 個人成本
   /cost/provider/<provider>      # 按服務商成本
   /cost/day/<date>               # 按日期成本
```

## 🔒 安全特性

✅ **敏感操作確認**
- 刪除、覆蓋、大規模修改需要二次確認
- 確認超時自動拒絕

✅ **審計日誌**
- 所有操作完整記錄
- 包含執行人、時間、參數、結果

✅ **API Key 管理**
- 環境變量存儲
- 加密存儲
- 定期輪換

✅ **速率限制**
- 防止濫用
- 按優先級分配資源

## 📈 監控和可觀測性

```
監控指標:
├─ Gateway
│  ├─ 請求速率
│  ├─ 響應時間
│  └─ 錯誤率
│
├─ Router
│  ├─ 意圖檢測準確率
│  ├─ 工作流執行時間
│  └─ Worker 選擇準確率
│
├─ Workers
│  ├─ 執行成功率
│  ├─ 平均響應時間
│  ├─ API 調用計數
│  └─ 成本統計
│
└─ System
   ├─ CPU/Memory 使用
   ├─ 磁盤 I/O
   └─ 網絡 I/O
```

通過 Prometheus + Grafana 可視化。

## 🧪 測試

```bash
# 運行單元測試
pytest tests/

# 運行集成測試
pytest tests/ -m integration

# 運行覆蓋率分析
pytest --cov=src tests/

# 運行性能測試
pytest tests/performance/ --benchmark
```

目標: >90% 代碼覆蓋率

## 🚢 部署

### 開發部署

```bash
docker-compose up -d
```

### 生產部署

```bash
# 構建鏡像
docker build -t rip/gateway:v1.0.0 -f docker/gateway/Dockerfile .

# 推送到 Registry
docker push rip/gateway:v1.0.0

# 部署到 Kubernetes
kubectl apply -f k8s/
```

詳見 [05-DEPLOYMENT.md](docs/05-DEPLOYMENT.md)

## 📅 開發 Roadmap

| Phase | Timeline | 目標 |
|-------|----------|------|
| **Foundation** | Month 1-2 | 項目框架、基礎設施 |
| **Core Services** | Month 2-4 | Gateway、Router、Workers |
| **Integration** | Month 4-6 | 完整集成、測試優化 |
| **Production** | Month 6 | 生產就緒 |
| **Advanced** | Month 8+ | RAG、MCP、Agent、Task Queue |

詳見 [06-ROADMAP.md](docs/06-ROADMAP.md)

## 👥 貢獻指南

我們歡迎貢獻！請見 [CONTRIBUTING.md](CONTRIBUTING.md)

### 常見任務

1. **新增 Worker**
   - 繼承 `BaseWorker`
   - 實現必需方法
   - 編寫測試
   - 更新文檔

2. **改進 Router**
   - 優化意圖識別
   - 改進 Worker 選擇
   - 增強錯誤處理

3. **優化性能**
   - 緩存優化
   - 並發改進
   - 成本降低

## 📞 支持

- 📧 Email: support@example.com
- 💬 Discord: [Join Server]
- 📝 Issues: [GitHub Issues]
- 📚 Wiki: [Documentation]

## 📄 許可證

MIT License - 見 [LICENSE](LICENSE)

## 🙏 致謝

感謝所有貢獻者和用戶！

---

**Made with ❤️ by Rex Intelligence Platform Team**

Last Updated: June 9, 2024
