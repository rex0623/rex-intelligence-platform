# Worker 分工設計

## 1. Worker 基本定義

### Worker 通用接口

```python
class BaseWorker(ABC):
    """所有 Worker 的基類"""
    
    # 必需属性
    id: str                      # 唯一標識符
    name: str                    # 名稱
    version: str                 # 版本
    status: WorkerStatus         # 狀態 (active/inactive/error)
    config: WorkerConfig         # 配置
    
    # 必需方法
    @abstractmethod
    async def process(self, request: WorkerRequest) -> WorkerResponse:
        """執行任務"""
        pass
    
    @abstractmethod
    async def validate(self, request: WorkerRequest) -> bool:
        """驗證請求有效性"""
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """健康檢查"""
        pass
    
    # 可選方法
    async def initialize(self):
        """初始化"""
        pass
    
    async def cleanup(self):
        """清理資源"""
        pass
```

## 2. AI Worker（AI 模型服務）

### 2.1 Claude Worker

| 屬性 | 值 |
|------|-----|
| **用途** | 文本生成、代碼生成、分析 |
| **成本** | 低-中 |
| **速度** | 中等 |
| **質量** | 高 |
| **API** | Anthropic API |
| **模型** | Claude 3.5 Sonnet/Opus/Haiku |

**職責**：
- 文本分析和生成
- 代碼分析和優化
- 知識查詢和解釋
- 複雜推理任務

**配置示例**：
```yaml
claude_worker:
  enabled: true
  version: "1.0"
  api_key: ${ANTHROPIC_API_KEY}
  model: "claude-3-5-sonnet-20241022"
  max_tokens: 4096
  timeout: 60
  retry_attempts: 3
  rate_limit: 100/min
```

### 2.2 GPT Worker

| 屬性 | 值 |
|------|-----|
| **用途** | 多模態處理、函數調用 |
| **成本** | 高 |
| **速度** | 快 |
| **質量** | 高 |
| **API** | OpenAI API |
| **模型** | GPT-4/4o/4 Turbo |

**職責**：
- 視覺分析（圖片識別）
- 函數調用和工具使用
- 實時對話和流式輸出
- 高級推理

**配置示例**：
```yaml
gpt_worker:
  enabled: true
  version: "1.0"
  api_key: ${OPENAI_API_KEY}
  model: "gpt-4o"
  max_tokens: 4096
  timeout: 60
  retry_attempts: 3
  rate_limit: 50/min
```

### 2.3 Gemini Worker

| 屬性 | 值 |
|------|-----|
| **用途** | 快速響應、多語言 |
| **成本** | 低 |
| **速度** | 快 |
| **質量** | 中高 |
| **API** | Google Generative AI API |
| **模型** | Gemini Pro/1.5 Pro |

**職責**：
- 快速文本生成
- 多語言支持
- 實時信息搜索
- 低成本任務

**配置示例**：
```yaml
gemini_worker:
  enabled: true
  version: "1.0"
  api_key: ${GOOGLE_API_KEY}
  model: "gemini-1.5-pro"
  max_tokens: 2048
  timeout: 45
  retry_attempts: 3
  rate_limit: 100/min
```

---

## 3. Data Worker（數據處理服務）

### 3.1 PDF Worker

| 屬性 | 值 |
|------|-----|
| **用途** | PDF 上傳、解析、提取 |
| **成本** | 低（本地計算） |
| **延遲** | 中等 |
| **依賴** | PyPDF2、pdfplumber、LLM |

**職責**：
- PDF 上傳和存儲
- 文本提取和結構化
- 表格識別和提取
- 圖像提取
- 元數據識別
- OCR（光學字符識別）

**支持的操作**：
```python
{
    "extract_text": "提取所有文本",
    "extract_images": "提取所有圖像",
    "extract_tables": "識別和提取表格",
    "get_metadata": "獲取文檔元數據",
    "search": "搜索文本內容",
    "ocr": "光學字符識別"
}
```

**配置示例**：
```yaml
pdf_worker:
  enabled: true
  version: "1.0"
  storage_path: "/data/pdf"
  max_file_size: "100MB"
  supported_formats: ["pdf"]
  ocr_enabled: true
  timeout: 120
  require_confirm: false
```

### 3.2 Folder Worker

