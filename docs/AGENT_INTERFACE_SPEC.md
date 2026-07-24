# Agent接口规范文档

## 一、标准Agent接口

### 1.1 基础接口定义

所有Agent必须实现以下标准接口：

```python
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

class IAgent(ABC):
    """Agent标准接口"""
    
    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Agent唯一标识符"""
        pass
    
    @abstractmethod
    async def initialize(self, **dependencies) -> None:
        """
        初始化Agent
        
        Args:
            **dependencies: 依赖的其他Agent或服务
        """
        pass
    
    @abstractmethod
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理请求
        
        Args:
            request: {
                "action": str,      # 操作类型
                "params": dict,     # 参数
                "context": dict     # 上下文（可选）
            }
            
        Returns:
            {
                "success": bool,
                "result": Any,
                "error": str (可选)
            }
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
```

---

## 二、各Agent接口规范

### 2.1 Memory Agent

**Agent ID**: `memory_agent`

**依赖**: 无（独立Agent）

**核心操作**:

#### 2.1.1 存储记忆
```python
# Action: store
Request:
{
    "action": "store",
    "params": {
        "user_id": int,
        "memory_type": str,  # meal_photo, chat, sensor, order
        "data": dict,
        "importance_score": float  # 可选，0-1
    }
}

Response:
{
    "success": bool,
    "result": {
        "memory_id": str,
        "expire_time": datetime
    }
}
```

#### 2.1.2 召回记忆
```python
# Action: recall
Request:
{
    "action": "recall",
    "params": {
        "user_id": int,
        "context": {
            "intent": str,
            "meal_type": str,  # 可选
            "embedding": list  # 可选，用于向量检索
        },
        "limit": int  # 默认10
    }
}

Response:
{
    "success": bool,
    "result": {
        "recent": list,      # 近期记忆
        "semantic": list,    # 语义记忆
        "events": list,      # 事件记忆
        "profile": dict      # 健康画像
    }
}
```

#### 2.1.3 压缩旧记忆
```python
# Action: compress_old_memories
Request:
{
    "action": "compress_old_memories",
    "params": {}
}

Response:
{
    "success": bool,
    "result": {
        "compressed_count": int,
        "deleted_count": int,
        "timestamp": datetime
    }
}
```

#### 2.1.4 获取健康画像
```python
# Action: get_health_profile
Request:
{
    "action": "get_health_profile",
    "params": {
        "user_id": int
    }
}

Response:
{
    "success": bool,
    "result": {
        "user_id": int,
        "goal": str,
        "current_weight": float,
        "nutrition_pattern": dict,
        "preferences": dict,
        "allergies": list
    }
}
```

---

### 2.2 Health Agent

**Agent ID**: `health_agent`

**依赖**: Memory Agent

**核心操作**:

#### 2.2.1 获取当前健康状态
```python
# Action: get_current_state
Request:
{
    "action": "get_current_state",
    "params": {
        "user_id": int
    }
}

Response:
{
    "success": bool,
    "result": {
        "profile": dict,        # 用户画像
        "today_intake": dict,   # 今日摄入
        "target": dict,         # 今日目标
        "gap": dict,            # 营养缺口
        "calorie_budget": float # 剩余热量预算
    }
}
```

#### 2.2.2 更新每日健康数据
```python
# Action: update_daily_health
Request:
{
    "action": "update_daily_health",
    "params": {
        "user_id": int,
        "date": str,  # YYYY-MM-DD
        "data": {
            "weight": float,
            "blood_pressure": str,
            "sleep_hours": float,
            "exercise_log": dict
        }
    }
}

Response:
{
    "success": bool,
    "result": {
        "updated": bool,
        "changes": dict  # 与上次的变化
    }
}
```

#### 2.2.3 计算营养缺口
```python
# Action: calculate_gap
Request:
{
    "action": "calculate_gap",
    "params": {
        "user_id": int,
        "date": str
    }
}

Response:
{
    "success": bool,
    "result": {
        "calories": float,      # 正值=还需摄入
        "protein": float,
        "carbs": float,
        "fat": float,
        "fiber": float,
        "vegetables": float,
        "sodium_available": float
    }
}
```

---

### 2.3 Meal Decision Agent

