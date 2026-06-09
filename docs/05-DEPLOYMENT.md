# 部署架構設計

## 1. 部署環境設計

### 1.1 多環境架構

```
┌─────────────────────────────────────────────────────────────┐
│                     Development                              │
│  • Local Docker Compose                                      │
│  • SQLite / Redis (in-memory)                                │
│  • Mock External APIs                                        │
│  • Logging to console                                        │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                     Staging                                  │
│  • Docker Compose on VM                                      │
│  • PostgreSQL + Redis                                        │
│  • Real External APIs (limited usage)                        │
│  • Centralized logging                                       │
│  • Monitoring (Prometheus)                                   │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                     Production                               │
│  • Kubernetes Cluster                                        │
│  • RDS + ElastiCache                                         │
│  • Real External APIs (full)                                 │
│  • ELK Stack (Elasticsearch, Logstash, Kibana)              │
│  • Full monitoring & alerting                                │
│  • Multi-region replication                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 開發環境 - Docker Compose

### 2.1 docker-compose.yml 結構

```yaml
version: '3.8'

services:
  # Gateway 層
  rip-gateway:
    build: ./docker/gateway
    ports:
      - "8000:8000"
    environment:
      - LOG_LEVEL=DEBUG
      - ROUTER_URL=http://rip-router:8001
    depends_on:
      - rip-router
    networks:
      - rip-network
    volumes:
      - ./logs:/app/logs

  # Router 層
  rip-router:
    build: ./docker/router
    ports:
      - "8001:8001"
    environment:
      - LOG_LEVEL=DEBUG
      - REDIS_URL=redis://redis:6379/0
      - DB_URL=postgresql://postgres:password@postgres:5432/rip_dev
      - WORKER_REGISTRY_URL=http://rip-worker-registry:8002
    depends_on:
      - redis
      - postgres
      - rip-worker-registry
    networks:
      - rip-network
    volumes:
      - ./logs:/app/logs

  # Worker Registry（可選，用於動態註冊）
  rip-worker-registry:
    build: ./docker/worker-registry
    ports:
      - "8002:8002"
    environment:
      - LOG_LEVEL=DEBUG
    networks:
      - rip-network
    volumes:
      - ./logs:/app/logs

  # AI Workers
  rip-worker-ai:
    build: ./docker/workers/ai
    environment:
      - LOG_LEVEL=DEBUG
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - ROUTER_URL=http://rip-router:8001
    depends_on:
      - redis
    networks:
      - rip-network
    volumes:
      - ./logs:/app/logs

  # Data Workers
  rip-worker-data:
    build: ./docker/workers/data
    environment:
      - LOG_LEVEL=DEBUG
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - ROUTER_URL=http://rip-router:8001
    depends_on:
      - redis
    networks:
      - rip-network
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs

  # Cloud Workers
  rip-worker-cloud:
    build: ./docker/workers/cloud
    environment:
      - LOG_LEVEL=DEBUG
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - GOOGLE_CALENDAR_API_KEY=${GOOGLE_CALENDAR_API_KEY}
      - ROUTER_URL=http://rip-router:8001
    depends_on:
      - redis
    networks:
      - rip-network
    volumes:
      - ./logs:/app/logs

  # Redis - 用於消息隊列和緩存
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - rip-network
    volumes:
      - redis-data:/data

  # PostgreSQL - 用於持久化存儲
  postgres:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=rip_dev
    networks:
      - rip-network
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql

  # 監控 - Prometheus（可選）
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    networks:
      - rip-network
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  # 可視化 - Grafana（可選）
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana
    networks:
      - rip-network
    depends_on:
      - prometheus

networks:
  rip-network:
    driver: bridge

volumes:
  redis-data:
  postgres-data:
  prometheus-data:
  grafana-data:
```

### 2.2 環境文件 (.env.example)

```bash
# ===== Application =====
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DEBUG=true

# ===== Gateway =====
GATEWAY_PORT=8000
GATEWAY_HOST=0.0.0.0
LINE_CHANNEL_ID=${LINE_CHANNEL_ID}
LINE_CHANNEL_SECRET=${LINE_CHANNEL_SECRET}
LINE_ACCESS_TOKEN=${LINE_ACCESS_TOKEN}

# ===== Router =====
ROUTER_PORT=8001
ROUTER_HOST=0.0.0.0

# ===== Database =====
DB_HOST=postgres
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=rip_dev
DB_URL=postgresql://postgres:password@postgres:5432/rip_dev

# ===== Redis =====
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_URL=redis://redis:6379/0

# ===== API Keys =====
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxx
GOOGLE_API_KEY=xxxxxxxx
GOOGLE_CALENDAR_API_KEY=xxxxxxxx
GITHUB_TOKEN=ghp_xxxxxxxx

# ===== AWS =====
AWS_ACCESS_KEY_ID=AKIAXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxx
AWS_REGION=us-east-1
AWS_S3_BUCKET=rip-platform-bucket

# ===== Security =====
JWT_SECRET=your-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here

# ===== Monitoring =====
PROMETHEUS_ENABLED=true
GRAFANA_ADMIN_PASSWORD=admin

