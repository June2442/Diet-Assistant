"""
Agent工作流示例和实际应用场景
展示如何使用子Agent框架完成复杂任务
"""

import asyncio
from typing import Dict, Any
import logging

from agents.base_agent import BaseSubAgent, AgentWorkflow, AgentCoordinator
from agents.communication import (
    AgentCommunicationProtocol,
    MessageBus,
    EventType
)

logger = logging.getLogger(__name__)


# ============================================
# 示例1: 用户拍照选菜的完整工作流
# ============================================

async def meal_decision_workflow_example(
    user_id: int,
    image_url: str,
    coordinator: AgentCoordinator,
    message_bus: MessageBus
):
    """
    完整的选菜决策工作流

    场景：用户在餐厅拍了菜单照片，询问"我该吃什么？"

    工作流：
    1. Memory Agent: 召回相关记忆
    2. Health Agent: 获取当前营养状态
    3. Vision Skill: 识别菜单中的菜品
    4. Safety Agent: 过滤不安全的菜品
    5. Meal Decision Agent: 生成推荐组合
    6. Emotion Agent: 提供情绪支持
    """

    # 创建工作流
    workflow = AgentWorkflow(workflow_id="meal_decision_001")

    # 步骤1: Memory Agent召回记忆
    memory_agent = coordinator.get_agent("memory_agent")
    workflow.add_step(
        agent=memory_agent,
        task={
            "task_id": "recall_memory",
            "action": "recall",
            "params": {
                "user_id": user_id,
                "context": {
                    "intent": "meal_decision",
                    "scenario": "restaurant_menu"
                }
            }
        }
    )

    # 步骤2: Health Agent获取营养状态
    health_agent = coordinator.get_agent("health_agent")
    workflow.add_step(
        agent=health_agent,
        task={
            "task_id": "get_health_state",
            "action": "get_current_state",
            "params": {
                "user_id": user_id
            }
        }
    )

    # 步骤3: Meal Decision Agent识别菜品并推荐
    meal_agent = coordinator.get_agent("meal_decision_agent")
    workflow.add_step(
        agent=meal_agent,
        task={
            "task_id": "recommend_dishes",
            "action": "recommend",
            "params": {
                "user_id": user_id,
                "image_url": image_url,
                "scenario": "restaurant_menu"
            }
        }
    )

    # 执行工作流（串行）
    results = await workflow.execute_sequential()

    # 提取结果
    memories = results[0]["result"] if results[0]["success"] else {}
    health_state = results[1]["result"] if results[1]["success"] else {}
    recommendations = results[2]["result"] if results[2]["success"] else {}

    # 发布事件
    comm = AgentCommunicationProtocol(message_bus, "orchestrator")
    await comm.emit_event(
        EventType.MEAL_RECOMMENDED,
        {
            "user_id": user_id,
            "recommendations": recommendations,
            "context": {
                "memories": memories,
                "health_state": health_state
            }
        }
    )

    return {
        "success": True,
        "recommendations": recommendations,
        "health_context": health_state,
        "memories": memories
    }


# ============================================
# 示例2: 记忆压缩的定时任务工作流
# ============================================

async def memory_compression_workflow_example(
    coordinator: AgentCoordinator,
    message_bus: MessageBus
):
    """
    记忆压缩工作流

    场景：每日凌晨3点自动运行，压缩超过90天的记忆

    工作流：
    1. 扫描超过90天的raw_memory
    2. 计算重要性评分
    3. 生成语义摘要
    4. 删除低价值数据
    5. 发送压缩报告
    """

    memory_agent = coordinator.get_agent("memory_agent")

    # 执行压缩任务
    result = await memory_agent.execute_task(
        task={
            "task_id": "compress_memories",
            "action": "compress_old_memories",
            "params": {}
        },
        context={}
    )

    if result["success"]:
        # 发布压缩完成事件
        comm = AgentCommunicationProtocol(message_bus, "scheduler")
        await comm.emit_event(
            EventType.MEMORY_COMPRESSED,
            {
                "compressed_count": result["result"].get("compressed_count", 0),
                "deleted_count": result["result"].get("deleted_count", 0),
                "timestamp": result["result"].get("timestamp")
            }
        )

    return result


# ============================================
# 示例3: 并行健康数据采集工作流
# ============================================

async def health_data_collection_workflow_example(
    user_id: int,
    coordinator: AgentCoordinator,
    message_bus: MessageBus
):
    """
    并行采集多个健康数据源

    场景：用户更新健康数据，需要同时：
    1. 更新Health Agent的状态
    2. Memory Agent记录
    3. 检查是否达到里程碑
    4. 评估情绪状态
    """

    # 创建并行工作流
    workflow = AgentWorkflow(workflow_id="health_data_collection_001")

    health_agent = coordinator.get_agent("health_agent")
    memory_agent = coordinator.get_agent("memory_agent")
    emotion_agent = coordinator.get_agent("emotion_support_agent")

    # 添加并行任务
    workflow.add_step(
        agent=health_agent,
        task={
            "task_id": "update_health",
            "action": "update_daily_health",
            "params": {
                "user_id": user_id,
                "data": {
                    "weight": 73.5,
                    "blood_pressure": "125/80"
                }
            }
        }
    )

    workflow.add_step(
        agent=memory_agent,
        task={
            "task_id": "record_health_update",
            "action": "store",
            "params": {
                "user_id": user_id,
                "memory_type": "health_update",
                "data": {"weight": 73.5}
            }
        }
    )

    workflow.add_step(
        agent=emotion_agent,
        task={
            "task_id": "assess_emotion",
            "action": "detect_emotion",
            "params": {
                "user_id": user_id,
                "context": {"weight_change": -0.5}
            }
        }
    )

    # 并行执行
    results = await workflow.execute_parallel()

    return {
        "success": all(r.get("success", False) for r in results),
        "results": results
    }


