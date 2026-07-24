"""
Memory Agent 单元测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.memory_agent.memory_agent import MemoryAgent


@pytest.fixture
def memory_agent():
    agent = MemoryAgent(db_config={}, vector_store_config={})
    agent.db = MagicMock()
    return agent


@pytest.mark.asyncio
async def test_calculate_importance(memory_agent):
    score = await memory_agent.calculate_importance(
        1001,
        "health_update",
        {"weight": 73.5, "weight_change": -1.5}
    )

    assert 0 <= score <= 1
    assert score > 0.5  # 体重变化+健康更新应得高分


@pytest.mark.asyncio
async def test_generate_semantic_summary(memory_agent):
    memories = [
        {"type": "meal_photo", "data": {"dishes": ["鸡胸肉", "蔬菜"]}, "created_time": __import__("datetime").datetime.now()}
    ]

    summary = await memory_agent.generate_semantic_summary(memories)

    assert "category" in summary
    assert "summary" in summary
    assert "confidence" in summary


@pytest.mark.asyncio
async def test_process_store(memory_agent):
    memory_agent.store = AsyncMock(return_value="mem_123")

    result = await memory_agent.process({
        "action": "store",
        "params": {
            "user_id": 1001,
            "memory_type": "chat",
            "data": {"text": "今天吃得很少"}
        }
    })

    assert result["success"] is True
    assert result["result"]["memory_id"] == "mem_123"


@pytest.mark.asyncio
async def test_process_recall(memory_agent):
    memory_agent.recall = AsyncMock(return_value={
        "recent": [],
        "semantic": [],
        "events": [],
        "profile": {}
    })

    result = await memory_agent.process({
        "action": "recall",
        "params": {
            "user_id": 1001,
            "context": {"intent": "meal_decision"}
        }
    })

    assert result["success"] is True
    assert "recent" in result["result"]