**Agent ID**: `meal_decision_agent`

**依赖**: Memory Agent, Health Agent, Safety Agent

**核心操作**:

#### 2.3.1 推荐菜品
```python
# Action: recommend
Request:
{
    "action": "recommend",
    "params": {
        "user_id": int,
        "scenario": str,  # restaurant_menu, takeout_platform, user_photo
        "image_url": str,  # 可选
        "available_dishes": list  # 可选，已识别的菜品
    }
}

Response:
{
    "success": bool,
    "result": {
        "recommendations": [
            {
                "dishes": list,
                "score": float,
                "nutrition": dict,
                "explanation": str,
                "warnings": list
            }
        ],
        "health_state": dict,
        "context": dict
    }
}
```

#### 2.3.2 调整餐食计划
```python
# Action: adjust_plan
Request:
{
    "action": "adjust_plan",
    "params": {
        "user_id": int,
        "reason": str,  # overeating_compensation, goal_change
        "adjustments": dict
    }
}

Response:
{
    "success": bool,
    "result": {
        "adjusted_target": dict,
        "suggestions": list
    }
}
```

---

### 2.4 Recipe Agent

**Agent ID**: `recipe_agent`

**依赖**: Memory Agent, Health Agent, CookHero

**核心操作**:

#### 2.4.1 搜索菜谱
```python
# Action: search_recipes
Request:
{
    "action": "search_recipes",
    "params": {
        "user_id": int,
        "query": str,
        "filters": {
            "difficulty": str,      # 可选
            "cooking_time": str,    # 可选，如 "<30"
            "cuisine": str          # 可选
        }
    }
}

Response:
{
    "success": bool,
    "result": {
        "recipes": [
            {
                "recipe_id": str,
                "name": str,
                "ingredients": list,
                "steps": list,
                "cooking_time": int,
                "difficulty": str,
                "nutrition": dict,
                "fit_score": float
            }
        ]
    }
}
```

#### 2.4.2 获取烹饪指导
```python
# Action: get_instructions
Request:
{
    "action": "get_instructions",
    "params": {
        "recipe_id": str,
        "user_id": int
    }
}

Response:
{
    "success": bool,
    "result": {
        "instructions": list,
        "tips": list,
        "video_url": str
    }
}
```

---

### 2.5 Emotion Support Agent

**Agent ID**: `emotion_support_agent`

**依赖**: Memory Agent, Safety Agent

**核心操作**:

#### 2.5.1 检测情绪
```python
# Action: detect_emotion
Request:
{
    "action": "detect_emotion",
    "params": {
        "user_id": int,
        "message": str,
        "context": dict  # 可选
    }
}

Response:
{
    "success": bool,
    "result": {
        "emotion": str,  # guilt, anxiety, frustration, stress, neutral
        "confidence": float
    }
}
```

#### 2.5.2 提供情绪支持
```python
# Action: provide_support
Request:
{
    "action": "provide_support",
    "params": {
        "user_id": int,
        "emotion": str,
        "context": dict
    }
}

Response:
{
    "success": bool,
    "result": {
        "message": str,
        "action_suggestions": list,
        "cognitive_reframe": str,
        "risk_level": str,
        "professional_help": dict  # 可选
    }
}
```

#### 2.5.3 评估饮食障碍风险
```python
# Action: assess_risk
Request:
{
    "action": "assess_risk",
    "params": {
        "user_id": int
    }
}

Response:
{
    "success": bool,
    "result": {
        "risk_level": str,  # none, low, moderate, high
        "risk_factors": list,
        "recommendations": list
    }
}
```

---

### 2.6 Safety Agent

**Agent ID**: `safety_agent`

**依赖**: 无（独立Agent）

**核心操作**:

#### 2.6.1 输入校验
```python
# Action: validate_input
Request:
{
    "action": "validate_input",
    "params": {
        "data": dict
    }
}

Response:
{
    "success": bool,
    "result": {
        "valid": bool,
        "errors": list
    }
}
```

#### 2.6.2 过滤不安全菜品
```python
# Action: filter_dishes
Request:
{
    "action": "filter_dishes",
    "params": {
        "dishes": list,
        "user_profile": dict
    }
}

Response:
{
    "success": bool,
    "result": {
        "safe_dishes": list,
        "filtered_out": list,
        "reasons": dict
    }
}
```

