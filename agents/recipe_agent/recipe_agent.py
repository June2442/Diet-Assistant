"""
Recipe Agent - 菜谱专家Agent
调用CookHero作为数据源，提供个性化菜谱推荐
"""

from typing import Dict, Any, List, Optional
import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class CookHeroClient:
    """CookHero API客户端"""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def search(self, query: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """搜索菜谱"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                response = await client.post(
                    f"{self.base_url}/api/v1/recipes/search",
                    json={"query": query, "filters": filters or {}},
                    headers=headers
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("recipes", data if isinstance(data, list) else [])
                else:
                    logger.warning(f"CookHero search returned {response.status_code}: {response.text}")
                    return []
        except Exception as e:
            logger.error(f"CookHero search failed: {e}", exc_info=True)
            return []

    async def get_recipe(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """获取菜谱详情"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                response = await client.get(
                    f"{self.base_url}/api/v1/recipes/{recipe_id}",
                    headers=headers
                )

                if response.status_code == 200:
                    return response.json()
                return None
        except Exception as e:
            logger.error(f"CookHero get recipe failed: {e}", exc_info=True)
            return None


class RecipeAgent:
    """
    Recipe Agent - 菜谱专家

    职责：
    1. 菜谱检索（调用CookHero RAG）
    2. 烹饪指导
    3. 食材替换建议
    4. 难度评估
    5. 基于Memory的个性化过滤

    与Meal Decision Agent的区别：
    - Recipe Agent: "这道菜怎么做？"（菜谱查询）
    - Meal Decision Agent: "现在该吃什么？"（基于身体状态决策）
    """

    def __init__(self, cookhero_config: Optional[Dict[str, Any]] = None):
        self.cookhero_config = cookhero_config or {}
        self.cookhero_client: Optional[CookHeroClient] = None
        self.memory_agent = None
        self.health_agent = None

    async def initialize(self, memory_agent, health_agent):
        """初始化并注入依赖的Agent"""
        self.memory_agent = memory_agent
        self.health_agent = health_agent

        # 初始化CookHero客户端
        if os.getenv("COOKHERO_ENABLED", "True").lower() == "true":
            base_url = self.cookhero_config.get("api_url") or os.getenv("COOKHERO_API_URL", "http://localhost:8000")
            api_key = self.cookhero_config.get("api_key") or os.getenv("COOKHERO_API_KEY")
            self.cookhero_client = CookHeroClient(base_url=base_url, api_key=api_key)
            logger.info(f"CookHero client initialized: {base_url}")
        else:
            logger.info("CookHero integration disabled")

        logger.info("Initialized Recipe Agent")

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """标准Agent接口"""
        action = request.get("action", "")
        params = request.get("params", {})

        try:
            if action == "search_recipes":
                result = await self.search_recipes(
                    user_id=params["user_id"],
                    query=params["query"],
                    filters=params.get("filters")
                )
            elif action == "get_instructions":
                result = await self.get_cooking_instructions(
                    recipe_id=params["recipe_id"],
                    user_id=params.get("user_id")
                )
            elif action == "suggest_substitutes":
                result = await self.suggest_ingredient_substitutes(
                    recipe_id=params["recipe_id"],
                    ingredient=params["ingredient"],
                    reason=params.get("reason", "过敏")
                )
            elif action == "estimate_difficulty":
                result = await self.estimate_recipe_difficulty(
                    recipe_id=params["recipe_id"],
                    user_id=params["user_id"]
                )
            elif action == "track_usage":
                await self.track_recipe_usage(
                    user_id=params["user_id"],
                    recipe_id=params["recipe_id"],
                    feedback=params.get("feedback", {})
                )
                result = {"tracked": True}
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Recipe Agent action {action} failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """健康检查"""
        if not self.cookhero_client:
            return True
        try:
            recipes = await self.cookhero_client.search("test", {"limit": 1})
            return True
        except Exception as e:
            logger.error(f"Recipe Agent health check failed: {e}")
            return False

    async def search_recipes(
        self,
        user_id: int,
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索菜谱

        Args:
            user_id: 用户ID
            query: 搜索关键词（如："高蛋白低脂鸡胸肉"）
            filters: 过滤条件 {
                "difficulty": "简单",
                "cooking_time": "<30",
                "cuisine": "中餐"
            }

        Returns:
            菜谱列表
        """
        # 1. 获取用户健康状态和记忆
        health_state = await self.health_agent.get_current_state(user_id)
        memories = await self.memory_agent.recall(
            user_id,
            context={"intent": "recipe_query", "query": query}
        )

        # 2. 基于营养缺口调整搜索策略
        nutrition_gap = health_state["gap"]
        enhanced_query = self._enhance_query_with_nutrition(query, nutrition_gap)

        # 3. 调用CookHero RAG检索
        raw_recipes = await self._call_cookhero_rag(enhanced_query, filters)

        # 4. 基于用户偏好和历史过滤
        filtered_recipes = self._filter_by_preferences(
            raw_recipes,
            memories["profile"]
        )

        # 5. 基于营养适配度排序
        ranked_recipes = self._rank_by_nutrition_fit(
            filtered_recipes,
            nutrition_gap
        )

        logger.info(f"Found {len(ranked_recipes)} recipes for query: {query}")

        return ranked_recipes[:10]  # 返回Top 10

    def _enhance_query_with_nutrition(
        self,
        query: str,
        nutrition_gap: Dict[str, Any]
    ) -> str:
        """
        根据营养缺口增强搜索关键词

        例如：
        - query="鸡肉" + protein=-60 → "高蛋白鸡肉"
        - query="炒菜" + vegetables=-300 → "多蔬菜炒菜"
        """
        enhancements = []

        if nutrition_gap.get("protein", 0) < -50:
            enhancements.append("高蛋白")

        if nutrition_gap.get("vegetables", 0) < -200:
            enhancements.append("多蔬菜")

        if nutrition_gap.get("fiber", 0) < -10:
            enhancements.append("高纤维")

        if nutrition_gap.get("calories", 0) < -300:
            enhancements.append("低卡")

        if enhancements:
            return " ".join(enhancements) + " " + query
        return query

    async def _call_cookhero_rag(
        self,
        query: str,
        filters: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """调用CookHero的RAG检索"""
        if self.cookhero_client:
            recipes = await self.cookhero_client.search(query, filters)
            if recipes:
                return recipes

        # 兜底模拟数据
        return [
            {
                "recipe_id": "recipe_001",
                "name": "清蒸鲈鱼",
                "ingredients": ["鲈鱼 500g", "姜 20g", "葱 30g", "料酒 15ml"],
                "steps": [
                    "鲈鱼处理干净，两面划刀",
                    "姜葱铺在鱼身上",
                    "蒸锅水开后蒸8分钟"
                ],
                "cooking_time": 20,
                "difficulty": "简单",
                "cuisine": "中餐",
                "nutrition": {
                    "calories": 250,
                    "protein": 35,
                    "carbs": 0,
                    "fat": 12,
                    "sodium": 400
                }
            },
            {
                "recipe_id": "recipe_002",
                "name": "鸡胸肉沙拉",
                "ingredients": ["鸡胸肉 150g", "生菜 100g", "圣女果 50g"],
                "steps": ["鸡胸肉煎熟切片", "蔬菜洗净装盘", "淋上油醋汁"],
                "cooking_time": 15,
                "difficulty": "简单",
                "cuisine": "西餐",
                "nutrition": {
                    "calories": 200,
                    "protein": 30,
                    "carbs": 8,
                    "fat": 6,
                    "sodium": 200
                }
            }
        ]

    def _filter_by_preferences(
        self,
        recipes: List[Dict[str, Any]],
        user_profile: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """基于用户偏好过滤菜谱"""
        filtered = []

        for recipe in recipes:
            # 检查过敏原
            allergens = user_profile.get("allergies", []) if user_profile else []
            if self._contains_allergen(recipe, allergens):
                continue

            # 检查饮食偏好
            preferences = user_profile.get("preferences", {}) if user_profile else {}
            if not self._matches_preferences(recipe, preferences):
                continue

            filtered.append(recipe)

        return filtered

    def _contains_allergen(
        self,
        recipe: Dict[str, Any],
        allergens: List[str]
    ) -> bool:
        """检查菜谱是否包含过敏原"""
        ingredients = recipe.get("ingredients", [])
        ingredients_text = " ".join(str(i) for i in ingredients).lower()

        for allergen in allergens:
            if allergen.lower() in ingredients_text:
                return True

        return False

    def _matches_preferences(
        self,
        recipe: Dict[str, Any],
        preferences: Dict[str, Any]
    ) -> bool:
        """检查是否符合饮食偏好"""
        cuisine_pref = preferences.get("cuisine")
        if cuisine_pref and recipe.get("cuisine") != cuisine_pref:
            return False

        max_time = preferences.get("max_cooking_time")
        if max_time and recipe.get("cooking_time", 999) > max_time:
            return False

        difficulty_pref = preferences.get("difficulty")
        if difficulty_pref and recipe.get("difficulty") != difficulty_pref:
            return False

        return True

    def _rank_by_nutrition_fit(
        self,
        recipes: List[Dict[str, Any]],
        nutrition_gap: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """根据营养适配度排序"""
        for recipe in recipes:
            recipe["fit_score"] = self._calculate_nutrition_fit(
                recipe.get("nutrition", {}),
                nutrition_gap
            )

        # 按适配度排序
        return sorted(recipes, key=lambda r: r.get("fit_score", 0), reverse=True)

    def _calculate_nutrition_fit(
        self,
        recipe_nutrition: Dict[str, Any],
        nutrition_gap: Dict[str, Any]
    ) -> float:
        """
        计算营养适配度

        高蛋白菜谱 + 蛋白质缺口大 → 高分
        低卡菜谱 + 热量已超标 → 高分
        """
        score = 0.0

        # 蛋白质适配
        if nutrition_gap.get("protein", 0) < -30:
            score += recipe_nutrition.get("protein", 0) * 0.5

        # 热量适配
        calorie_gap = nutrition_gap.get("calories", 0)
        recipe_calories = recipe_nutrition.get("calories", 0)
        if calorie_gap > 0 and abs(recipe_calories - calorie_gap) < 200:
            score += 30
        elif calorie_gap < 0 and recipe_calories < 300:
            score += 30

        # 低钠适配（如果钠已超标）
        if nutrition_gap.get("sodium_available", 2300) < 500:
            if recipe_nutrition.get("sodium", 0) < 400:
                score += 20

        return score

    async def get_cooking_instructions(
        self,
        recipe_id: str,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取详细烹饪指导

        返回分步骤的详细说明，包括：
        - 食材处理技巧
        - 火候控制
        - 时间把握
        - 常见错误避免
        """
        if self.cookhero_client:
            recipe = await self.cookhero_client.get_recipe(recipe_id)
            if recipe:
                return {
                    "recipe_id": recipe_id,
                    "instructions": recipe.get("steps", []),
                    "tips": recipe.get("tips", []),
                    "video_url": recipe.get("video_url")
                }

        # 兜底模拟
        return {
            "recipe_id": recipe_id,
            "instructions": [
                "准备所有食材",
                "按菜谱步骤烹饪",
                "注意火候和时间控制"
            ],
            "tips": ["新手建议先用小火", "调味分多次加入"],
            "video_url": None
        }

    async def suggest_ingredient_substitutes(
        self,
        recipe_id: str,
        ingredient: str,
        reason: str
    ) -> List[Dict[str, Any]]:
        """
        建议食材替换

        Args:
            recipe_id: 菜谱ID
            ingredient: 要替换的食材
            reason: 替换原因（过敏/买不到/不喜欢）

        Returns:
            替换建议列表
        """
        # 基于食材数据库和营养相似度推荐
        substitutes_db = {
            "鸡胸肉": {
                "alternative": "鸡腿肉（去皮）",
                "reason": "蛋白质接近，口感更嫩",
                "impact": "热量和脂肪略高"
            },
            "牛肉": {
                "alternative": "瘦猪肉",
                "reason": "蛋白质和铁含量接近",
                "impact": "风味略有不同"
            },
            "牛奶": {
                "alternative": "无糖豆浆",
                "reason": "植物蛋白替代，适合乳糖不耐",
                "impact": "钙含量较低"
            },
            "鸡蛋": {
                "alternative": "豆腐",
                "reason": "植物蛋白替代，适合素食/过敏",
                "impact": "口感不同"
            },
            "花生": {
                "alternative": "腰果",
                "reason": "坚果类替代",
                "impact": "过敏风险仍存在，需确认"
            }
        }

        # 尝试获取菜谱以查看其他食材
        recipe = None
        if self.cookhero_client:
            recipe = await self.cookhero_client.get_recipe(recipe_id)

        # 默认返回
        default = {
            "original": ingredient,
            "substitute": substitutes_db.get(ingredient, {}).get("alternative", "同类食材"),
            "reason": f"因{reason}推荐替换",
            "impact": substitutes_db.get(ingredient, {}).get("impact", "营养和风味可能有差异")
        }

        return [default]

    async def estimate_recipe_difficulty(
        self,
        recipe_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        评估菜谱难度（个性化）

        根据用户的烹饪经验和历史记录，个性化评估难度
        """
        # 获取用户烹饪历史
        memories = await self.memory_agent.recall(
            user_id,
            context={"intent": "recipe_history"}
        )

        # 简单经验评估：做过的菜谱越多，经验越高
        recipe_history = [m for m in memories.get("recent", []) if m.get("memory_type") == "recipe_used"]
        experience_level = min(len(recipe_history) / 10, 1.0)  # 0-1

        recipe = None
        if self.cookhero_client:
            recipe = await self.cookhero_client.get_recipe(recipe_id)

        base_difficulty = recipe.get("difficulty", "简单") if recipe else "简单"
        base_time = recipe.get("cooking_time", 20) if recipe else 20

        # 根据经验调整
        if experience_level > 0.7:
            success_rate = 0.92
        elif experience_level > 0.3:
            success_rate = 0.85
        else:
            success_rate = 0.75

        return {
            "difficulty": base_difficulty,
            "estimated_time": base_time,
            "success_rate": round(success_rate, 2),
            "personalized_tips": [
                "先准备好所有食材再开始",
                "建议全程关注火候变化"
            ]
        }

    async def track_recipe_usage(
        self,
        user_id: int,
        recipe_id: str,
        feedback: Dict[str, Any]
    ):
        """
        追踪菜谱使用情况

        更新recipe_lifecycle表，用于：
        1. 个性化推荐
        2. 菜谱老化检测
        3. 用户画像更新
        """
        from datetime import date

        # 记录到Memory
        await self.memory_agent.store(
            user_id=user_id,
            memory_type="recipe_used",
            data={"recipe_id": recipe_id, "feedback": feedback},
            importance_score=0.5
        )

        # TODO: 更新数据库recipe_lifecycle
        logger.info(f"Tracked recipe usage: user={user_id}, recipe={recipe_id}")
