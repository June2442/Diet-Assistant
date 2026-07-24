# 子Agent框架设计文档

## 一、架构概览

Diet Assistant采用**多Agent协作架构**，每个Agent作为独立的子系统运行，通过标准化的通信协议协作完成复杂任务。

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                        │
│                  (总调度器 + 意图分类)                         │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │   Message Bus         │  (消息总线 - 异步通信)
         │   Event System        │  (事件系统 - 发布订阅)
         └───────────┬───────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
    ▼                ▼                ▼
┌─────────┐    ┌─────────┐    ┌─────────┐
│ Memory  │    │ Health  │    │  Meal   │
│ Agent   │    │ Agent   │    │Decision │
│         │    │         │    │ Agent   │
└─────────┘    └─────────┘    └─────────┘
    ▲                ▲                ▲
    │                │                │
    └────────────────┴────────────────┘
         Agent Communication Protocol
```

---

## 二、核心组件

### 2.1 BaseSubAgent（子Agent基类）

**文件**: `agents/base_agent.py`

**职责**:
- 定义所有子Agent的标准接口
- 提供生命周期管理（初始化、执行、停止）
- 任务执行状态跟踪
- 健康检查机制

**核心方法**:
```python
class BaseSubAgent(ABC):
    @abstractmethod
    async def initialize(self, **dependencies):
        """初始化Agent，注入依赖"""
        
    @abstractmethod
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理请求的核心逻辑"""
        
    async def execute_task(self, task, context) -> Dict[str, Any]:
        """带状态管理的任务执行"""
        
    async def health_check(self) -> bool:
        """健康检查"""
```

**已实现的子Agent**:
1. ✅ Memory Agent - 记忆管理
2. ✅ Health Agent - 健康状态
3. ✅ Meal Decision Agent - 选菜决策
4. ✅ Recipe Agent - 菜谱专家
5. ✅ Emotion Support Agent - 情绪支持
6. ✅ Safety Agent - 安全监测

---

### 2.2 AgentCommunicationProtocol（通信协议）

**文件**: `agents/communication.py`

**职责**:
- Agent间消息传递
- 请求-响应模式
- 事件发布-订阅
- 消息路由和队列管理

**通信模式**:

**1. 请求-响应（Request-Response）**
```python
# Meal Decision Agent向Memory Agent请求数据
comm = AgentCommunicationProtocol(message_bus, "meal_decision_agent")
response = await comm.request(
    target_agent="memory_agent",
    action="recall",
    params={"user_id": 1001},
    timeout=10
)
```

**2. 通知（Notification）**
```python
# 通知Health Agent餐食已记录（不需要响应）
await comm.notify(
    target_agent="health_agent",
    notification_type="meal_recorded",
    data={"user_id": 1001, "nutrition": {...}}
)
```

**3. 事件广播（Event Broadcasting）**
```python
# 发布事件，所有订阅者都会收到
await comm.emit_event(
    EventType.MEAL_RECOMMENDED,
    {"user_id": 1001, "recommendations": [...]}
)
```

**消息类型**:
- `REQUEST` - 请求（需要响应）
- `RESPONSE` - 响应
- `NOTIFICATION` - 通知（不需要响应）
- `EVENT` - 事件广播

**系统事件类型**:
```python
class EventType(Enum):
    HEALTH_DATA_UPDATED = "health_data_updated"
    MEAL_RECORDED = "meal_recorded"
    MEAL_RECOMMENDED = "meal_recommended"
    MEMORY_COMPRESSED = "memory_compressed"
    EMOTION_DETECTED = "emotion_detected"
    RISK_ALERT = "risk_alert"
    SAFETY_VIOLATION = "safety_violation"
    ALLERGEN_DETECTED = "allergen_detected"
```

---

### 2.3 AgentWorkflow（工作流编排）

**文件**: `agents/base_agent.py`

**职责**:
- 定义多Agent协作的工作流
- 支持串行、并行、条件分支
- 上下文管理和结果聚合

**执行模式**:

**1. 串行执行（Sequential）**
```python
workflow = AgentWorkflow("meal_decision_flow")
workflow.add_step(memory_agent, task1)
workflow.add_step(health_agent, task2)
workflow.add_step(meal_agent, task3)

results = await workflow.execute_sequential()
# 步骤1 → 步骤2 → 步骤3（依次执行）
```

**2. 并行执行（Parallel）**
```python
workflow = AgentWorkflow("parallel_collection")
workflow.add_step(memory_agent, task1)
workflow.add_step(health_agent, task2)
workflow.add_step(emotion_agent, task3)

results = await workflow.execute_parallel()
# 步骤1、2、3同时执行
```

**3. 条件分支（Conditional）**
```python
workflow.add_step(
    agent=emotion_agent,
    task=support_task,
    condition=lambda ctx: ctx.get("emotion") == "guilt"
)
# 仅当条件满足时执行
```

---

### 2.4 AgentCoordinator（协调器）

**文件**: `agents/base_agent.py`

**职责**:
- Agent注册和管理
- 任务分发
- 健康检查
- 状态监控

**核心方法**:
```python
coordinator = AgentCoordinator()

# 注册Agent
coordinator.register_agent(memory_agent)
coordinator.register_agent(health_agent)

# 分发任务到指定Agent
result = await coordinator.dispatch_task(
    agent_id="memory_agent",
    task={"action": "recall", "params": {...}}
)

# 广播任务到多个Agent
results = await coordinator.broadcast_task(
    task={...},
    agent_ids=["memory_agent", "health_agent"]
)

# 健康检查所有Agent
health_status = await coordinator.health_check_all()
```

---

## 三、工作流示例

### 3.1 用户拍照选菜工作流

**场景**: 用户在餐厅拍了菜单照片，询问"我该吃什么？"

**工作流**:
```
1. Memory Agent: 召回用户偏好和历史记忆
   ↓
2. Health Agent: 获取当前营养状态和缺口
   ↓
3. Vision Skill: 识别照片中的菜品
   ↓
4. Safety Agent: 过滤过敏原和不安全菜品
   ↓
5. Meal Decision Agent: 生成推荐组合
   ↓
6. 发布MEAL_RECOMMENDED事件
```

**代码结构**: 见 `agents/workflow_examples.py`

---

### 3.2 记忆压缩定时任务

**场景**: 每日凌晨3点自动压缩超过90天的记忆

**工作流**:
```
1. 扫描raw_memory表（created_time < 90天前）
   ↓
2. 批量计算importance_score
   ↓
3. 低价值记忆（score < 0.3）→ 删除
   ↓
4. 高价值记忆（score ≥ 0.3）→ 生成语义摘要
   ↓
5. 保存到semantic_memory表
   ↓
6. 发布MEMORY_COMPRESSED事件
```

---

### 3.3 并行健康数据采集

**场景**: 用户更新体重，需要同时通知多个Agent

**工作流** (并行):
```
┌─────────────────────────────────────┐
│   Health Agent: 更新daily_health    │
├─────────────────────────────────────┤
│   Memory Agent: 记录健康事件         │  ← 并行执行
├─────────────────────────────────────┤
│   Emotion Agent: 评估情绪状态        │
└─────────────────────────────────────┘
```

---

## 四、Agent依赖关系

```
Agent Orchestrator (总调度)
    │
    ├── Memory Agent (独立，被所有Agent依赖)
    │
    ├── Health Agent (依赖: Memory)
    │
    ├── Meal Decision Agent (依赖: Memory, Health, Safety)
    │
    ├── Recipe Agent (依赖: Memory, Health)
    │
    ├── Emotion Support Agent (依赖: Memory, Safety)
    │
    └── Safety Agent (独立)
```

**依赖注入**:
```python
# 初始化时注入依赖
await meal_decision_agent.initialize(
    memory_agent=memory_agent,
    health_agent=health_agent,
    safety_agent=safety_agent
)
```

---

## 五、消息总线架构

```
┌──────────────────────────────────────────────────────┐
│                   Message Bus                         │
│  ┌────────────────────────────────────────────────┐ │
│  │   Message Queue (asyncio.Queue)                │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │   Subscribers Registry                          │ │
│  │   {event_type: [handler1, handler2, ...]}     │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │   Pending Responses                             │ │
│  │   {correlation_id: future}                     │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

**特点**:
- ✅ 异步非阻塞
- ✅ 请求超时控制
- ✅ 事件发布-订阅
- ✅ 消息优先级
- ✅ 错误隔离

---

## 六、开发指南

### 6.1 创建新的子Agent

```python
from agents.base_agent import BaseSubAgent

class NewAgent(BaseSubAgent):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(agent_id="new_agent", config=config)
        
    async def initialize(self, **dependencies):
        """注入依赖的Agent"""
        self.memory_agent = dependencies.get("memory_agent")
        logger.info("New Agent initialized")
        
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理请求的核心逻辑"""
        action = request.get("action")
        params = request.get("params")
        
        if action == "do_something":
            return await self._do_something(params)
        
        return {"error": "Unknown action"}
