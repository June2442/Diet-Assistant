"""
子Agent基类和工作流框架
定义子Agent的标准接口和任务执行流程
"""

from typing import Dict, Any, List, Optional, Callable
from abc import ABC, abstractmethod
from enum import Enum
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent状态"""
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class BaseSubAgent(ABC):
    """
    子Agent基类

    所有子Agent（Memory、Health、Meal Decision等）都继承此类
    提供统一的接口和生命周期管理
    """

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.status = AgentStatus.IDLE
        self.dependencies = {}  # 依赖的其他Agent
        self.current_task = None
        self.task_history = []

    @abstractmethod
    async def initialize(self, **dependencies):
        """
        初始化Agent

        Args:
            **dependencies: 依赖的其他Agent实例
        """
        pass

    @abstractmethod
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理请求的主方法

        Args:
            request: 请求数据

        Returns:
            处理结果
        """
        pass

    async def execute_task(
        self,
        task: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行任务（带状态管理）

        标准工作流：
        1. 更新状态为WORKING
        2. 记录任务开始时间
        3. 调用process()处理
        4. 记录任务结果
        5. 更新状态
        """
        self.status = AgentStatus.WORKING
        self.current_task = task

        task_record = {
            "task_id": task.get("task_id"),
            "started_at": datetime.now(),
            "context": context
        }

        try:
            logger.info(f"[{self.agent_id}] Starting task: {task.get('task_id')}")

            # 执行任务
            result = await self.process(task)

            # 记录成功
            task_record["completed_at"] = datetime.now()
            task_record["status"] = "completed"
            task_record["result"] = result

            self.status = AgentStatus.COMPLETED
            logger.info(f"[{self.agent_id}] Task completed: {task.get('task_id')}")

            return {
                "success": True,
                "agent_id": self.agent_id,
                "result": result
            }

        except Exception as e:
            logger.error(f"[{self.agent_id}] Task failed: {e}", exc_info=True)

            # 记录失败
            task_record["completed_at"] = datetime.now()
            task_record["status"] = "failed"
            task_record["error"] = str(e)

            self.status = AgentStatus.FAILED

            return {
                "success": False,
                "agent_id": self.agent_id,
                "error": str(e)
            }

        finally:
            # 记录任务历史
            self.task_history.append(task_record)
            self.current_task = None

    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态"""
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "current_task": self.current_task,
            "task_history_count": len(self.task_history)
        }

    async def health_check(self) -> bool:
        """健康检查"""
        # 检查依赖是否正常
        for dep_name, dep_agent in self.dependencies.items():
            if not hasattr(dep_agent, 'health_check'):
                continue
            try:
                is_healthy = await dep_agent.health_check()
                if not is_healthy:
                    logger.warning(f"[{self.agent_id}] Dependency {dep_name} is unhealthy")
                    return False
            except Exception as e:
                logger.error(f"[{self.agent_id}] Health check failed for {dep_name}: {e}")
                return False

        return True


class AgentWorkflow:
    """
    Agent工作流编排器

    支持：
    1. 串行执行（Sequential）
    2. 并行执行（Parallel）
    3. 条件分支（Conditional）
    4. 循环执行（Loop）
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.steps = []
        self.context = {}

    def add_step(
        self,
        agent: BaseSubAgent,
        task: Dict[str, Any],
        condition: Optional[Callable] = None
    ):
        """
        添加工作流步骤

        Args:
            agent: 要执行的Agent
            task: 任务数据
            condition: 可选的执行条件
        """
        self.steps.append({
            "agent": agent,
            "task": task,
            "condition": condition
        })

    async def execute_sequential(self) -> List[Dict[str, Any]]:
        """
        串行执行所有步骤

        适用场景：后续步骤依赖前面步骤的结果
        """
        results = []

        for i, step in enumerate(self.steps):
            # 检查执行条件
            if step["condition"] and not step["condition"](self.context):
                logger.info(f"[Workflow {self.workflow_id}] Step {i} skipped due to condition")
                continue

            # 执行Agent任务
            result = await step["agent"].execute_task(step["task"], self.context)
            results.append(result)

            # 更新上下文（供后续步骤使用）
            if result["success"]:
                self.context[step["agent"].agent_id] = result["result"]

        return results

    async def execute_parallel(self) -> List[Dict[str, Any]]:
        """
        并行执行所有步骤

        适用场景：步骤之间无依赖关系，可以同时执行
        """
        tasks = []

        for step in self.steps:
            # 检查执行条件
            if step["condition"] and not step["condition"](self.context):
                continue

            # 创建并发任务
            task = step["agent"].execute_task(step["task"], self.context)
            tasks.append(task)

        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append({
                    "success": False,
                    "error": str(result)
                })
            else:
                processed_results.append(result)

        return processed_results


class AgentCoordinator:
    """
    Agent协调器

    负责：
    1. Agent注册和管理
    2. 任务分发
    3. 结果聚合
    4. 错误处理
    """

    def __init__(self):
        self.agents: Dict[str, BaseSubAgent] = {}
        self.task_queue = []

    def register_agent(self, agent: BaseSubAgent):
        """注册Agent"""
        self.agents[agent.agent_id] = agent
        logger.info(f"Registered agent: {agent.agent_id}")

    def get_agent(self, agent_id: str) -> Optional[BaseSubAgent]:
        """获取Agent实例"""
        return self.agents.get(agent_id)

    async def dispatch_task(
        self,
        agent_id: str,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        分发任务到指定Agent

        Args:
            agent_id: Agent ID
            task: 任务数据
            context: 上下文数据

        Returns:
            执行结果
        """
        agent = self.get_agent(agent_id)
        if not agent:
            return {
                "success": False,
                "error": f"Agent {agent_id} not found"
            }

        return await agent.execute_task(task, context or {})

    async def broadcast_task(
        self,
        task: Dict[str, Any],
        agent_ids: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        广播任务到多个Agent

        Args:
            task: 任务数据
            agent_ids: Agent ID列表（None表示所有Agent）

        Returns:
            {agent_id: result}
        """
        target_agents = agent_ids or list(self.agents.keys())

        tasks = []
        for agent_id in target_agents:
            agent = self.get_agent(agent_id)
            if agent:
                tasks.append(agent.execute_task(task, {}))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            agent_id: result
            for agent_id, result in zip(target_agents, results)
        }

    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有Agent健康状态"""
        health_status = {}

        for agent_id, agent in self.agents.items():
            try:
                is_healthy = await agent.health_check()
                health_status[agent_id] = is_healthy
            except Exception as e:
                logger.error(f"Health check failed for {agent_id}: {e}")
                health_status[agent_id] = False

        return health_status

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有Agent的状态"""
        return {
            agent_id: agent.get_status()
            for agent_id, agent in self.agents.items()
        }


# 全局协调器实例
agent_coordinator = AgentCoordinator()
