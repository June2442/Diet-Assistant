"""
Health Agent 单元测试
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from agents.health_agent.health_agent import HealthAgent


@pytest.fixture
def health_agent():
    agent = HealthAgent(db_config={"database_url": "postgresql://mock"})
    agent.db = MagicMock()
    return agent


@pytest.mark.asyncio
async def test_calculate_bmi(health_agent):
    bmi = await health_agent.calculate_bmi(74, 178)
    assert bmi == 23.4


@pytest.mark.asyncio
async def test_calculate_nutrition_gap():
    agent = HealthAgent(db_config={})
    intake = {"calories": 1300, "protein": 45, "carbs": 120, "fat": 40, "fiber": 12, "vegetables": 180, "sodium": 1800}
    target = {"calories": 2000, "protein": 150, "carbs": 200, "fat": 67, "fiber": 25, "vegetables": 500, "sodium_limit": 2300}

    gap = agent.calculate_nutrition_gap(intake, target)

    assert gap["calories"] == 700
    assert gap["protein"] == 105
    assert gap["sodium_available"] == 500


@pytest.mark.asyncio
async def test_get_daily_intake_empty(health_agent):
    # 模拟空查询结果
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    health_agent.db.acquire = MagicMock()
    health_agent.db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    health_agent.db.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    intake = await health_agent.get_daily_intake(1001, date.today())

    assert intake["calories"] == 0
    assert intake["protein"] == 0


@pytest.mark.asyncio
async def test_calculate_daily_target():
    agent = HealthAgent(db_config={})
    agent.get_user_profile = AsyncMock(return_value={
        "age": 29,
        "gender": "male",
        "current_weight": 74,
        "height": 178,
        "goal": "减脂",
        "preferences": {"activity_factor": 1.375}
    })
    agent.get_daily_exercise = AsyncMock(return_value=None)
    agent._cache_target = AsyncMock()

    target = await agent.calculate_daily_target(1001, date.today())

    assert target["calories"] > 0
    assert target["protein"] == 148  # 74 * 2
    assert target["carbs"] > 0
    assert target["fat"] > 0


@pytest.mark.asyncio
async def test_process_get_current_state(health_agent):
    health_agent.get_current_state = AsyncMock(return_value={
        "profile": {"user_id": 1001},
        "today_intake": {"calories": 0},
        "target": {"calories": 2000},
        "gap": {"calories": 2000},
        "calorie_budget": 2000
    })

    result = await health_agent.process({
        "action": "get_current_state",
        "params": {"user_id": 1001}
    })

    assert result["success"] is True
    assert result["result"]["calorie_budget"] == 2000
