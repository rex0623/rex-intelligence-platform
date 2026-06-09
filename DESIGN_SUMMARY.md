# 設計總結 - Rex Intelligence Platform

## 📋 快速概覽

**項目名稱**：Rex Intelligence Platform (RIP)  
**類型**：企業級 AI 作業系統  
**入口**：LINE Bot  
**核心**：AI Router（智能路由和任務調度）  
**Workers**：Claude、GPT、Gemini、PDF、Folder、GitHub、AWS、Calendar  
**部署**：Docker Compose (Dev) / Kubernetes (Prod)  

---

## 🎯 核心設計原則

| 原則 | 說明 |
|------|------|
| **1. LINE 是 Gateway** | 不是核心，只是消息入口。可輕易替換為其他消息平台。 |
| **2. Router 是大腦** | 所有智能決策和路由都在 Router，而不是分散到各處。 |
| **3. Workers 是執行者** | 所有具體工作由 Workers 完成，Router 只負責調度。 |
| **4. 模塊化架構** | 每個 Worker 獨立，可以增加、替換或停用。 |
| **5. 敏感操作確認** | 所有刪除、移動、覆蓋操作都需要二次確認。 |
| **6. 配置外部化** | 使用 .env、docker-compose.yml、pyproject.toml 管理配置。 |
| **7. 可觀測性** | 完整的日誌、追蹤、監控，便於調試和分析。 |
| **8. 預留擴展** | RAG、MCP、Agent、Task Queue 架構已預留。 |

---

## 🏗️ 系統分層

### Layer 1: Gateway (入口層)

```
任何消息平台 → Unified Message Format → Router
```

**職責**：
- 接收外部消息
- 轉換為內部格式
- 驗證和認證
- 返回結果

**當前實現**：LINE Gateway

---

### Layer 2: AI Router (大腦層)

```
[意圖識別] → [任務分解] → [Worker選擇] → [工作流編排]
    ↓           ↓           ↓              ↓
  NLP        DAG        Score      Async Execution
```

**核心功能**：
1. **意圖識別** - 理解用戶意圖
2. **任務分解** - 分解為可執行任務
3. **Worker 選擇** - 選擇最優 Worker
4. **工作流編排** - 編排任務依賴
5. **優先級管理** - 資源分配
6. **上下文管理** - 狀態跟蹤
7. **結果聚合** - 合并結果
8. **敏感操作確認** - 安全保護

---

### Layer 3: Worker Layer (執行層)

#### AI Workers（AI 模型）
- **Claude** - 高質量分析、代碼生成
- **GPT** - 多模態、函數調用
- **Gemini** - 快速響應、低成本

#### Data Workers（數據處理）
- **PDF Worker** - PDF 解析、OCR、文本提取
- **Folder Worker** - 文件管理、操作
- **GitHub Worker** - 代碼庫、提交管理

#### Cloud Workers（雲服務）
- **AWS Worker** - S3、Lambda、計算資源
- **Calendar Worker** - 日程管理、提醒

---

### Layer 4: External Services (外部服務層)

- Anthropic Claude API
- OpenAI GPT API
- Google Generative AI
- GitHub API
- AWS Services
- Google Calendar API
- 等等...

---

## 📦 項目結構

```
src/
├── core/
│   ├── ai_router.py          ⭐ 核心 Router
│   ├── worker_manager.py     ⭐ Worker 管理
│   ├── message_bus.py        消息總線
│   └── state_manager.py      狀態管理
│
├── gateway/
│   └── line_gateway.py       LINE 入口
│
├── workers/
│   ├── base_worker.py        Worker 基類
│   ├── ai/                   AI Workers
│   ├── data/                 Data Workers
│   ├── cloud/                Cloud Workers
│   └── extension/            自定義 Workers
│
├── rag/                      RAG (預留)
├── mcp/                      MCP (預留)
├── agent/                    Agent (預留)
├── task/                     Task Queue (預留)
│
└── utils/
    ├── logger.py
    ├── config.py
    ├── validation.py
    └── security.py
```

**其中標記 ⭐ 的是最核心的模塊。**

---

## 🔄 典型工作流

### 場景 1: 簡單查詢

```
User: "用 Claude 寫個 Python 函數"
  ↓
Gateway: 接收消息
  ↓
Router: 意圖識別 → "code_generation"
  ↓
Router: 選擇 Worker → Claude (用戶指定)
  ↓
Claude Worker: 調用 API → 生成代碼
  ↓
Gateway: 返回結果給用戶
```

時間: ~2-3 秒

---

### 場景 2: 複雜工作流

