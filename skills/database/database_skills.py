"""
数据库相关Skill
用于食物数据库查询、营养计算等
"""

from typing import Dict, Any, List
import logging
import os

import asyncpg
from dotenv import load_dotenv

from skills import BaseSkill

load_dotenv()

logger = logging.getLogger(__name__)


class FoodDatabaseMatchingSkill(BaseSkill):
    """
    食物数据库匹配Skill
    将识别的食物名称匹配到营养数据库
    """

    def __init__(self):
        super().__init__(name="food_database_matching", category="database")
        self.db = None

    async def _ensure_db(self):
        """确保数据库连接"""
        if self.db is None:
            database_url = os.getenv("DATABASE_URL")
            if database_url:
                self.db = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
            else:
                self.db = await asyncpg.create_pool(
                    host=os.getenv("POSTGRES_HOST", "localhost"),
                    port=int(os.getenv("POSTGRES_PORT", 5432)),
                    user=os.getenv("POSTGRES_USER", "postgres"),
                    password=os.getenv("POSTGRES_PASSWORD", ""),
                    database=os.getenv("POSTGRES_DB", "diet_assistant"),
                    min_size=1,
                    max_size=5
                )

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        匹配食物营养数据

        Input context:
            - detected_foods: 识别的食物列表

        Output:
            - matched_foods: List[{"name": "...", "nutrition": {...}}]
        """
        detected_foods = context.get("detected_foods", [])
        matched_foods = []

        try:
            await self._ensure_db()
        except Exception as e:
            logger.warning(f"Database not available for food matching: {e}")
            self.db = None

        for food in detected_foods:
            name = food.get("name", "")
            nutrition = await self._query_food_nutrition(name)
            matched_foods.append({
                "name": name,
                "nutrition": nutrition,
                "confidence": food.get("confidence", 0.8)
            })

        logger.info(f"Matched {len(matched_foods)} foods to nutrition database")
        return {"matched_foods": matched_foods}

    async def _query_food_nutrition(self, food_name: str) -> Dict[str, Any]:
        """查询食物营养数据"""
        if self.db:
            try:
                async with self.db.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT calories_per_100g, protein_per_100g, carbs_per_100g,
                               fat_per_100g, sodium_per_100g, fiber_per_100g
                        FROM food_nutrition
                        WHERE name = $1 OR $1 ILIKE '%' || name || '%'
                        LIMIT 1
                        """,
                        food_name
                    )

                if row:
                    return {
                        "calories_per_100g": row["calories_per_100g"],
                        "protein_per_100g": row["protein_per_100g"],
                        "carbs_per_100g": row["carbs_per_100g"],
                        "fat_per_100g": row["fat_per_100g"],
                        "sodium_per_100g": row["sodium_per_100g"],
                        "fiber_per_100g": row.get("fiber_per_100g", 0)
                    }
            except Exception as e:
                logger.error(f"Failed to query food nutrition: {e}")

        # 默认营养数据映射
        defaults = {
            "米饭": {"calories_per_100g": 116, "protein_per_100g": 2.6, "carbs_per_100g": 25.6, "fat_per_100g": 0.3, "sodium_per_100g": 2, "fiber_per_100g": 0.3},
            "红烧肉": {"calories_per_100g": 450, "protein_per_100g": 20, "carbs_per_100g": 10, "fat_per_100g": 35, "sodium_per_100g": 800, "fiber_per_100g": 0},
            "炒青菜": {"calories_per_100g": 80, "protein_per_100g": 3, "carbs_per_100g": 8, "fat_per_100g": 4, "sodium_per_100g": 200, "fiber_per_100g": 2},
            "清蒸鱼": {"calories_per_100g": 120, "protein_per_100g": 22, "carbs_per_100g": 0, "fat_per_100g": 3, "sodium_per_100g": 150, "fiber_per_100g": 0},
            "鸡胸肉": {"calories_per_100g": 165, "protein_per_100g": 31, "carbs_per_100g": 0, "fat_per_100g": 3.6, "sodium_per_100g": 74, "fiber_per_100g": 0},
            "鸡蛋": {"calories_per_100g": 155, "protein_per_100g": 13, "carbs_per_100g": 1.1, "fat_per_100g": 11, "sodium_per_100g": 124, "fiber_per_100g": 0},
            "豆腐": {"calories_per_100g": 76, "protein_per_100g": 8, "carbs_per_100g": 1.9, "fat_per_100g": 4.8, "sodium_per_100g": 7, "fiber_per_100g": 0.3},
        }

        for key, value in defaults.items():
            if key in food_name:
                return value

        return {
            "calories_per_100g": 150,
            "protein_per_100g": 8,
            "carbs_per_100g": 15,
            "fat_per_100g": 6,
            "sodium_per_100g": 200,
            "fiber_per_100g": 1
        }