| 屬性 | 值 |
|------|-----|
| **用途** | 本地文件管理 |
| **成本** | 低 |
| **延遲** | 低 |
| **依賴** | os、shutil、pathlib |

**職責**：
- 列表文件/文件夾
- 創建/刪除/移動文件
- 讀取/寫入文件
- 文件監視

**支持的操作**：
```python
{
    "list": "列表文件夾內容",
    "read": "讀取文件內容",
    "write": "寫入文件內容",
    "create_folder": "建立文件夾",
    "delete": "刪除文件（敏感）",
    "move": "移動文件（敏感）",
    "copy": "複製文件",
    "search": "搜索文件"
}
```

**敏感操作標記**：
```
delete ✓ 需要確認
move ✓ 需要確認
rename ✓ 需要確認
```

**配置示例**：
```yaml
folder_worker:
  enabled: true
  version: "1.0"
  base_path: "/data"
  allowed_extensions: ["*"]  # 限制可訪問的副檔名
  max_file_size: "500MB"
  timeout: 30
  require_confirm: true      # 敏感操作確認
  operations:
    delete: true
    move: true
    create: true
```

### 3.3 GitHub Worker

| 屬性 | 值 |
|------|-----|
| **用途** | GitHub 集成 |
| **成本** | 低（API 免費額度） |
| **延遲** | 中等（網絡） |
| **依賴** | PyGithub、gitpython |

**職責**：
- 克隆/推送倉庫
- 提交管理
- Issue/PR 管理
- 代碼搜索和分析

**支持的操作**：
```python
{
    "clone": "克隆倉庫",
    "push": "推送更改",
    "pull": "拉取更改",
    "commit": "提交代碼",
    "create_issue": "建立 Issue",
    "create_pr": "建立 PR",
    "list_repos": "列表倉庫",
    "search_code": "搜索代碼",
    "delete_repo": "刪除倉庫（敏感）"
}
```

**敏感操作標記**：
```
delete_repo ✓ 需要確認
force_push ✓ 需要確認
delete_branch ✓ 需要確認
```

**配置示例**：
```yaml
github_worker:
  enabled: true
  version: "1.0"
  api_key: ${GITHUB_TOKEN}
  base_path: "/data/repos"
  max_repo_size: "1GB"
  timeout: 60
  require_confirm: true
  operations:
    delete_repo: true
    force_push: true
    delete_branch: true
```

---

## 4. Cloud Worker（雲服務集成）

### 4.1 AWS Worker

| 屬性 | 值 |
|------|-----|
| **用途** | AWS 服務集成 |
| **成本** | 中-高（按使用付費） |
| **延遲** | 中等 |
| **依賴** | boto3 |

**職責**：
- S3 文件上傳/下載
- 計算任務執行（Lambda）
- 數據存儲（DynamoDB）
- 日誌管理（CloudWatch）

**支持的操作**：
```python
{
    "s3_upload": "上傳文件到 S3",
    "s3_download": "從 S3 下載文件",
    "s3_delete": "刪除 S3 文件（敏感）",
    "lambda_invoke": "調用 Lambda 函數",
    "dynamodb_query": "查詢 DynamoDB",
    "cloudwatch_logs": "獲取日誌"
}
```

**敏感操作標記**：
```
s3_delete ✓ 需要確認
lambda_invoke ✓ 需要確認（成本）
```

**配置示例**：
```yaml
aws_worker:
  enabled: true
  version: "1.0"
  aws_access_key: ${AWS_ACCESS_KEY_ID}
  aws_secret_key: ${AWS_SECRET_ACCESS_KEY}
  region: "us-east-1"
  s3_bucket: "rip-platform-bucket"
  timeout: 60
  require_confirm: true
  cost_limit_per_month: 100  # 美元
```

### 4.2 Calendar Worker

| 屬性 | 值 |
|------|-----|
| **用途** | 日曆管理 |
| **成本** | 低 |
| **延遲** | 低 |
| **依賴** | google-auth、google-api-client |

**職責**：
- 日程查詢
- 事件創建/更新
- 提醒管理
- 日程衝突檢測

**支持的操作**：
```python
{
    "list_events": "列表日程事件",
    "create_event": "創建事件",
    "update_event": "更新事件",
    "delete_event": "刪除事件（敏感）",
    "get_free_slots": "查詢空閒時段",
    "check_conflicts": "檢查衝突"
}
```

