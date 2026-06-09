# AI Router 設計 - 系統的大腦

## 1. AI Router 核心職責

```
┌─────────────────────────────────────────────┐
│         AI Router (The Brain)               │
│                                             │
│  1. 意圖識別 (Intent Detection)             │
│  2. 任務分解 (Task Decomposition)           │
│  3. 工作流編排 (Workflow Orchestration)     │
│  4. Worker 選擇 (Worker Selection)          │
│  5. 優先級管理 (Priority Management)        │
│  6. 上下文管理 (Context Management)         │
│  7. 結果聚合 (Result Aggregation)           │
│  8. 錯誤處理 (Error Handling)               │
│  9. 敏感操作確認 (Confirmation Handling)    │
│  10. 狀態追蹤 (State Tracking)              │
│                                             │
└─────────────────────────────────────────────┘
```

## 2. 意圖識別系統

### 2.1 意圖分類層級

```
用戶輸入
    │
    ▼
Pre-Processing
    • 文本清理
    • 去除特殊符號
    • 語言檢測
    │
    ▼
Intent Classification Engine
    │
    ├─ Intent: "text_generation"
    │  ├─ Sub-intent: "creative_writing"
    │  ├─ Sub-intent: "code_generation"
    │  └─ Sub-intent: "explanation"
    │
    ├─ Intent: "data_processing"
    │  ├─ Sub-intent: "pdf_analysis"
    │  ├─ Sub-intent: "file_management"
    │  └─ Sub-intent: "github_operation"
    │
    ├─ Intent: "information_retrieval"
    │  ├─ Sub-intent: "calendar_lookup"
    │  ├─ Sub-intent: "cloud_query"
    │  └─ Sub-intent: "local_search"
    │
    ├─ Intent: "multi_step_task"
    │  ├─ Sub-intent: "research"
    │  ├─ Sub-intent: "integration"
    │  └─ Sub-intent: "automation"
    │
    └─ Intent: "admin_operation"
       ├─ Sub-intent: "system_config"
       ├─ Sub-intent: "worker_management"
       └─ Sub-intent: "sensitive_operation"
    │
    ▼
Confidence Score & Priority
    • 高信心 (>0.9)
    • 中信心 (0.7-0.9)
    • 低信心 (<0.7)
```

### 2.2 意圖識別方法 (多層次)

```python
class IntentDetector:
    
    def detect_intent(self, user_input: str) -> Intent:
        # 1. 關鍵字匹配 (最快)
        if match := self._keyword_match(user_input):
            return match
        
        # 2. 規則引擎 (快速)
        if match := self._rule_engine(user_input):
            return match
        
        # 3. 向量相似度 (中等)
        if match := self._vector_similarity(user_input):
            return match
        
        # 4. LLM 分類 (最準確但慢)
        return self._llm_classification(user_input)
```

### 2.3 意圖示例

```
User: "幫我分析 reports.pdf 並生成摘要"
Output:
{
    "primary_intent": "data_processing",
    "sub_intent": "pdf_analysis",
    "entity": "reports.pdf",
    "action": "analyze_and_summarize",
    "required_workers": ["pdf_worker", "claude_worker"],
    "priority": "high",
    "confidence": 0.95,
    "sensitive": false
}

---

User: "刪除我 GitHub 上的 repo"
Output:
{
    "primary_intent": "admin_operation",
    "sub_intent": "sensitive_operation",
    "entity": "github_repo",
    "action": "delete",
    "required_workers": ["github_worker"],
    "priority": "high",
    "confidence": 0.98,
    "sensitive": true,              # ⚠️ 需要確認
    "confirmation_required": true
}
```

---

## 3. 任務分解系統

### 3.1 任務分解邏輯

```
Intent Analysis
    │
    ▼
Task Decomposition Engine
    │
    ├─ Single Step Task
    │  ├─ No dependencies
    │  └─ Direct execution
    │
    ├─ Multi-Step Task (Sequential)
    │  ├─ Step 1: PDF Analysis
    │  ├─ Step 2: Claude Review (depends on Step 1)
    │  ├─ Step 3: Report Generation (depends on Step 2)
    │  └─ Step 4: Upload (depends on Step 3)
    │
    ├─ Parallel Tasks
    │  ├─ Task A (independent)
    │  ├─ Task B (independent)
    │  └─ Task C (depends on A & B)
    │
    └─ Complex DAG (Directed Acyclic Graph)
       ├─ Multiple dependencies
       ├─ Conditional branching
       └─ Loop handling
```

### 3.2 任務結構