# ===== Worker Configuration =====
WORKER_TIMEOUT=120
WORKER_MAX_RETRIES=3
WORKER_REGISTRY_URL=http://rip-worker-registry:8002

# ===== Feature Flags =====
ENABLE_RAG=false
ENABLE_MCP=false
ENABLE_AGENT=false
ENABLE_TASK_QUEUE=false
```

---

## 3. 容器鏡像設計

### 3.1 Dockerfile 模板 - Gateway

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製源代碼
COPY src/gateway ./src/gateway
COPY src/utils ./src/utils
COPY config ./config

# 環境變量
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# 啟動
CMD ["python", "-m", "src.gateway.main"]
```

### 3.2 Dockerfile 模板 - Router

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/core ./src/core
COPY src/utils ./src/utils
COPY config ./config

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8001/health')"

CMD ["python", "-m", "src.core.main"]
```

### 3.3 Dockerfile 模板 - Worker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/workers ./src/workers
COPY src/utils ./src/utils
COPY config ./config

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV WORKER_NAME=worker

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health')"

CMD ["python", "-m", "src.workers.main"]
```

---

## 4. 生產環境 - Kubernetes

### 4.1 Kubernetes 架構

```
Kubernetes Cluster
│
├─ Namespace: rip-production
│
├─ Deployments:
│  ├─ rip-gateway (replicas: 3, autoscale: 3-10)
│  ├─ rip-router (replicas: 3, autoscale: 3-15)
│  ├─ rip-worker-ai (replicas: 5, autoscale: 5-20)
│  ├─ rip-worker-data (replicas: 3, autoscale: 3-10)
│  └─ rip-worker-cloud (replicas: 3, autoscale: 3-10)
│
├─ Services:
│  ├─ rip-gateway-svc (LoadBalancer)
│  ├─ rip-router-svc (ClusterIP)
│  ├─ rip-worker-ai-svc (ClusterIP)
│  ├─ rip-worker-data-svc (ClusterIP)
│  └─ rip-worker-cloud-svc (ClusterIP)
│
├─ StatefulSets:
│  ├─ redis-cluster (replicas: 3)
│  └─ postgres (replicas: 1, with persistent volume)
│
├─ ConfigMaps:
│  └─ rip-config
│
├─ Secrets:
│  └─ rip-secrets (API keys, credentials)
│
├─ Ingress:
│  ├─ API Gateway
│  ├─ Monitoring (Prometheus, Grafana)
│  └─ Logging (Kibana)
│
└─ Jobs/CronJobs:
   ├─ Database migrations
   ├─ Cache cleanup
   └─ Backup jobs
```

### 4.2 Kubernetes Deployment 示例 - Gateway

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rip-gateway
  namespace: rip-production
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: rip-gateway
  template:
    metadata:
      labels:
        app: rip-gateway
    spec:
      containers:
      - name: gateway
        image: registry.example.com/rip/gateway:v1.0.0
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
          name: http
        
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: LOG_LEVEL
          value: "INFO"
        - name: ROUTER_URL
          value: "http://rip-router-svc:8001"
        - name: LINE_ACCESS_TOKEN
          valueFrom:
            secretKeyRef:
              name: rip-secrets
              key: line-access-token
        
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10

---
apiVersion: v1
kind: Service
metadata:
  name: rip-gateway-svc
  namespace: rip-production
spec:
  type: LoadBalancer
  selector:
    app: rip-gateway
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: rip-gateway-hpa
  namespace: rip-production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: rip-gateway
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

## 5. 部署流程

### 5.1 開發環境部署

```bash
# 1. 克隆項目
git clone https://github.com/xxx/rex-intelligence-platform.git
cd rex-intelligence-platform

# 2. 複製環境配置
cp .env.example .env
# 編輯 .env 文件，添加必要的 API Key

# 3. 啟動 Docker Compose
docker-compose up -d

# 4. 驗證服務
docker-compose ps
curl http://localhost:8000/health

# 5. 查看日誌
docker-compose logs -f rip-router
```

### 5.2 生產環境部署

```bash
# 1. 構建鏡像
docker build -t registry.example.com/rip/gateway:v1.0.0 -f docker/gateway/Dockerfile .
docker build -t registry.example.com/rip/router:v1.0.0 -f docker/router/Dockerfile .
docker build -t registry.example.com/rip/worker-ai:v1.0.0 -f docker/workers/ai/Dockerfile .

# 2. 推送到 Registry
docker push registry.example.com/rip/gateway:v1.0.0
docker push registry.example.com/rip/router:v1.0.0
docker push registry.example.com/rip/worker-ai:v1.0.0

# 3. 部署到 Kubernetes
kubectl create namespace rip-production
kubectl apply -f k8s/secrets.yaml -n rip-production
kubectl apply -f k8s/configmap.yaml -n rip-production
kubectl apply -f k8s/deployments/ -n rip-production

# 4. 驗證部署
kubectl get pods -n rip-production
kubectl get svc -n rip-production

# 5. 監控日誌
kubectl logs -f deployment/rip-gateway -n rip-production
```