**敏感操作標記**：
```
delete_event ✓ 需要確認
```

**配置示例**：
```yaml
calendar_worker:
  enabled: true
  version: "1.0"
  api_key: ${GOOGLE_CALENDAR_API_KEY}
  calendar_id: "primary"
  timezone: "Asia/Taipei"
  timeout: 30
  require_confirm: true
```

---

## 5. Worker 優先級矩陣

| Worker | 成本 | 速度 | 質量 | 並發度 | 用途 |
|--------|------|------|------|--------|------|
| **Claude** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 中等 | 高質量分析 |
| **GPT** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 中等 | 多模態處理 |
| **Gemini** | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 高 | 快速響應 |
| **PDF** | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | 高 | 文檔處理 |
| **Folder** | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 高 | 本地文件 |
| **GitHub** | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | 中等 | 代碼管理 |
| **AWS** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 中等 | 雲計算 |
| **Calendar** | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 高 | 日程管理 |

---

## 6. Worker 選擇邏輯

### 6.1 AI Worker 選擇規則

```
If 用戶指定特定 model:
    Use specified model
Else If 任務類型 == "code_generation":
    Prefer: Claude > GPT > Gemini
Else If 任務類型 == "visual_analysis":
    Prefer: GPT > Claude > Gemini
Else If 任務類型 == "fast_response":
    Prefer: Gemini > GPT > Claude
Else If 成本考慮 == "important":
    Prefer: Gemini > Claude > GPT
Else (Default):
    Prefer: Claude (balance)
```

### 6.2 Data Worker 選擇規則

```
If 目標 == "PDF":
    Use PDF Worker
Else If 目標 == "Local File":
    Use Folder Worker
Else If 目標 == "GitHub":
    Use GitHub Worker
Else If 目標 == "Multiple Sources":
    Chain workers (PDF → Claude → Folder)
```

---

## 7. Worker 生命周期

```
┌─────────────┐
│  INIT       │  - 初始化配置
│  (created)  │  - 連接外部服務
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  READY      │  - 健康檢查通過
│  (active)   │  - 等待請求
└──────┬──────┘
       │ 接收請求
       ▼
┌─────────────┐
│  PROCESSING │  - 執行任務
│  (busy)     │  - 暫不接收新請求
└──────┬──────┘
       │ 任務完成
       ▼
┌─────────────┐
│  READY      │  - 返回就緒狀態
│  (active)   │
└──────┬──────┘
       │ 错误 / 主动关闭
       ▼
┌─────────────┐
│  ERROR      │  - 記錄錯誤
│  (error)    │  - 嘗試恢復
└──────┬──────┘
       │
       ├─ 自動恢復成功 ──> READY
       │
       └─ 恢復失敗 ──────> DISABLED
                           (manual restart needed)
```

---

## 8. Worker 管理功能

### 8.1 動態註冊

```python
# 添加新 Worker
platform.register_worker(
    worker_class=CustomWorker,
    name="custom_worker",
    config={...}
)

# 註銷 Worker
platform.unregister_worker("custom_worker")
```

### 8.2 狀態監控

```python
# 獲取 Worker 狀態
status = platform.get_worker_status("claude_worker")

# 獲取所有 Worker 狀態
all_status = platform.get_all_workers_status()

# 健康檢查
health = platform.health_check_worker("github_worker")
```

### 8.3 配置更新

```python
# 熱更新配置（無需重啟）
platform.update_worker_config(
    "claude_worker",
    {"max_tokens": 8096}
)

# 重啟 Worker
platform.restart_worker("gpt_worker")
```

---

## 9. Worker 擴展指南

### 新增自定義 Worker 的步驟

1. **繼承基類**
   ```python
   from src.workers.base_worker import BaseWorker
   
   class CustomWorker(BaseWorker):
       ...
   ```

2. **實現必需方法**
   - `process()`
   - `validate()`
   - `health_check()`

3. **添加到配置**
   ```yaml
   custom_worker:
     enabled: true
     class_path: "src.workers.extension.custom_worker.CustomWorker"
   ```

4. **通過 Worker Manager 註冊**

5. **編寫測試**

6. **文檔化**