# ============================================
# 示例4: 条件分支工作流
# ============================================

async def conditional_workflow_example(
    user_id: int,
    coordinator: AgentCoordinator
):
    """
    条件分支工作流

    场景：根据用户情绪状态，选择不同的响应策略
    """

    emotion_agent = coordinator.get_agent("emotion_support_agent")

    # 先检测情绪
    emotion_result = await emotion_agent.execute_task(
        task={
            "task_id": "detect_emotion",
            "action": "detect_emotion",
            "params": {
                "user_id": user_id,
                "message": "我又吃多了，好难受"
            }
        },
        context={}
    )

    emotion = emotion_result["result"].get("emotion")

    # 创建工作流
    workflow = AgentWorkflow(workflow_id="conditional_001")

    # 根据情绪添加不同的步骤
    if emotion == "guilt":
        # 内疚情绪：提供情绪支持 + 调整下一餐计划
        workflow.add_step(
            agent=emotion_agent,
            task={
                "task_id": "provide_support",
                "action": "provide_support",
                "params": {
                    "user_id": user_id,
                    "emotion": emotion
                }
            }
        )

        meal_agent = coordinator.get_agent("meal_decision_agent")
        workflow.add_step(
            agent=meal_agent,
            task={
                "task_id": "adjust_next_meal",
                "action": "adjust_plan",
                "params": {
                    "user_id": user_id,
                    "reason": "overeating_compensation"
                }
            }
        )

    elif emotion == "anxiety":
        # 焦虑情绪：提供支持 + 检查风险
        workflow.add_step(
            agent=emotion_agent,
            task={
                "task_id": "provide_support",
                "action": "provide_support",
                "params": {
                    "user_id": user_id,
                    "emotion": emotion
                }
            }
        )

        workflow.add_step(
            agent=emotion_agent,
            task={
                "task_id": "assess_risk",
                "action": "assess_eating_disorder_risk",
                "params": {
                    "user_id": user_id
                }
            }
        )

    # 执行工作流
    results = await workflow.execute_sequential()

    return {
        "emotion": emotion,
        "workflow_results": results
    }


# ============================================
# 示例5: Agent间通信示例
# ============================================

async def agent_communication_example(
    coordinator: AgentCoordinator,
    message_bus: MessageBus
):
    """
    Agent间通信示例

    场景：Meal Decision Agent需要从Memory Agent获取数据
    """

    # 创建通信协议
    meal_comm = AgentCommunicationProtocol(message_bus, "meal_decision_agent")

    # 向Memory Agent发送请求
    response = await meal_comm.request(
        target_agent="memory_agent",
        action="recall",
        params={
            "user_id": 1001,
            "context": {"intent": "meal_decision"}
        },
        timeout=10
    )

    if response:
        logger.info(f"Received response from memory_agent: {response}")

    # 发送通知（不需要响应）
    await meal_comm.notify(
        target_agent="health_agent",
        notification_type="meal_selected",
        data={
            "user_id": 1001,
            "selected_dishes": ["清蒸鱼", "炒青菜"]
        }
    )

    # 发布事件
    await meal_comm.emit_event(
        EventType.MEAL_RECOMMENDED,
        {
            "user_id": 1001,
            "recommendations": []
        }
    )


# ============================================
# 示例6: 事件订阅和处理
# ============================================

async def event_subscription_example(message_bus: MessageBus):
    """
    事件订阅示例

    场景：Health Agent订阅MEAL_RECORDED事件，自动更新营养状态
    """

    # 定义事件处理函数
    async def handle_meal_recorded(event_data: Dict[str, Any]):
        user_id = event_data.get("user_id")
        meal_nutrition = event_data.get("nutrition")

        logger.info(f"[Health Agent] Meal recorded for user {user_id}: {meal_nutrition}")

        # TODO: 更新今日营养摄入
        # await health_agent.update_daily_intake(user_id, meal_nutrition)

    # 订阅事件
    health_comm = AgentCommunicationProtocol(message_bus, "health_agent")
    health_comm.subscribe_event(
        EventType.MEAL_RECORDED,
        handle_meal_recorded
    )

    logger.info("Health Agent subscribed to MEAL_RECORDED event")


# ============================================
# 运行示例
# ============================================

async def run_workflow_examples():
    """运行所有工作流示例"""

    # 初始化
    coordinator = AgentCoordinator()
    message_bus = MessageBus()
    await message_bus.start()

    # TODO: 注册所有Agent
    # coordinator.register_agent(memory_agent)
    # coordinator.register_agent(health_agent)
    # ...

    logger.info("=== Running Workflow Examples ===")

    # 示例1: 选菜决策
    # result1 = await meal_decision_workflow_example(
    #     user_id=1001,
    #     image_url="https://example.com/menu.jpg",
    #     coordinator=coordinator,
    #     message_bus=message_bus
    # )
    # logger.info(f"Meal decision result: {result1}")

    # 示例2: 记忆压缩
    # result2 = await memory_compression_workflow_example(
    #     coordinator=coordinator,
    #     message_bus=message_bus
    # )
    # logger.info(f"Memory compression result: {result2}")

    # 停止消息总线
    await message_bus.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_workflow_examples())
