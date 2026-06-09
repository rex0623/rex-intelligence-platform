# Phase 1 開發運行指南

## ✨ 完成的功能

### Core
- ✅ FastAPI 應用框架
- ✅ 配置管理 (app/core/config.py)
- ✅ 日誌系統 (app/core/logger.py)
- ✅ 數據模型 (Pydantic schemas)

### Gateway
- ✅ LINE Gateway (消息接收、驗證、簽名檢查)
- ✅ Webhook 端點 (POST /line/webhook)

### Router
- ✅ AI Router (消息路由、意圖識別)
- ✅ 簡單意圖檢測：
  - PDF 相關 → PDF Worker
  - 文件夾相關 → Folder Worker
  - 代碼相關 → Claude Worker
  - 其他 → Default Response

### Workers
- ✅ Worker 基類 (BaseWorker)
- ✅ PDF Worker (mock data)
- ✅ Folder Worker (mock data)
- ✅ Claude Worker (mock data)
- ✅ GPT Worker (mock data)

### API Endpoints
- ✅ GET /health - 基本健康檢查
- ✅ GET /health/detailed - 詳細健康檢查
- ✅ POST /line/webhook - LINE 消息接收
- ✅ GET / - 根端點 (API 信息)

### 部署
- ✅ Dockerfile - 容器鏡像
- ✅ docker-compose.yml - 編排配置
- ✅ pytest.ini - 測試配置
- ✅ tests/ - 測試套件

---

## 🚀 本機開發運行方式

### 方式 1: Docker Compose（推薦）

**優點**：無需安裝依賴，一鍵啟動所有服務

```bash
# 啟動
docker-compose up -d

# 驗證
curl http://localhost:8000/health

# 查看日誌
docker-compose logs -f rip-api

# 停止
docker-compose down

# 強制重建鏡像（如更新依賴）
docker-compose up --build -d
```

### 方式 2: 本地 Python 環境

**優點**：開發更快速，可直接編輯代碼

```bash
# 1. 設置虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 2. 啟動 PostgreSQL 和 Redis（Docker 容器）
docker run --name rip-postgres -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=rip_dev -p 5432:5432 -d postgres:15-alpine
docker run --name rip-redis -p 6379:6379 -d redis:7-alpine

# 3. 安裝依賴
pip install -e ".[dev]"

# 4. 運行開發服務器（自動重載）
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. 在另一個終端運行測試
pytest tests/ -v

# 6. 清理資源
docker stop rip-postgres rip-redis
docker rm rip-postgres rip-redis
deactivate
```

---

## 🧪 API 測試

### 健康檢查

```bash
# 基本健康檢查
curl http://localhost:8000/health

# 詳細健康檢查（包含 Worker 狀態）
curl http://localhost:8000/health/detailed

# 根端點
curl http://localhost:8000/
```

### LINE Webhook 測試

#### 測試 1: PDF Worker 觸發

```bash
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
      "replyToken": "test_token",
      "source": {"type": "user", "userId": "test_user"}
    }]
  }'
```

**預期結果**：
```json
{
  "status": "ok",
  "message": "Event received",
  "details": {
    "status": "success",
    "events_processed": 1,
    "results": [
      {
        "user_id": "test_user",
        "message": "請幫我分析電費單",
        "intent": "pdf_processing",
        "worker_id": "pdf_worker",
        "response": {
          "success": true,
          "data": {
            "status": "success",
            "action": "generate",
            "data": {...}
          }
        }
      }
    ]
  }
}
```

#### 測試 2: Folder Worker 觸發

```bash
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
      "replyToken": "test_token",
      "source": {"type": "user", "userId": "test_user"}
    }]
  }'
```

**預期結果**：`intent: "file_management"`, `worker_id: "folder_worker"`

#### 測試 3: Claude Worker 觸發

```bash
curl -X POST http://localhost:8000/line/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "type": "message",
      "message": {
        "type": "text",
        "text": "幫我寫 Python 代碼計算費波那契",
        "id": "100003"
      },
      "timestamp": 1262304000000,
      "mode": "active",
      "replyToken": "test_token",
      "source": {"type": "user", "userId": "test_user"}
    }]
  }'
```

**預期結果**：`intent: "code_generation"`, `worker_id: "claude_worker"`

#### 測試 4: 預設回應

```bash
curl -X POST http://localhost:8000/line/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "type": "message",
      "message": {
        "type": "text",
        "text": "你好，今天天氣如何？",
        "id": "100004"
      },
      "timestamp": 1262304000000,
      "mode": "active",
      "replyToken": "test_token",
      "source": {"type": "user", "userId": "test_user"}
    }]
  }'
```

**預期結果**：`intent: "general_query"`, `worker_id: "claude_worker"`, 回傳預設訊息

---

## 📊 測試

### 運行所有測試

```bash
pytest tests/ -v
```

### 運行特定測試

```bash
# 運行健康檢查測試
pytest tests/test_health.py -v

# 運行特定測試
pytest tests/test_health.py::test_health_check -v
```

### 代碼覆蓋率

```bash
pytest --cov=app tests/
```

---

## 🔧 代碼品質檢查

### 代碼格式化

```bash
black app tests
isort app tests
```

### 代碼檢查

```bash
flake8 app tests
mypy app
pylint app
```

### 所有檢查

```bash
black app tests && \
isort app tests && \
flake8 app tests && \
mypy app && \
pytest tests/ -v
```

---

## 📝 開發流程

### 1. 開發新功能

```bash
# 創建特性分支
git checkout -b feature/my-feature

# 編輯代碼
vim app/my_module.py

# 編寫測試
vim tests/test_my_module.py

# 運行測試
pytest tests/test_my_module.py -v

# 代碼檢查
black app tests
isort app tests
flake8 app tests
```

### 2. 提交代碼

```bash
# 檢查狀態
git status

# 添加文件
git add app/ tests/

# 提交
git commit -m "feat: add my feature"

# 推送
git push origin feature/my-feature

# 創建 Pull Request
```

---

## 🐛 常見問題

### 問題 1: 連接被拒絕

**症狀**：`Connection refused`

**解決方案**：
```bash
# 檢查服務是否運行
docker-compose ps

# 重啟服務
docker-compose restart rip-api

# 查看日誌
docker-compose logs rip-api
```

### 問題 2: 端口被佔用

**症狀**：`Address already in use`

**解決方案**：
```bash
# 找出佔用端口的進程
lsof -i :8000  # Linux/Mac
netstat -ano | findstr :8000  # Windows

# 殺死進程或使用不同端口
docker-compose down
```

### 問題 3: 依賴衝突

**症狀**：`pip install` 失敗

**解決方案**：
```bash
# 清除緩存
pip cache purge

# 重新安裝
pip install -e ".[dev]" --force-reinstall
```

---

## 🎯 下一步（Phase 2）

- [ ] 實現真實的 LINE API 集成
- [ ] 集成真實的 LLM APIs (Anthropic, OpenAI, Google)
- [ ] 實現數據庫模型（用戶、會話、執行追蹤）
- [ ] 實現完整的成本追蹤
- [ ] 添加更多 Workers（GitHub、AWS、Calendar）
- [ ] 實現敏感操作確認機制
- [ ] 集成 Redis 消息隊列
- [ ] 添加完整的監控和日誌

---

**Made with ❤️ by RIP Team**

Last Updated: June 9, 2024