```python
@dataclass
class Task:
    id: str                          # 任務 ID
    worker: str                      # 執行的 Worker 名稱
    action: str                      # 操作類型
    payload: dict                    # 輸入數據
    priority: str                    # 優先級
    timeout: int                     # 超時時間（秒）
    require_confirmation: bool       # 是否需要確認
    dependencies: List[str]          # 依賴的任務 ID
    condition: Optional[Callable]    # 條件函數
    retry_policy: RetryPolicy        # 重試策略
    metadata: dict                   # 元數據
```

### 3.3 分解示例

```
User: "分析 GitHub repo 代碼質量並生成報告保存到 S3"

Decomposed Tasks:
{
    "workflow_id": "wf_abc123",
    "tasks": [
        {
            "id": "t1",
            "worker": "github_worker",
            "action": "clone_repo",
            "payload": {"repo_url": "..."},
            "dependencies": [],
            "priority": "high",
            "timeout": 120
        },
        {
            "id": "t2",
            "worker": "claude_worker",
            "action": "analyze_code",
            "payload": {"code_path": "..."},
            "dependencies": ["t1"],  # 依賴 t1 完成
            "priority": "high",
            "timeout": 180
        },
        {
            "id": "t3",
            "worker": "pdf_worker",
            "action": "generate_report",
            "payload": {"analysis_result": "${t2.output}"},
            "dependencies": ["t2"],
            "priority": "high",
            "timeout": 60
        },
        {
            "id": "t4",
            "worker": "aws_worker",
            "action": "s3_upload",
            "payload": {"file": "${t3.output}", "bucket": "..."},
            "dependencies": ["t3"],
            "priority": "high",
            "timeout": 30,
            "require_confirmation": true  # 敏感操作
        }
    ]
}
```

---

## 4. Worker 選擇引擎

### 4.1 選擇策略

```
Request
    │
    ▼
Worker Selector
    │
    ├─ [Strategy 1] User Specified
    │  └─ Use user's preferred worker
    │
    ├─ [Strategy 2] Context-Based
    │  ├─ Historical performance
    │  ├─ User preference
    │  └─ Recent success rate
    │
    ├─ [Strategy 3] Cost Optimization
    │  ├─ Task complexity
    │  ├─ API pricing
    │  └─ Budget constraints
    │
    ├─ [Strategy 4] Quality Optimization
    │  ├─ Task accuracy requirements
    │  ├─ Worker quality score
    │  └─ Success rate
    │
    ├─ [Strategy 5] Performance Optimization
    │  ├─ Task latency requirements
    │  ├─ Worker response time
    │  └─ Current load
    │
    └─ [Strategy 6] Hybrid (Weighted)
       ├─ Cost weight
       ├─ Quality weight
       ├─ Performance weight
       └─ Availability weight
    │
    ▼
Final Decision
    └─ Selected Worker + Alternatives (fallback)
```

### 4.2 選擇器實現框架

```python
class WorkerSelector:
    
    async def select(
        self,
        intent: Intent,
        context: ExecutionContext
    ) -> WorkerSelection:
        """
        Returns: {
            "primary": "claude_worker",
            "alternatives": ["gpt_worker", "gemini_worker"],
            "reason": "Best quality for code analysis",
            "confidence": 0.95
        }
        """
        
        # 1. 檢查用戶指定
        if user_preference := context.user_preference:
            return self._user_specified(user_preference)
        
        # 2. 檢查上下文
        if context_hint := context.get_hint():
            return self._context_based(intent, context_hint)
        
        # 3. 計算評分
        scores = await self._calculate_scores(intent, context)
        
        # 4. 排序並返回
        return self._rank_and_return(scores)
    
    async def _calculate_scores(
        self,
        intent: Intent,
        context: ExecutionContext
    ) -> Dict[str, float]:
        """計算每個 Worker 的綜合評分"""
        scores = {}
        for worker in self.available_workers:
            scores[worker.name] = (
                self.quality_weight * worker.quality_score +
                self.cost_weight * (1 - worker.cost_score) +
                self.performance_weight * worker.speed_score +
                self.availability_weight * worker.availability_score
            )
        return scores
```

---

## 5. 優先級和資源管理

### 5.1 優先級系統

```
┌─────────────────────────┐
│   Priority Queue        │
│                         │
│ ⭐⭐⭐⭐⭐  CRITICAL     │
│  • System errors        │
│  • User confirmations   │
│                         │
│ ⭐⭐⭐⭐   HIGH         │
│  • Sensitive operations │
│  • User interactions    │
│                         │
│ ⭐⭐⭐     NORMAL       │
│  • Regular tasks        │
│  • User requests        │
│                         │
│ ⭐⭐       LOW          │
│  • Background tasks     │
│  • Maintenance jobs     │
│                         │
│ ⭐         DEFERRED     │
│  • Low priority ops     │
│  • Future scheduling    │
│                         │
└─────────────────────────┘
```

### 5.2 資源分配

