# 貢獻指南

感謝你對 Rex Intelligence Platform (RIP) 的興趣！本文檔將幫助你如何貢獻代碼、報告問題、建議功能等。

## 🤝 貢獻方式

### 1. 報告 Bug

如果你發現了 bug，請創建一個 Issue：

**提供以下信息**：
- 系統環境（OS、Python 版本、Docker 版本）
- 重現步驟
- 預期行為
- 實際行為
- 相關日誌

**Issue 模板**：
```markdown
## 描述
清楚簡潔地描述 bug。

## 重現步驟
1. ...
2. ...
3. ...

## 預期行為
應該發生什麼

## 實際行為
實際發生了什麼

## 環境
- OS: 
- Python: 
- Docker: 

## 日誌
```
错误日志片段
```
```

### 2. 建議功能

提交功能建議：

**提供以下信息**：
- 功能的清晰描述
- 使用場景
- 可能的實現方法
- 預期好處

**Feature 模板**：
```markdown
## 功能描述
清楚描述你想要的功能。

## 使用場景
什麼情況下需要這個功能？

## 可能的實現
你有何種實現想法？

## 額外內容
其他相關資訊
```

### 3. 提交代碼

我們歡迎 Pull Requests！

#### 開發工作流

```bash
# 1. Fork 項目
git clone https://github.com/YOUR_USERNAME/rex-intelligence-platform.git
cd rex-intelligence-platform

# 2. 創建開發分支
git checkout -b feature/my-feature

# 3. 設置開發環境
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"

# 4. 進行開發
# 編寫代碼
vim src/my_feature.py

# 5. 運行測試
pytest tests/

# 6. 代碼檢查
black src/
isort src/
flake8 src/
mypy src/

# 7. 提交代碼
git add .
git commit -m "feat: add my feature"

# 8. 推送到分支
git push origin feature/my-feature

# 9. 創建 Pull Request
```

#### 代碼風格指南

我們遵循 PEP 8 和以下約定：

**Python 代碼風格**：
```python
# 使用 black 格式化 (line length: 100)
def my_function(param1: str, param2: int) -> bool:
    """
    函數簡短描述。
    
    詳細描述（如果需要）。
    
    Args:
        param1: 參數1描述
        param2: 參數2描述
    
    Returns:
        返回值描述
    
    Raises:
        ValueError: 異常描述
    """
    return True
```

**Imports 組織**：
```python
# 標準庫
import os
import sys
from datetime import datetime

# 第三方庫
import fastapi
import pydantic
from loguru import logger

# 本地模塊
from src.core import router
from src.utils import logger as custom_logger
```

**Type Hints**：
```python
from typing import Optional, List, Dict, Any

def process_data(
    data: List[Dict[str, Any]],
    max_retries: int = 3
) -> Optional[str]:
    """Always use type hints."""
    pass
```

**文檔字符串**：
```python
def my_function():
    """
    一行簡短描述。
    
    更詳細的描述（如果需要多行）。
    可以提供更多上下文和使用示例。
    
    Args:
        param: 描述
    
    Returns:
        返回值描述
    
    Raises:
        CustomError: 何時拋出
    
    Example:
        >>> result = my_function()
        >>> print(result)
    """
    pass
```

#### 測試要求

- 所有新功能必須有對應的測試
- 測試覆蓋率必須 >80%
- 編寫單元測試和集成測試

**測試模板**：
```python
import pytest
from unittest.mock import Mock, patch

class TestMyFeature:
    """我的功能的測試套件。"""
    
    @pytest.fixture
    def setup(self):
        """設置測試夾具。"""
        # 初始化
        yield
        # 清理
    
    def test_basic_functionality(self, setup):
        """測試基本功能。"""
        result = my_function()
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """測試異步功能。"""
        result = await async_function()
        assert result == expected
    
    def test_error_handling(self):
        """測試錯誤處理。"""
        with pytest.raises(ValueError):
            my_function(invalid_param)
```

#### Commit 消息規範

