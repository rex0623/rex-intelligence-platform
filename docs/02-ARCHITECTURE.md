# 系統架構圖

## 1. 高層架構 - Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                      │
│  LINE Bot  │ Web Chat │ Mobile App │ Desktop App │ API      │
└────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Gateway Layer                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          LINE Gateway                                │   │
│  │  • 消息轉換 (Webhook → Internal Format)             │   │
│  │  • 用戶認證                                         │   │
│  │  • 速率限制                                         │   │
│  │  • 審計日誌                                         │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Router Layer (Brain)                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          AI Router                                   │   │
│  │  • 意圖識別                                         │   │
│  │  • 任務分解                                         │   │
│  │  • Worker 選擇                                      │   │
│  │  • 優先級管理                                       │   │
│  │  • 上下文管理                                       │   │
│  │  • 結果聚合                                         │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Message Bus     │  │  State Manager   │  │  Worker Manager  │
│                  │  │                  │  │                  │
│• Pub/Sub         │  │• User State      │  │• 註冊/註銷       │
│• Event Queue     │  │• Session Cache   │  │• 狀態監控        │
│• Rate Limiting   │  │• Context Store   │  │• 自動恢復        │
└──────────────────┘  └──────────────────┘  └──────────────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Worker Layer                              │
│                                                               │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│ │ AI Workers   │  │ Data Workers │  │ Cloud Workers│        │
│ ├──────────────┤  ├──────────────┤  ├──────────────┤        │
│ │ Claude       │  │ PDF          │  │ AWS          │        │
│ │ GPT          │  │ Folder       │  │ Calendar     │        │
│ │ Gemini       │  │ GitHub       │  │ Slack        │        │
│ └──────────────┘  └──────────────┘  └──────────────┘        │
│                                                               │
│ ┌──────────────┐                                            │
│ │ Custom Worker│ (插件系統)                                 │
│ └──────────────┘                                            │
│                                                               │
└─────────────────────────────────────────────────────────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
         ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  External APIs   │  │  File System     │  │  Cloud Services  │
│                  │  │                  │  │                  │
│• OpenAI          │  │• Local Storage   │  │• AWS S3          │
│• Anthropic       │  │• Database        │  │• Google Calendar │
│• Google          │  │• Cache           │  │• GitHub API      │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

## 2. 消息流程 - Sequence Diagram

```
用戶                Line Gateway           AI Router          Workers
 │                      │                     │                  │
 │ 1. 發送消息           │                     │                  │
 ├─────────────────────────>                  │                  │
 │                      │  2. 轉換格式         │                  │
 │                      ├────────────────────>│                  │
 │                      │                     │  3. 意圖識別      │
 │                      │                     ├─ ─ ─ ─ ─ ─ ─ ─ >│
 │                      │                     │  4. 任務分解      │
 │                      │                     │  5. 選擇 Worker   │
 │                      │                     │  6. 需要確認？    │
 │                      │                     │<─────────────────┤
 │                      │                     │  7. 等待確認      │
 │                      │<────────────────────┤                  │
 │ 8. 確認提示           │                     │                  │
 │<─────────────────────┤                     │                  │
 │                      │  9. 確認            │                  │
 ├─────────────────────────>                  │                  │
 │                      │  10. 再次路由       │                  │
 │                      ├────────────────────>│                  │
 │                      │                     │  11. 調用 Worker  │
 │                      │                     ├─────────────────>│
 │                      │                     │  12. 執行         │
 │                      │                     │<─────────────────┤
 │                      │                     │  13. 處理結果     │
 │ 14. 返回結果         │                     │                  │
 │<─────────────────────┤<────────────────────┤                  │
 │                      │                     │                  │
```

## 3. Worker 交互模型

```
┌─────────────────────────────────────────────────────────────┐
│                     AI Router (Orchestrator)                 │
└─────────────────────────────────────────────────────────────┘
         │                           │                   │
         ▼                           ▼                   ▼
    ┌────────┐                  ┌────────┐          ┌────────┐
    │ Claude │◄────────Async────│ Router │──────►   │ GPT    │
    │ Worker │   Event System    │        │  Config  │ Worker │
    └────────┘                  └────────┘          └────────┘
         │                           │                   │
         │  Worker Message Format    │                   │
         │  {                        │                   │
         │    id: "uuid",            │                   │
         │    type: "request",       │                   │
         │    worker: "claude",      │                   │
         │    payload: {...},        │                   │
         │    priority: "high",      │                   │
         │    timeout: 30000,        │                   │
         │    require_confirm: true, │                   │
         │    metadata: {...}        │                   │
         │  }                        │                   │
         │                           │                   │
         ▼                           ▼                   ▼
    ┌────────┐                  ┌────────┐          ┌────────┐
    │  PDF   │◄────────Sync─────│ Router │──────►   │Folder  │
    │ Worker │   Callback        │        │  State   │ Worker │
    └────────┘                  └────────┘          └────────┘
```

