# RIP - Rex Intelligence Platform

打造企業級以 LINE 為入口的 AI 作業系統。

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

- Docker & Docker Compose
- Python 3.11+
- Git

### 開發環境設置

```bash
# 1. 克隆項目
git clone https://github.com/xxx/rex-intelligence-platform.git
cd rex-intelligence-platform

# 2. 複製環境配置
cp .env.example .env

# 3. 編輯 .env，添加你的 API Key
# 需要配置:
#   - LINE_CHANNEL_ID
#   - LINE_CHANNEL_SECRET
#   - LINE_ACCESS_TOKEN
#   - ANTHROPIC_API_KEY
#   - OPENAI_API_KEY
#   - GOOGLE_API_KEY
#   - GITHUB_TOKEN
#   - AWS_* (可選)

# 4. 啟動服務
docker-compose up -d

# 5. 驗證服務
docker-compose ps
curl http://localhost:8000/health

# 6. 查看日誌
docker-compose logs -f rip-router
```

### 測試 Gateway

```bash
# 發送測試消息到 Gateway
curl -X POST http://localhost:8000/webhook \
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

## 📖 使用示例

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