---

## 6. 數據庫架構

### 6.1 PostgreSQL Schema

```sql
-- 用戶表
CREATE TABLE users (
    id UUID PRIMARY KEY,
    line_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 會話表
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    context JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- 執行追蹤表
CREATE TABLE execution_traces (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    workflow_id VARCHAR(255),
    status VARCHAR(50),
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    duration_seconds FLOAT,
    estimated_cost DECIMAL(10, 2),
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 任務日誌表
CREATE TABLE task_logs (
    id UUID PRIMARY KEY,
    trace_id UUID REFERENCES execution_traces(id),
    task_id VARCHAR(255),
    worker_name VARCHAR(255),
    status VARCHAR(50),
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    duration_seconds FLOAT,
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Worker 狀態表
CREATE TABLE worker_status (
    id UUID PRIMARY KEY,
    worker_name VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50),
    last_heartbeat TIMESTAMP,
    error_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    metadata JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- API 調用成本表
CREATE TABLE api_costs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    trace_id UUID REFERENCES execution_traces(id),
    api_provider VARCHAR(255),
    model_name VARCHAR(255),
    input_tokens INT,
    output_tokens INT,
    cost DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_users_line_id ON users(line_id);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_execution_traces_user_id ON execution_traces(user_id);
CREATE INDEX idx_task_logs_trace_id ON task_logs(trace_id);
CREATE INDEX idx_api_costs_user_id ON api_costs(user_id);
```

### 6.2 Redis 架構

```
Redis Key Patterns:

用戶會話:
  session:{user_id} -> SessionData (TTL: 24 hours)

執行隊列:
  queue:critical -> List of high-priority tasks
  queue:high -> List of high-priority tasks
  queue:normal -> List of normal tasks
  queue:low -> List of low-priority tasks

Worker 狀態:
  worker:{worker_name}:status -> WorkerStatus
  worker:{worker_name}:metrics -> Performance metrics

緩存:
  cache:{key} -> Cached data (configurable TTL)

消息:
  channel:{user_id}:notifications -> Pub/Sub channel
```

---

## 7. 部署檢查清單

### 7.1 部署前檢查

- [ ] 所有依賴項已安裝
- [ ] 環境變量已配置
- [ ] 數據庫已初始化
- [ ] API Key 已驗證
- [ ] 日誌目錄已創建
- [ ] SSL 證書已準備（生產）
- [ ] 備份策略已實施
- [ ] 監控告警已配置

### 7.2 部署後驗證

- [ ] 所有服務健康檢查通過
- [ ] Gateway 可以接收消息
- [ ] Router 可以路由任務
- [ ] Workers 可以執行任務
- [ ] 數據庫連接正常
- [ ] Redis 連接正常
- [ ] 監控指標正確顯示
- [ ] 日誌正確記錄

### 7.3 故障恢復

```
如果 Gateway 故障:
  1. 檢查日誌：docker logs rip-gateway
  2. 重啟服務：docker-compose restart rip-gateway
  3. 檢查依賴：redis, postgres, router

如果 Router 故障:
  1. 檢查日誌：docker logs rip-router
  2. 檢查數據庫連接
  3. 重啟服務：docker-compose restart rip-router

如果 Worker 故障:
  1. 檢查日誌：docker logs rip-worker-ai
  2. 檢查 API Key 配置
  3. 檢查速率限制
  4. 重啟服務：docker-compose restart rip-worker-ai
```

---

## 8. 備份和恢復

### 8.1 數據庫備份

```bash
# 每日自動備份
0 2 * * * pg_dump -U postgres rip_prod > /backup/rip_$(date +\%Y\%m\%d).sql

# 手動備份
pg_dump -U postgres rip_prod > rip_backup.sql

# 恢復
psql -U postgres rip_prod < rip_backup.sql
```

### 8.2 配置備份

```bash
# 備份配置文件
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  .env config/ k8s/secrets.yaml

# 備份 Docker 鏡像
docker save -o rip_images_$(date +%Y%m%d).tar \
  registry.example.com/rip/gateway:v1.0.0 \
  registry.example.com/rip/router:v1.0.0
```

---

## 9. 性能優化建議

1. **API 請求優化**
   - 使用批量請求減少 API 調用
   - 實現請求去重和緩存

2. **數據庫優化**
   - 定期分析和清理舊數據
   - 使用數據分區進行大型表的查詢優化

3. **緩存策略**
   - Redis 用於熱數據
   - CDN 用於靜態資源

4. **異步處理**
   - 使用消息隊列進行耗時操作
   - 非阻塞 I/O 操作

5. **監控告警**
   - CPU、內存、磁盤使用率
   - API 響應時間
   - 錯誤率

---

## 關鍵設計特點

✅ **多環境支持**：開發、測試、生產完整配置  
✅ **容器化**：Docker 和 Kubernetes 完全支持  
✅ **可擴展**：自動伸縮，負載均衡  
✅ **高可用**：多副本，故障轉移  
✅ **監控完善**：Prometheus、Grafana、ELK Stack  
✅ **備份恢復**：完整的備份和恢復策略
