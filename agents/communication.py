"""
Agent间通信协议
定义Agent之间的消息传递和事件系统
"""

from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    REQUEST = "request"          # 请求（需要响应）
    RESPONSE = "response"        # 响应
    NOTIFICATION = "notification"  # 通知（不需要响应）
    EVENT = "event"              # 事件广播


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Message:
    """Agent间通信消息"""
    message_id: str
    message_type: MessageType
    from_agent: str
    to_agent: str
    content: Dict[str, Any]
    priority: MessagePriority
    timestamp: datetime
    correlation_id: Optional[str] = None  # 关联ID（用于请求-响应匹配）
    requires_response: bool = False
    timeout: Optional[int] = None  # 超时时间（秒）


class MessageBus:
    """
    消息总线

    职责：
    1. Agent间消息路由
    2. 消息队列管理
    3. 发布-订阅模式支持
    4. 请求-响应匹配
    """

    def __init__(self):
        self.message_queue = asyncio.Queue()
        self.subscribers: Dict[str, List[Callable]] = {}  # {event_type: [handler1, handler2]}
        self.pending_responses: Dict[str, asyncio.Future] = {}  # {correlation_id: future}
        self.running = False

    async def start(self):
        """启动消息总线"""
        self.running = True
        logger.info("Message bus started")

        # 启动消息处理循环
        asyncio.create_task(self._process_messages())

    async def stop(self):
        """停止消息总线"""
        self.running = False
        logger.info("Message bus stopped")

    async def send_message(self, message: Message) -> Optional[Dict[str, Any]]:
        """
        发送消息

        Args:
            message: 消息对象

        Returns:
            如果需要响应，返回响应内容；否则返回None
        """
        # 放入消息队列
        await self.message_queue.put(message)

        # 如果需要响应，等待响应
        if message.requires_response:
            future = asyncio.Future()
            self.pending_responses[message.message_id] = future

            try:
                # 等待响应（带超时）
                timeout = message.timeout or 30
                response = await asyncio.wait_for(future, timeout=timeout)
                return response
            except asyncio.TimeoutError:
                logger.error(f"Message {message.message_id} timeout waiting for response")
                self.pending_responses.pop(message.message_id, None)
                return None

        return None

    async def send_response(
        self,
        correlation_id: str,
        response_content: Dict[str, Any]
    ):
        """
        发送响应消息

        Args:
            correlation_id: 原始请求的消息ID
            response_content: 响应内容
        """
        future = self.pending_responses.get(correlation_id)
        if future and not future.done():
            future.set_result(response_content)
            self.pending_responses.pop(correlation_id, None)
        else:
            logger.warning(f"No pending request for correlation_id: {correlation_id}")

    def subscribe(self, event_type: str, handler: Callable):
        """
        订阅事件

        Args:
            event_type: 事件类型
            handler: 事件处理函数
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []

        self.subscribers[event_type].append(handler)
        logger.info(f"Subscribed to event: {event_type}")

    async def publish_event(self, event_type: str, event_data: Dict[str, Any]):
        """
        发布事件

        Args:
            event_type: 事件类型
            event_data: 事件数据
        """
        handlers = self.subscribers.get(event_type, [])

        for handler in handlers:
            try:
                await handler(event_data)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}", exc_info=True)

    async def _process_messages(self):
        """消息处理循环"""
        while self.running:
            try:
                # 从队列获取消息
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )

                # 处理消息
                await self._handle_message(message)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)

    async def _handle_message(self, message: Message):
        """
        处理单个消息

        根据消息类型分发到不同的处理逻辑
        """
        logger.debug(f"Handling message: {message.message_id} from {message.from_agent} to {message.to_agent}")

        if message.message_type == MessageType.EVENT:
            # 事件广播
            event_type = message.content.get("event_type")
            await self.publish_event(event_type, message.content)

        elif message.message_type == MessageType.RESPONSE:
            # 响应消息
            await self.send_response(message.correlation_id, message.content)

        # REQUEST和NOTIFICATION由具体Agent处理


class EventType(Enum):
    """系统事件类型"""
    # 健康相关
    HEALTH_DATA_UPDATED = "health_data_updated"
    WEIGHT_MILESTONE = "weight_milestone"
    NUTRITION_GAP_CRITICAL = "nutrition_gap_critical"

    # 餐食相关
    MEAL_RECORDED = "meal_recorded"
    MEAL_RECOMMENDED = "meal_recommended"
    RECIPE_USED = "recipe_used"

    # 记忆相关
    MEMORY_COMPRESSED = "memory_compressed"
    MEMORY_RECALLED = "memory_recalled"

    # 情绪相关
    EMOTION_DETECTED = "emotion_detected"
    RISK_ALERT = "risk_alert"

    # 安全相关
    SAFETY_VIOLATION = "safety_violation"
    ALLERGEN_DETECTED = "allergen_detected"


class AgentCommunicationProtocol:
    """
    Agent通信协议

    提供高层API简化Agent间通信
    """

    def __init__(self, message_bus: MessageBus, agent_id: str):
        self.message_bus = message_bus
        self.agent_id = agent_id

    async def request(
        self,
        target_agent: str,
        action: str,
        params: Dict[str, Any],
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        向另一个Agent发送请求

        Args:
            target_agent: 目标Agent ID
            action: 请求的操作
            params: 参数
            timeout: 超时时间

        Returns:
            响应结果
        """
        message = Message(
            message_id=self._generate_message_id(),
            message_type=MessageType.REQUEST,
            from_agent=self.agent_id,
            to_agent=target_agent,
            content={
                "action": action,
                "params": params
            },
            priority=MessagePriority.NORMAL,
            timestamp=datetime.now(),
            requires_response=True,
            timeout=timeout
        )

        return await self.message_bus.send_message(message)

    async def notify(
        self,
        target_agent: str,
        notification_type: str,
        data: Dict[str, Any]
    ):
        """
        发送通知（不需要响应）

        Args:
            target_agent: 目标Agent ID
            notification_type: 通知类型
            data: 通知数据
        """
        message = Message(
            message_id=self._generate_message_id(),
            message_type=MessageType.NOTIFICATION,
            from_agent=self.agent_id,
            to_agent=target_agent,
            content={
                "notification_type": notification_type,
                "data": data
            },
            priority=MessagePriority.NORMAL,
            timestamp=datetime.now(),
            requires_response=False
        )

        await self.message_bus.send_message(message)

    async def emit_event(
        self,
        event_type: EventType,
        event_data: Dict[str, Any]
    ):
        """
        发布事件（广播给所有订阅者）

        Args:
            event_type: 事件类型
            event_data: 事件数据
        """
        message = Message(
            message_id=self._generate_message_id(),
            message_type=MessageType.EVENT,
            from_agent=self.agent_id,
            to_agent="*",  # 广播
            content={
                "event_type": event_type.value,
                **event_data
            },
            priority=MessagePriority.NORMAL,
            timestamp=datetime.now(),
            requires_response=False
        )

        await self.message_bus.send_message(message)

    def subscribe_event(
        self,
        event_type: EventType,
        handler: Callable
    ):
        """
        订阅事件

        Args:
            event_type: 事件类型
            handler: 事件处理函数
        """
        self.message_bus.subscribe(event_type.value, handler)

    def _generate_message_id(self) -> str:
        """生成消息ID"""
        import uuid
        return f"{self.agent_id}_{uuid.uuid4().hex[:8]}"


# 全局消息总线实例
message_bus = MessageBus()