#### 2.6.3 检查推荐安全性
```python
# Action: check_recommendation
Request:
{
    "action": "check_recommendation",
    "params": {
        "user_id": int,
        "recommendation": dict
    }
}

Response:
{
    "success": bool,
    "result": {
        "safe": bool,
        "risk_level": str,
        "reason": str,
        "suggestions": list
    }
}
```

---

## 三、事件规范

### 3.1 事件结构

所有事件必须包含以下字段：

```python
{
    "event_type": str,      # 事件类型
    "timestamp": datetime,  # 时间戳
    "source_agent": str,    # 发起Agent
    "data": dict           # 事件数据
}
```

### 3.2 标准事件列表

| 事件类型 | 触发条件 | 数据字段 | 订阅者 |
|---------|---------|---------|-------|
| `HEALTH_DATA_UPDATED` | 健康数据更新 | user_id, changes | Memory Agent |
| `MEAL_RECORDED` | 餐食记录 | user_id, nutrition | Health Agent, Memory Agent |
| `MEAL_RECOMMENDED` | 推荐生成 | user_id, recommendations | - |
| `MEMORY_COMPRESSED` | 记忆压缩完成 | compressed_count, deleted_count | - |
| `EMOTION_DETECTED` | 情绪检测 | user_id, emotion, risk_level | Memory Agent |
| `RISK_ALERT` | 高风险警告 | user_id, risk_type, level | Safety Agent |
| `ALLERGEN_DETECTED` | 过敏原检测 | user_id, allergen, dishes | Safety Agent |

---

## 四、错误处理规范

### 4.1 错误响应格式

```python
{
    "success": false,
    "error": {
        "code": str,      # 错误代码
        "message": str,   # 错误描述
        "details": dict   # 详细信息（可选）
    }
}
```

### 4.2 标准错误代码

| 错误代码 | 描述 | HTTP状态码 |
|---------|------|----------|
| `AGENT_NOT_FOUND` | Agent不存在 | 404 |
| `INVALID_ACTION` | 无效的操作 | 400 |
| `INVALID_PARAMS` | 参数错误 | 400 |
| `DEPENDENCY_ERROR` | 依赖Agent错误 | 503 |
| `TIMEOUT` | 请求超时 | 504 |
| `INTERNAL_ERROR` | 内部错误 | 500 |
| `PERMISSION_DENIED` | 权限不足 | 403 |

---

## 五、性能规范

### 5.1 响应时间要求

| Agent操作 | 目标响应时间 | 最大响应时间 |
|----------|------------|------------|
| Memory召回 | < 100ms | 500ms |
| 健康状态计算 | < 50ms | 200ms |
| 选菜推荐（含Vision） | < 3s | 10s |
| 菜谱搜索 | < 200ms | 1s |
| 情绪检测 | < 100ms | 500ms |
| 安全检查 | < 50ms | 200ms |

### 5.2 并发要求

- 每个Agent应支持至少 **10个并发请求**
- 消息总线应支持 **100+ 消息/秒**
- 事件系统应支持 **50+ 订阅者**

---

## 六、测试规范

### 6.1 单元测试

每个Agent必须包含以下测试：

```python
class TestMemoryAgent:
    async def test_store_memory(self):
        """测试存储记忆"""
        
    async def test_recall_memory(self):
        """测试召回记忆"""
        
    async def test_compress_old_memories(self):
        """测试记忆压缩"""
        
    async def test_health_check(self):
        """测试健康检查"""
```

### 6.2 集成测试

测试Agent间协作：

```python
async def test_meal_decision_workflow(self):
    """测试完整的选菜决策流程"""
    # 1. Memory召回
    # 2. Health状态
    # 3. Safety检查
    # 4. Meal推荐
```

---

## 七、文档要求

每个Agent必须提供：

1. **README.md** - Agent概述
2. **API.md** - 详细API文档
3. **EXAMPLES.md** - 使用示例
4. **CHANGELOG.md** - 变更日志

---

**接口规范文档完成！** ✅

所有Agent的标准接口、请求/响应格式、事件规范已定义完毕。