```python
class ResourceAllocator:
    
    # 基於優先級的資源分配
    RESOURCE_LIMITS = {
        "CRITICAL": {"concurrent": 10, "timeout": 600},
        "HIGH": {"concurrent": 5, "timeout": 300},
        "NORMAL": {"concurrent": 3, "timeout": 120},
        "LOW": {"concurrent": 1, "timeout": 60},
    }
    
    async def allocate(
        self,
        task: Task
    ) -> ResourceAllocation:
        """分配執行資源"""
        limits = self.RESOURCE_LIMITS[task.priority]
        
        # 等待可用資源
        await self._wait_for_capacity(
            limits["concurrent"]
        )
        
        return ResourceAllocation(
            timeout=limits["timeout"],
            max_retries=self._get_retry_count(task.priority),
            resource_id=self._allocate_id()
        )
```

---

## 6. 上下文管理

### 6.1 上下文結構

```python
@dataclass
class ExecutionContext:
    # 用戶信息
    user_id: str
    session_id: str
    
    # 請求信息
    request_id: str
    timestamp: datetime
    
    # 狀態追蹤
    workflow_id: str
    current_step: int
    completed_steps: List[str]
    
    # 數據存儲
    variables: Dict[str, Any]        # ${var} 引用
    previous_outputs: Dict[str, Any] # 上一步結果
    
    # 用戶偏好
    user_preference: Dict[str, Any]
    
    # 操作歷史
    operation_history: List[Operation]
    
    # 安全信息
    confirmation_pending: bool
    confirmed_operations: List[str]
```

### 6.2 變數引用系統

```
Task payload 中可以引用前面任務的輸出：

{
    "id": "t3",
    "worker": "pdf_worker",
    "payload": {
        "content": "${t2.output}",      # 引用 t2 的輸出
        "mode": "${context.mode}",       # 引用上下文變量
        "user": "${user_id}"             # 引用用戶信息
    }
}

Runtime 會自動替換這些引用。
```

---

## 7. 敏感操作確認流程

### 7.1 確認流程圖

```
Task with require_confirmation=true
        │
        ▼
Router detects sensitive operation
        │
        ▼
Generate confirmation message
        │
        ├─ Show operation details
        ├─ Show consequences
        └─ Request user approval
        │
        ▼
Send to LINE Gateway
        │
        ├─ User responds "是"    ──> Mark as confirmed
        │                              │
        │                              ▼
        │                        Execute task
        │                              │
        │                              ▼
        │                        Send result
        │
        └─ User responds "否"    ──> Task aborted
                                      │
                                      ▼
                                Notify user
```

### 7.2 確認消息示例

```
⚠️ 敏感操作確認

操作: 刪除 GitHub 倉庫
倉庫: rex-intelligence-platform
無法撤銷: 是

確認刪除？(輸入 "確認" 或 "取消")

---

如果用戶回復 "確認":
Router 標記操作為已確認，執行刪除
如果用戶回復 "取消":
Router 放棄操作，返回用戶提示
```

---

## 8. 結果聚合

### 8.1 聚合策略

```python
class ResultAggregator:
    
    async def aggregate(
        self,
        task_results: Dict[str, TaskResult],
        workflow_structure: WorkflowDAG
    ) -> AggregatedResult:
        """
        聚合所有任務結果
        """
        
        if len(task_results) == 1:
            # 單任務：直接返回
            return self._single_result(task_results)
        
        elif self._is_sequential(workflow_structure):
            # 順序執行：最後一步的結果
            return self._last_result(task_results)
        
        elif self._is_parallel(workflow_structure):
            # 並行執行：合並結果
            return self._merge_results(task_results)
        
        else:
            # 複雜 DAG：結構化聚合
            return self._dag_aggregation(task_results, workflow_structure)
```

### 8.2 聚合格式

```
Single Task Result:
{
    "status": "success",
    "data": "...",
    "worker": "claude_worker",
    "execution_time": 2.5,
    "cost": 0.05
}

Multi-Task Result:
{
    "status": "success",
    "workflow_id": "wf_abc123",
    "results": [
        {"task_id": "t1", "status": "success", "data": "..."},
        {"task_id": "t2", "status": "success", "data": "..."},
        {"task_id": "t3", "status": "success", "data": "..."},
    ],
    "total_time": 15.3,
    "total_cost": 0.25,
    "summary": "All tasks completed successfully"
}

Failed Result:
{
    "status": "failed",
    "failed_task": "t2",
    "error": "Timeout exceeded",
    "attempted_retries": 3,
    "last_error_time": "2024-06-09T10:30:45Z"
}
```

---

## 9. 錯誤處理和重試

### 9.1 重試策略