使用 Conventional Commits 格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**：
- `feat`: 新功能
- `fix`: Bug 修復
- `docs`: 文檔更新
- `style`: 代碼格式（不影響功能）
- `refactor`: 代碼重構
- `perf`: 性能改進
- `test`: 測試相關
- `chore`: 構建工具、依賴等

**Examples**：
```
feat(router): add support for conditional workflows

Implement conditional branching in AI Router to support
if/else logic in multi-step tasks.

Closes #123

---

fix(claude-worker): handle timeout errors correctly

Update Claude Worker to properly handle API timeouts
and implement exponential backoff retry strategy.

Closes #456

---

docs: update installation instructions

Add Docker Compose examples and troubleshooting guide.
```

### 4. 改進文檔

文檔同樣重要！

- 改進現有文檔
- 添加使用示例
- 修復文檔中的錯誤
- 翻譯文檔

## 📋 開發檢查清單

在提交 PR 之前，請確保：

- [ ] 代碼遵循風格指南 (black, isort, flake8)
- [ ] 添加了類型提示 (mypy passes)
- [ ] 編寫了測試
- [ ] 測試覆蓋率 >80%
- [ ] 所有現有測試通過
- [ ] 更新了相關文檔
- [ ] 更新了 CHANGELOG
- [ ] Commit 消息清晰且遵循規範
- [ ] 沒有添加沒必要的依賴

## 🔄 審查流程

1. **自動檢查**
   - GitHub Actions 運行測試
   - 代碼質量檢查
   - 安全掃描

2. **代碼審查**
   - 至少一個維護者審查
   - 確保代碼質量和設計

3. **合併**
   - 如果審查通過且 CI 成功
   - 使用 squash merge 保持歷史整潔

## 🎯 優先事項

我們特別歡迎以下方面的貢獻：

### 高優先級
- 核心 Worker 的改進
- Router 性能優化
- 安全性改進
- 文檔改進

### 中優先級
- 新的集成（新 Worker）
- 功能增強
- 測試改進
- 示例代碼

### 低優先級
- UI/UX 改進
- 配置選項
- 日誌格式化

## 📚 開發資源

### 本地開發

```bash
# 設置開發環境
git clone <repo>
cd rex-intelligence-platform
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 啟動 Docker 服務
docker-compose up -d

# 運行測試
pytest tests/

# 啟動開發服務器
python -m src.gateway.main
```

### 常用命令

```bash
# 代碼格式化
black src/
isort src/

# 代碼檢查
flake8 src/
mypy src/

# 運行測試
pytest                          # 運行所有測試
pytest tests/test_router.py     # 運行特定測試
pytest -v --cov=src            # 帶覆蓋率報告

# 構建 Docker 鏡像
docker build -t rip:dev .

# 查看日誌
docker-compose logs -f rip-router
```

### 有用的資源

- [設計文檔](docs/README.md)
- [API 文檔](docs/04-AI_ROUTER.md)
- [Deployment Guide](docs/05-DEPLOYMENT.md)
- [Roadmap](docs/06-ROADMAP.md)

## 🚫 代碼審查時可能被拒絕的情況

1. **不符合代碼風格**
   - 沒有運行 black/isort/flake8
   - 沒有類型提示

2. **缺少測試**
   - 沒有單元測試
   - 測試覆蓋率低於要求

3. **缺少文檔**
   - 沒有 docstring
   - 沒有更新相關文檔

4. **設計問題**
   - 違反架構原則
   - 與現有設計衝突
   - 安全問題

5. **性能問題**
   - 引入重大性能退化
   - 沒有性能測試

## 📞 聯繫方式

有任何問題？

- 📧 Email: dev@example.com
- 💬 Discord: [Join Server]
- 📝 Discussions: GitHub Discussions

## 🎓 行為準則

我們致力於營造一個歡迎、包容的社區。

- 尊重他人
- 建設性反饋
- 沒有騷擾或歧視
- 專業溝通

違反行為準則的行為將被報告給維護者。

## 📄 許可證

通過提交 PR，你同意將代碼貢獻到本項目。
代碼將根據 MIT 許可證發布。

---

感謝你的貢獻！ ❤️

**Happy coding! 🚀**