```

### 6.2 注册和使用Agent

```python
# 1. 创建实例
new_agent = NewAgent(config={})

# 2. 初始化
await new_agent.initialize(memory_agent=memory_agent)

# 3. 注册到协调器
coordinator.register_agent(new_agent)

# 4. 使用
result = await coordinator.dispatch_task(
    agent_id="new_agent",
    task={"action": "do_something", "params": {...}}
)
```

### 6.3 订阅事件

```python
async def handle_meal_recorded(event_data: Dict[str, Any]):
    user_id = event_data["user_id"]
    # 处理逻辑
    
# 订阅
comm = AgentCommunicationProtocol(message_bus, "my_agent")
comm.subscribe_event(EventType.MEAL_RECORDED, handle_meal_recorded)
```

---

## 七、技术栈

- **异步框架**: asyncio
- **消息队列**: asyncio.Queue
- **Agent通信**: 自定义消息总线
- **工作流编排**: 自定义AgentWorkflow
- **事件系统**: 发布-订阅模式

---

## 八、下一步实现

### Phase 1: 核心框架完善（由Codex完成）
- [ ] 实现AgentCoordinator的完整逻辑
- [ ] 实现MessageBus的消息持久化
- [ ] 添加消息重试机制
- [ ] 实现Agent负载均衡

### Phase 2: Agent业务逻辑（由Codex完成）
- [ ] Memory Agent的压缩算法
- [ ] Health Agent的营养计算
- [ ] Meal Decision Agent的推荐算法
- [ ] 各Agent的数据库操作

### Phase 3: 监控和运维（由Codex完成）
- [ ] Agent性能监控
- [ ] 消息总线监控
- [ ] 任务执行日志
- [ ] 错误追踪和报警

---

**子Agent框架设计完成！** ✅

所有核心接口、通信协议、工作流编排已定义完毕，具体业务逻辑实现交由Codex完成。
