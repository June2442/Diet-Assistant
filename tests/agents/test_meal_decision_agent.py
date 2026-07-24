"""
Meal Decision Agent 单元测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.meal_decision_agent.meal_decision_agent import MealDecisionAgent, MealScenario


@pytest.fixture
def meal_agent():
    skills = {"vision_food_detection": MagicMock(), "food_database_matching": MagicMock()}
    agent = MealDecisionAgent(skill_registry=skills)
    agent.memory_agent = AsyncMock()
    agent.health_agent = AsyncMock()
    agent.safety_agent = AsyncMock()
    return agent


@pytest.mark.asyncio
async def test_normalize_dishes(meal_agent):
    dishes = [
        {"name": "清蒸鱼", "nutrition": {"calories": 120, "protein": 22}},
        "未知菜品"
    ]
    normalized = meal_agent._normalize_dishes(dishes)

    assert len(normalized) == 2
    assert normalized[0]["name"] == "清蒸鱼"
    assert normalized[0]["calories"] == 120
    assert normalized[1]["name"] == "未知菜品"


@pytest.mark.asyncio
async def test_sum_nutrition(meal_agent):
    dishes = [
        {"name": "A", "calories": 100, "protein": 10},
        {"name": "B", "calories": 200, "protein": 20}
    ]
    total = meal_agent._sum_nutrition(dishes)

    assert total["calories"] == 300
    assert total["protein"] == 30


@pytest.mark.asyncio
async def test_generate_combinations(meal_agent):
    dishes = [
        {"name": "清蒸鱼", "calories": 250, "protein": 35, "carbs": 0, "fat": 12, "sodium": 400, "fiber": 0, "vegetables": 0},
        {"name": "炒青菜", "calories": 80, "protein": 3, "carbs": 8, "fat": 4, "sodium": 200, "fiber": 2, "vegetables": 200},
        {"name": "米饭", "calories": 116, "protein": 2.6, "carbs": 25.6, "fat": 0.3, "sodium": 2, "fiber": 0.3, "vegetables": 0}
    ]
    gap = {"calories": 700, "protein": 100, "carbs": 100, "fat": 30, "fiber": 15, "vegetables": 300, "sodium_available": 1000}

    combinations = await meal_agent._generate_combinations(dishes, gap)

    assert len(combinations) > 0
    assert all("dishes" in c and "score" in c and "nutrition" in c for c in combinations)
    # 应该按分数降序
    assert combinations[0]["score"] >= combinations[-1]["score"]


@pytest.mark.asyncio
async def test_recommend_dishes(meal_agent):
    meal_agent.memory_agent.recall = AsyncMock(return_value={
        "recent": [],
        "semantic": [],
        "events": [],
        "profile": {"allergies": [], "goal": "减脂"}
    })
    meal_agent.health_agent.get_current_state = AsyncMock(return_value={
        "gap": {"calories": 700, "protein": 100, "carbs": 100, "fat": 30, "fiber": 15, "vegetables": 300, "sodium_available": 1000}
    })
    meal_agent.safety_agent.filter_dishes = AsyncMock(side_effect=lambda dishes, profile: dishes)

    result = await meal_agent.recommend_dishes(
        user_id=1001,
        scenario=MealScenario.RESTAURANT_MENU,
        input_data={"available_dishes": ["清蒸鱼", "炒青菜", "米饭"]}
    )

    assert result["success"] is True
    assert len(result["recommendations"]) > 0
    assert result["context"]["scenario"] == "restaurant_menu"