```
User: "分析 GitHub repo 代碼，生成報告保存到 S3"
  ↓
Router: 意圖識別 → "multi-step_analysis"
  ↓
Router: 任務分解 → 4 個任務
    Task 1: GitHub Worker clone
    Task 2: Claude Worker analyze (depends on 1)
    Task 3: PDF Worker generate (depends on 2)
    Task 4: AWS Worker upload (depends on 3)
  ↓
Router: 檢查敏感操作 → Task 4 需要確認
  ↓
Gateway: 發送確認消息給用戶
  ↓
User: 確認操作
  ↓
Router: 順序執行所有任務
  ↓
Gateway: 返回完整結果
```

時間: ~15-30 秒（取決於代碼量）

---

### 場景 3: 敏感操作

```
User: "刪除我 GitHub 上的 repo xxx"
  ↓
Router: 意圖識別 + 檢測敏感操作
  ↓
Router: 發送二次確認請求
  ↓
Gateway: "⚠️ 確認要刪除 xxx 嗎？(是/否)"
  ↓
User: "是"
  ↓
Router: 執行刪除
  ↓
Gateway: "✅ 已刪除"
```

---

## 💾 數據流

### 消息流

```
LINE
  ↓ JSON (webhook)
LINE Gateway
  ↓ Internal Format {user_id, intent, payload}
Redis Queue (priority queue)
  ↓ Event
AI Router
  ↓ Task List [{...}, {...}, {...}]
Workers (serial/parallel)
  ↓ Results [{...}, {...}, {...}]
Result Aggregator
  ↓ Final Response
LINE Gateway
  ↓ JSON (reply)
LINE
```

### 狀態存儲

```
PostgreSQL (持久化)
├─ 用戶信息
├─ 會話歷史
├─ 執行追蹤
├─ 成本記錄
└─ 操作日誌

Redis (高速緩存)
├─ 用戶會話
├─ 執行隊列
├─ Worker 狀態
└─ 臨時數據
```

---

## 🔐 安全機制

### 1. 敏感操作確認

```
敏感操作列表:
- delete (刪除)
- move (移動)
- override (覆蓋)
- uninstall (卸載)
- force_push (強制推送)
- delete_repo (刪除倉庫)
```

流程：
1. Router 檢測敏感操作
2. 生成確認消息
3. 發送給用戶確認
4. 等待用戶回應（30 分鐘超時）
5. 若確認則執行，否則中止

### 2. 認證和授權

- LINE 簽名驗證
- JWT token 驗證
- API Key 加密存儲
- 用戶權限檢查

### 3. 審計日誌

所有操作完整記錄：
- 執行人、時間、操作內容
- 操作參數、結果、錯誤
- 成本、性能指標

### 4. 速率限制

- 每分鐘請求限制
- 每小時請求限制
- 按優先級分配資源

---

## 💰 成本管理

### 成本追蹤

每個 API 調用都被記錄：
```
{
  "user_id": "...",
  "api_provider": "openai",
  "model": "gpt-4",
  "input_tokens": 1000,
  "output_tokens": 500,
  "cost": 0.03,
  "timestamp": "..."
}
```

### 成本優化策略

1. **智能選擇** - 根據需要選擇最便宜的模型
2. **緩存** - 避免重複 API 調用
3. **批量處理** - 合并多個請求
4. **預算限制** - 設定月度預算

---

## 📊 監控和可觀測性

### 指標

```
Gateway
├─ 請求速率 (req/min)
├─ 響應時間 (ms)
└─ 錯誤率 (%)

Router
├─ 意圖檢測準確率 (%)
├─ 工作流執行時間 (s)
└─ Worker 選擇準確率 (%)

Workers
├─ 執行成功率 (%)
├─ 平均響應時間 (ms)
├─ 成本 ($/call)
└─ API 錯誤率 (%)

System
├─ CPU 使用率 (%)
├─ 內存使用率 (%)
├─ 磁盤 I/O (MB/s)
└─ 網絡 I/O (MB/s)
```

### 日誌

- **結構化日誌** - JSON 格式便於分析
- **集中存儲** - ELK Stack（開發中）
- **追蹤 ID** - 全鏈路追蹤
- **多級別** - DEBUG, INFO, WARNING, ERROR

---

## 🚀 部署架構

### 開發環境

```
Docker Host
├─ rip-gateway
├─ rip-router
├─ rip-worker-ai
├─ rip-worker-data
├─ rip-worker-cloud
├─ redis
└─ postgres
```

使用 `docker-compose up` 一鍵啟動

### 生產環境

