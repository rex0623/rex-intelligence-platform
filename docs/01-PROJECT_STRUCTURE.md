# RIP - 專案目錄結構

```
rex-intelligence-platform/
│
├── docs/                          # 文檔
│   ├── 01-PROJECT_STRUCTURE.md   # 項目結構
│   ├── 02-ARCHITECTURE.md        # 系統架構
│   ├── 03-WORKER_DESIGN.md       # Worker 分工
│   ├── 04-AI_ROUTER.md           # AI Router 設計
│   ├── 05-DEPLOYMENT.md          # 部署架構
│   └── 06-ROADMAP.md             # 開發 Roadmap
│
├── src/                           # 源代碼
│   ├── core/                      # 核心模塊
│   │   ├── __init__.py
│   │   ├── ai_router.py          # AI 路由核心邏輯
│   │   ├── worker_manager.py      # Worker 管理器
│   │   ├── message_bus.py         # 消息總線
│   │   └── state_manager.py       # 狀態管理
│   │
│   ├── gateway/                   # 網關層
│   │   ├── __init__.py
│   │   └── line_gateway.py        # LINE 消息網關
│   │
│   ├── workers/                   # Worker 實現
│   │   ├── __init__.py
│   │   ├── base_worker.py         # Worker 基類
│   │   │
│   │   ├── ai/                    # AI Worker
│   │   │   ├── __init__.py
│   │   │   ├── claude_worker.py   # Claude Worker
│   │   │   ├── gpt_worker.py      # GPT Worker
│   │   │   └── gemini_worker.py   # Gemini Worker
│   │   │
│   │   ├── data/                  # 數據 Worker
│   │   │   ├── __init__.py
│   │   │   ├── pdf_worker.py      # PDF 處理
│   │   │   ├── folder_worker.py   # 文件夾處理
│   │   │   └── github_worker.py   # GitHub 集成
│   │   │
│   │   ├── cloud/                 # 雲服務 Worker
│   │   │   ├── __init__.py
│   │   │   ├── aws_worker.py      # AWS 集成
│   │   │   └── calendar_worker.py # 日曆集成
│   │   │
│   │   └── extension/             # 擴展 Worker 目錄
│   │       └── __init__.py
│   │
│   ├── rag/                       # RAG 模塊（預留）
│   │   ├── __init__.py
│   │   ├── vector_store.py
│   │   ├── retriever.py
│   │   └── indexer.py
│   │
│   ├── mcp/                       # MCP 模塊（預留）
│   │   ├── __init__.py
│   │   └── mcp_server.py
│   │
│   ├── agent/                     # Agent 模塊（預留）
│   │   ├── __init__.py
│   │   ├── base_agent.py
│   │   └── agent_manager.py
│   │
│   ├── task/                      # 任務隊列（預留）
│   │   ├── __init__.py
│   │   ├── task_queue.py
│   │   └── task_executor.py
│   │
│   ├── utils/                     # 工具函數
│   │   ├── __init__.py
│   │   ├── logger.py              # 日誌
│   │   ├── config.py              # 配置管理
│   │   ├── validation.py          # 驗證工具
│   │   └── security.py            # 安全工具
│   │
│   └── api/                       # API 層（預留）
│       ├── __init__.py
│       ├── routes.py
│       └── middleware.py
│
├── tests/                         # 測試
│   ├── __init__.py
│   ├── test_workers/
│   ├── test_ai_router/
│   ├── test_gateway/
│   └── fixtures/
│
├── config/                        # 配置文件
│   ├── docker-compose.yml         # Docker 編排
│   ├── .env.example               # 環境變數示例
│   └── settings.yaml              # 應用配置
│
├── scripts/                       # 腳本
│   ├── setup.sh                   # 設置腳本
│   ├── start.sh                   # 啟動腳本
│   ├── stop.sh                    # 停止腳本
│   └── dev_setup.sh               # 開發環境設置
│
├── pyproject.toml                 # Python 項目配置
├── poetry.lock                    # Python 依賴鎖定（如使用 Poetry）
├── requirements.txt               # Python 依賴（備選）
├── Dockerfile                     # Docker 鏡像
├── .dockerignore
├── .gitignore
├── .env.example
├── README.md
└── CONTRIBUTING.md
```

## 文件夾用途說明

### 核心層次

| 層次 | 目錄 | 職責 |
|------|------|------|
| **Gateway** | `src/gateway/` | LINE 或其他消息入口 |
| **Router** | `src/core/ai_router.py` | 消息路由和智能決策 |
| **Workers** | `src/workers/` | 具體功能實現 |
| **Infrastructure** | `src/rag/`, `src/mcp/`, `src/task/` | 基礎設施組件 |
| **API** | `src/api/` | 內部 API 調用 |

### Worker 分類

```
Workers/
├── AI Worker        # Claude、GPT、Gemini
├── Data Worker      # PDF、Folder、GitHub
├── Cloud Worker     # AWS、Calendar
└── Custom Worker    # 未來擴展位置
```

## 關鍵設計特點

✅ **模塊化**：每個 Worker 獨立，可單獨增加/替換/停用  
✅ **可擴展**：預留 `src/workers/extension/` 目錄  
✅ **分離關注**：Gateway、Router、Workers 職責明確  
✅ **基礎設施準備**：RAG、MCP、Agent、Task Queue 目錄已預留  
✅ **配置管理**：.env、settings.yaml、docker-compose.yml 統一管理  
✅ **測試就緒**：完整的 tests/ 目錄結構