## 4. 核心模塊依賴圖

```
┌───────────────┐
│   Gateway     │
│   (入口)      │
└───────┬───────┘
        │
        ▼
┌──────────────────────┐
│   AI Router          │
│   • Router logic     │◄─────────┐
│   • Intent detection │          │
│   • Task decompose   │          │
└───────┬──────────────┘          │
        │                         │
        ├─────────────┬───────────┤───────┐
        │             │           │       │
        ▼             ▼           ▼       ▼
┌─────────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐
│   Workers   │ │State Mgr │ │Msg Bus │ │Worker Mgr│
│             │ │          │ │        │ │          │
│ • AI        │ │• Cache   │ │• Queue │ │• Monitor │
│ • Data      │ │• Context │ │• Pub   │ │• Registry│
│ • Cloud     │ │• Session │ │• Event │ │• Recovery│
└─────────────┘ └──────────┘ └────────┘ └──────────┘
        │             │           │       │
        └─────────────┴───────────┴───────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │  External APIs & Services   │
        │  • LLM APIs                 │
        │  • Cloud Services           │
        │  • File System              │
        └─────────────────────────────┘
```

## 5. 部署容器架構

```
Docker Host
│
├─ rip-gateway
│  ├─ LINE Webhook Server
│  └─ Message Transformer
│
├─ rip-router
│  ├─ AI Router Core
│  ├─ State Manager
│  └─ Message Bus
│
├─ rip-worker-ai
│  ├─ Claude Integration
│  ├─ GPT Integration
│  └─ Gemini Integration
│
├─ rip-worker-data
│  ├─ PDF Processor
│  ├─ File Manager
│  └─ GitHub Connector
│
├─ rip-worker-cloud
│  ├─ AWS Integration
│  └─ Calendar Integration
│
├─ rip-redis
│  └─ Cache & Message Queue
│
├─ rip-postgres
│  └─ State Persistence
│
└─ rip-monitoring
   ├─ Prometheus
   └─ Grafana
```

## 6. 數據流 - 典型使用場景

### 場景 1: 簡單文本生成

```
User: "幫我寫個 Python 函數來計算費波那契數列"
       │
       ▼ LINE Gateway
       │
       ▼ AI Router (Content Detected: "code generation")
       │
       ▼ Worker Selector
       │
       ├─ Option 1: Claude (cost: low, quality: high)
       ├─ Option 2: GPT (cost: high, quality: high)
       └─ Option 3: Gemini (cost: medium, quality: medium)
       │
       ▼ Router Decision: Claude (optimal)
       │
       ▼ Claude Worker
       │
       ▼ LLM API Call
       │
       ▼ Result → AI Router
       │
       ▼ Format & Send → LINE Gateway
       │
       ▼ User receives answer
```

### 場景 2: 複雜多步驟任務

```
User: "分析 GitHub repo 的代碼複雜度並生成優化建議"
       │
       ▼ AI Router (Multi-step Task Detected)
       │
       ├─ Step 1: GitHub Worker → 獲取代碼
       ├─ Step 2: Claude Worker → 分析
       ├─ Step 3: PDF Worker → 生成報告
       └─ Step 4: AWS Worker → 上傳到 S3
       │
       ▼ Aggregator: Combine results
       │
       ▼ User receives full report
```

### 場景 3: 敏感操作 - 需要確認

```
User: "刪除 GitHub repo xxx"
       │
       ▼ AI Router (Sensitive Operation Detected)
       │
       ▼ Generate Confirmation Message
       │
       ▼ Send to User: "確認要刪除 xxx 嗎？(Yes/No)"
       │
       ├─ User: No ──> Abort
       │
       └─ User: Yes ──> GitHub Worker Delete
                      │
                      ▼ Operation Complete
```

## 架構特點

✅ **模塊化**：每個層級獨立，職責清晰  
✅ **可擴展**：易於添加新的 Worker 或 Gateway  
✅ **可靠性**：異步消息、重試機制、狀態恢復  
✅ **可觀測性**：完整的日誌、監控、追蹤  
✅ **安全性**：敏感操作確認、審計日誌、加密  
✅ **高性能**：異步 I/O、緩存、隊列機制