class NutritionCalculationSkill(BaseSkill):
    """
    营养计算Skill
    根据食物和份量计算总营养
    """

    def __init__(self):
        super().__init__(name="nutrition_calculation", category="calculation")

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算总营养

        Input context:
            - matched_foods: 匹配的食物列表
            - portion_estimates: 份量估算（可选）

        Output:
            - total_nutrition: {"calories": 500, "protein": 35, ...}
        """
        matched_foods = context.get("matched_foods", [])
        portion_estimates = context.get("portion_estimates", [])

        # 创建份量映射
        portion_map = {}
        for estimate in portion_estimates:
            portion_map[estimate["food"]] = estimate["weight_g"]

        # 计算总营养
        total_nutrition = {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            "sodium": 0,
            "fiber": 0
        }

        for food in matched_foods:
            weight = portion_map.get(food["name"], 100)  # 默认100g
            nutrition = food["nutrition"]

            # 按份量计算
            factor = weight / 100

            total_nutrition["calories"] += nutrition["calories_per_100g"] * factor
            total_nutrition["protein"] += nutrition["protein_per_100g"] * factor
            total_nutrition["carbs"] += nutrition.get("carbs_per_100g", 0) * factor
            total_nutrition["fat"] += nutrition.get("fat_per_100g", 0) * factor
            total_nutrition["sodium"] += nutrition.get("sodium_per_100g", 0) * factor
            total_nutrition["fiber"] += nutrition.get("fiber_per_100g", 0) * factor

        # 四舍五入
        for key in total_nutrition:
            total_nutrition[key] = round(total_nutrition[key], 1)

        logger.info(f"Calculated total nutrition: {total_nutrition['calories']} kcal")

        return {"total_nutrition": total_nutrition}


class RecipeSearchSkill(BaseSkill):
    """
    菜谱搜索Skill
    从CookHero或其他数据源搜索菜谱
    """

    def __init__(self):
        super().__init__(name="recipe_search", category="database")
        self.recipe_db = None

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        搜索菜谱

        Input context:
            - query: 搜索关键词
            - filters: 过滤条件（可选）

        Output:
            - recipes: List[{"name": "...", "ingredients": [...], ...}]
        """
        query = context.get("query", "")
        filters = context.get("filters", {})

        # 调用CookHero
        cookhero_url = os.getenv("COOKHERO_API_URL", "http://localhost:8000")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{cookhero_url}/api/v1/recipes/search",
                    json={"query": query, "filters": filters}
                )
                if response.status_code == 200:
                    data = response.json()
                    recipes = data.get("recipes", data if isinstance(data, list) else [])
                    return {"recipes": recipes}
        except Exception as e:
            logger.warning(f"RecipeSearchSkill CookHero call failed: {e}")

        # 兜底模拟
        recipes = [
            {
                "name": "清蒸鲈鱼",
                "ingredients": ["鲈鱼", "姜", "葱", "料酒"],
                "cooking_time": 20,
                "difficulty": "简单",
                "nutrition": {"calories": 250, "protein": 35}
            }
        ]

        return {"recipes": recipes}


class CombinationScorerSkill(BaseSkill):
    """
    组合评分Skill
    对菜品组合进行多维度评分
    """

    def __init__(self):
        super().__init__(name="combination_scorer", category="calculation")

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        评分菜品组合

        Input context:
            - combinations: 组合列表
            - nutrition_gap: 营养缺口
            - user_preferences: 用户偏好

        Output:
            - scored_combinations: 排序后的组合列表
        """
        combinations = context.get("combinations", [])
        nutrition_gap = context.get("nutrition_gap", {})

        scored = []

        for combo in combinations:
            score = self._calculate_score(combo, nutrition_gap)
            combo["score"] = score
            scored.append(combo)

        # 按分数排序
        scored.sort(key=lambda x: x["score"], reverse=True)

        return {"scored_combinations": scored}

    def _calculate_score(
        self,
        combo: Dict[str, Any],
        nutrition_gap: Dict[str, Any]
    ) -> float:
        """
        计算组合评分

        评分函数：
        score = 0.30 * nutrition_gap_match +
                0.20 * calorie_budget_fit +
                0.15 * user_preference +
                0.10 * food_diversity +
                0.10 * satiety_index +
                0.05 * price_fit -
                0.10 * risk_penalty
        """
        nutrition = combo.get("nutrition", {})

        # 营养素缺口匹配
        matches = 0
        weights = {"protein": 0.4, "vegetables": 0.3, "carbs": 0.2, "fat": 0.1}
        for nutrient, weight in weights.items():
            gap_value = nutrition_gap.get(nutrient, 0)
            provided = nutrition.get(nutrient, 0)
            if gap_value > 0:
                ratio = min(provided / max(gap_value, 1), 1.5)
                matches += weight * (1 - abs(1 - ratio))
            else:
                matches += weight * (1 if provided < 10 else 0.3)

        # 热量预算匹配
        calorie_gap = nutrition_gap.get("calories", 0)
        combo_calories = nutrition.get("calories", 0)
        if calorie_gap > 0:
            calorie_fit = max(0, 1 - abs(calorie_gap - combo_calories) / max(calorie_gap, 200))
        else:
            calorie_fit = 1 if combo_calories < 200 else 0.3

        # 多样性
        dishes = combo.get("dishes", [])
        diversity = min(len(dishes) / 3.0, 1.0)

        # 饱腹感：蛋白质和纤维
        satiety = 0.0
        if combo_calories > 0:
            protein_ratio = nutrition.get("protein", 0) * 4 / combo_calories
            fiber_score = min(nutrition.get("fiber", 0) / 10, 1.0)
            satiety = min(protein_ratio * 2 + fiber_score * 0.3, 1.0)

        # 风险惩罚
        risk_penalty = 0.0
        sodium_available = nutrition_gap.get("sodium_available", 2300)
        if nutrition.get("sodium", 0) > sodium_available:
            risk_penalty = min((nutrition["sodium"] - sodium_available) / 1000, 1.0)

        # 价格适配（默认0.8）
        price_fit = 0.8

        # 用户偏好（默认0.7）
        user_preference = 0.7

        score = (
            0.30 * matches +
            0.20 * calorie_fit +
            0.15 * user_preference +
            0.10 * diversity +
            0.10 * satiety +
            0.05 * price_fit -
            0.10 * risk_penalty
        )

        return round(max(0, min(score, 1)), 3)