```
Kubernetes Cluster
├─ Namespace: rip-production
├─ Deployments
│  ├─ rip-gateway (3 replicas, autoscale to 10)
│  ├─ rip-router (3 replicas, autoscale to 15)
│  ├─ rip-worker-* (multiple, autoscale)
├─ Services (Load Balancer, ClusterIP)
├─ Redis Cluster
├─ RDS (PostgreSQL)
├─ Monitoring (Prometheus, Grafana)
└─ Logging (ELK)
```

高可用、可擴展、完全監控

---

## 🛠️ 技術棧

### 后端

- **Framework**: FastAPI + Uvicorn
- **ORM**: SQLAlchemy
- **Database**: PostgreSQL
- **Cache**: Redis
- **Queue**: Redis (or Celery)
- **Logging**: Loguru

### 集成

- **LLM APIs**: Anthropic, OpenAI, Google
- **Cloud**: AWS boto3
- **Version Control**: PyGithub
- **Calendar**: Google Calendar API
- **PDF**: PyPDF2, pdfplumber, pytesseract

### 工具

- **Code Quality**: Black, isort, flake8, mypy
- **Testing**: pytest, pytest-asyncio
- **Monitoring**: Prometheus, Grafana
- **Logging**: ELK Stack (計劃中)

---

## 📈 開發里程碑

```
Phase 1: Foundation
  ├─ Project setup & infra
  ├─ Docker environment
  └─ CI/CD pipeline
  Duration: 2 weeks

Phase 2: Core Services
  ├─ Gateway implementation
  ├─ Router implementation
  ├─ Worker framework
  └─ Basic workers
  Duration: 6 weeks

Phase 3: Integration
  ├─ All workers
  ├─ Testing & optimization
  └─ Documentation
  Duration: 6 weeks

Phase 4: Production Ready
  ├─ Performance optimization
  ├─ Security hardening
  ├─ Monitoring setup
  └─ Production deployment
  Duration: 4 weeks

Phase 5: Advanced Features
  ├─ RAG implementation
  ├─ MCP integration
  ├─ Agent framework
  └─ Task queue system
  Duration: 8+ weeks
```

**Total: 6 months to MVP, 12+ months to full feature set**

---

## 🎯 成功指標

### 功能指標
- ✅ 支持 8+ Workers
- ✅ 複雜工作流支持
- ✅ >90% 測試覆蓋率
- ✅ <5 秒端到端延遲
- ✅ >99.5% 可用性

### 業務指標
- ✅ 1000+ 並發用戶
- ✅ 自動化率 >80%
- ✅ 成本降低 >30%
- ✅ 用戶滿意度 >4.5/5

### 質量指標
- ✅ 代碼覆蓋率 >90%
- ✅ 代碼質量評分 A
- ✅ 安全漏洞 0
- ✅ 文檔完整 100%

---

## 🔗 相關文檔

| 文檔 | 內容 |
|------|------|
| [README.md](../README.md) | 項目概覽 |
| [01-PROJECT_STRUCTURE.md](../docs/01-PROJECT_STRUCTURE.md) | 目錄結構 |
| [02-ARCHITECTURE.md](../docs/02-ARCHITECTURE.md) | 系統架構 |
| [03-WORKER_DESIGN.md](../docs/03-WORKER_DESIGN.md) | Worker 設計 |
| [04-AI_ROUTER.md](../docs/04-AI_ROUTER.md) | Router 設計 |
| [05-DEPLOYMENT.md](../docs/05-DEPLOYMENT.md) | 部署指南 |
| [06-ROADMAP.md](../docs/06-ROADMAP.md) | 開發計劃 |

---

## ❓ 常見問題

**Q: 為什麼選擇 LINE 作為 Gateway？**
A: LINE 是亞洲最流行的消息平台，可方便接觸C端用戶。但系統設計允許輕易替換為其他平台。

**Q: Router 會成為性能瓶頸嗎？**
A: 不會。Router 只做輕量級決策（< 100ms）。具體工作由 Workers 異步執行。

**Q: 支持多個用戶並發嗎？**
A: 完全支持。使用 Redis Queue 和 Worker Pool 實現高並發。

**Q: 如何添加新的 Worker？**
A: 繼承 `BaseWorker`，實現必需方法，通過 Worker Registry 註冊即可。

**Q: 成本如何管理？**
A: 所有 API 調用都被追蹤和計費。支持預算限制和成本警告。

---

## 📝 下一步

1. **閱讀詳細文檔** - 理解每個層級的設計
2. **搭建開發環境** - 按照 README 進行本地開發
3. **運行示例** - 測試基本功能
4. **提交貢獻** - 按照 CONTRIBUTING.md 提交 PR

---

**Made with ❤️ by Rex Intelligence Platform Team**

Last Updated: June 9, 2024