```python
class RetryPolicy:
    """
    重試策略定義
    """
    max_attempts: int = 3
    initial_delay: float = 1.0      # 秒
    backoff_multiplier: float = 2.0
    max_delay: float = 60.0
    
    # 應該重試的錯誤類型
    retryable_errors = {
        "TimeoutError",
        "ConnectionError",
        "RateLimitError",
    }
    
    # 不應該重試的錯誤
    non_retryable_errors = {
        "InvalidRequest",
        "AuthenticationError",
        "NotFoundError",
    }
```

### 9.2 熔斷器 (Circuit Breaker)

```
State: CLOSED (正常)
    └─ 請求通過
       ├─ 成功 -> 保持 CLOSED
       └─ 失敗計數達到閾值 -> 轉到 OPEN

State: OPEN (熔斷)
    └─ 拒絕所有請求
       └─ 等待超時 -> 轉到 HALF_OPEN

State: HALF_OPEN (測試)
    └─ 允許部分請求測試
       ├─ 成功 -> 轉到 CLOSED
       └─ 失敗 -> 轉到 OPEN
```

---

## 10. 監控和追蹤

### 10.1 追蹤信息

```python
@dataclass
class ExecutionTrace:
    trace_id: str                    # 追蹤 ID
    workflow_id: str                 # 工作流 ID
    
    # 時間戳
    start_time: datetime
    end_time: datetime
    
    # 執行步驟
    steps: List[StepTrace]
    
    # 性能指標
    total_duration: float
    task_durations: Dict[str, float]
    
    # 資源消耗
    api_calls: List[APICall]
    estimated_cost: float
    
    # 錯誤追蹤
    errors: List[ErrorRecord]
    warnings: List[WarningRecord]
```

### 10.2 查詢追蹤

```
用戶可以查詢執行歷史：

/trace/<trace_id>           - 查詢特定追蹤
/trace/workflow/<wf_id>     - 查詢工作流所有追蹤
/trace/user/<user_id>       - 查詢用戶所有追蹤
/cost/user/<user_id>        - 查詢用戶成本統計
```

---

## 11. Router 配置示例

```yaml
ai_router:
  enabled: true
  version: "1.0"
  
  # 意圖檢測
  intent_detection:
    method: "hybrid"          # keyword, rules, vector, llm, hybrid
    confidence_threshold: 0.7
    fallback_intent: "help"
  
  # 任務分解
  task_decomposition:
    max_depth: 10
    timeout: 300
  
  # Worker 選擇
  worker_selection:
    strategy: "hybrid"        # user, context, cost, quality, performance, hybrid
    quality_weight: 0.4
    cost_weight: 0.3
    performance_weight: 0.2
    availability_weight: 0.1
  
  # 優先級管理
  priority_management:
    default_priority: "normal"
    queue_size: 1000
    resource_limits:
      critical:
        concurrent: 10
        timeout: 600
      high:
        concurrent: 5
        timeout: 300
      normal:
        concurrent: 3
        timeout: 120
      low:
        concurrent: 1
        timeout: 60
  
  # 錯誤處理
  error_handling:
    retry_policy:
      max_attempts: 3
      backoff: "exponential"
      initial_delay: 1
      max_delay: 60
    
    circuit_breaker:
      enabled: true
      failure_threshold: 5
      success_threshold: 2
      timeout: 60
  
  # 敏感操作
  sensitive_operations:
    require_confirmation: true
    confirmation_timeout: 300
    operations:
      - "delete"
      - "move"
      - "override"
      - "uninstall"
```

---

## 12. Router 核心接口

```python
class AIRouter:
    
    async def route(
        self,
        message: Message
    ) -> Response:
        """主路由方法"""
        
        # 1. 意圖識別
        intent = await self.intent_detector.detect(message.content)
        
        # 2. 任務分解
        tasks = await self.task_decomposer.decompose(intent)
        
        # 3. 檢查敏感操作
        if any(t.require_confirmation for t in tasks):
            return await self._handle_confirmation(tasks, message)
        
        # 4. 執行工作流
        results = await self._execute_workflow(tasks, message)
        
        # 5. 聚合結果
        return await self.result_aggregator.aggregate(results)
    
    async def confirm(
        self,
        user_id: str,
        confirmation: bool,
        original_request_id: str
    ) -> Response:
        """處理用戶確認"""
        if confirmation:
            tasks = self._get_pending_tasks(original_request_id)
            return await self._execute_workflow(tasks)
        else:
            return Response(status="aborted")
```

---

## 關鍵設計特點

✅ **智能決策**：多層次意圖識別，確保準確理解用戶需求  
✅ **靈活執行**：支持單步、順序、並行、複雜 DAG 工作流  
✅ **優化選擇**：多策略 Worker 選擇，支持成本/質量/性能權衡  
✅ **安全確認**：敏感操作自動確認，防止誤操作  
✅ **完整追蹤**：全程執行追蹤，便於調試和成本統計  
✅ **可靠性**：重試機制、熔斷器、錯誤處理完備
