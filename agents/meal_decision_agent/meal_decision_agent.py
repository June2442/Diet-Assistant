"""
Meal Decision Agent - 智能选菜决策Agent
基于营养缺口和场景，动态推荐最合适的饮食组合
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from itertools import combinations
import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class MealScenario(Enum):
    """选菜场景"""
    RESTAURANT_MENU = "restaurant_menu"      # 餐厅菜单
    TAKEOUT_PLATFORM = "takeout_platform"    # 外卖平台
    USER_PHOTO = "user_photo"                # 用户拍的菜品
    RECIPE_BASED = "recipe_based"            # 基于菜谱


class MealDecisionAgent:
    """
    Meal Decision Agent - 智能选菜决策

    职责：
    1. 根据营养缺口推荐菜品组合
    2. 多场景支持（餐厅/外卖/用户照片）
    3. 动态Skill路由
    4. 生成可解释的推荐结果

    核心差异：
    - Recipe Agent: "这道菜怎么做？"
    - Meal Decision Agent: "现在该吃什么？"（基于身体状态）
    """

    def __init__(self, skill_registry: Dict[str, Any]):
        self.skills = skill_registry  # Skill注册表
        self.memory_agent = None
        self.health_agent = None
        self.safety_agent = None
        self._openai_client = None

    async def initialize(
        self,
        memory_agent,
        health_agent,
        safety_agent
    ):
        """初始化并注入依赖的Agent"""
        self.memory_agent = memory_agent
        self.health_agent = health_agent
        self.safety_agent = safety_agent

        # 可选初始化OpenAI客户端用于Vision和解释生成
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=openai_key)
            except Exception as e:
                logger.warning(f"OpenAI client init failed in MealDecisionAgent: {e}")

        logger.info("Initialized Meal Decision Agent")

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """标准Agent接口"""
        action = request.get("action", "")
        params = request.get("params", {})

        try:
            if action == "recommend":
                scenario = MealScenario(params.get("scenario", "restaurant_menu"))
                result = await self.recommend_dishes(
                    user_id=params["user_id"],
                    scenario=scenario,
                    input_data={
                        "image_url": params.get("image_url"),
                        "text": params.get("text"),
                        "available_dishes": params.get("available_dishes", [])
                    }
                )
            elif action == "adjust_plan":
                result = await self.adjust_plan(
                    user_id=params["user_id"],
                    reason=params.get("reason", "goal_change"),
                    adjustments=params.get("adjustments", {})
                )
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Meal Decision Agent action {action} failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def recommend_dishes(
        self,
        user_id: int,
        scenario: MealScenario,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        推荐菜品组合

        Args:
            user_id: 用户ID
            scenario: 场景类型
            input_data: {
                "image_url": "...",        # 可选
                "text": "...",             # 可选
                "available_dishes": [...], # 可选（已识别的菜品列表）
            }

        Returns:
            {
                "recommendations": [
                    {
                        "dishes": ["清蒸鱼", "炒青菜", "半碗米饭"],
                        "score": 0.92,
                        "nutrition": {...},
                        "explanation": "清蒸鱼补充蛋白质...",
                        "warnings": [...]
                    }
                ]
            }
        """
        # 1. 召回记忆
        memories = await self.memory_agent.recall(
            user_id,
            context={"intent": "meal_decision", "scenario": scenario.value}
        )

        # 2. 获取健康状态
        health_state = await self.health_agent.get_current_state(user_id)

        # 3. 根据场景动态路由Skill
        dishes = await self._route_and_detect_dishes(scenario, input_data)

        # 4. 安全检查
        safe_dishes = await self.safety_agent.filter_dishes(
            dishes,
            memories["profile"]
        )

        # 5. 组合评分
        combinations = await self._generate_combinations(
            safe_dishes,
            health_state["gap"]
        )

        # 6. 生成推荐（Top 3）
        recommendations = await self._explain_recommendations(
            combinations[:3],
            health_state,
            memories
        )

        return {
            "success": True,
            "recommendations": recommendations,
            "health_state": health_state,
            "context": {
                "scenario": scenario.value,
                "dishes_detected": len(dishes),
                "safe_dishes": len(safe_dishes)
            }
        }

    async def _route_and_detect_dishes(
        self,
        scenario: MealScenario,
        input_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        动态Skill路由 - 根据场景选择不同的检测Skill

        场景1: 餐厅菜单照片
            -> vision_food_detection
            -> food_database_matching
            -> nutrition_calculation

        场景2: 外卖平台截图
            -> ocr_menu_parser
            -> takeout_platform_api
            -> price_filter

        场景3: 用户拍的菜品
            -> vision_portion_estimation
            -> ingredient_detection
        """
        # 如果调用方已经提供菜品列表，直接使用
        available_dishes = input_data.get("available_dishes", [])
        if available_dishes:
            return self._normalize_dishes(available_dishes)

        image_url = input_data.get("image_url")

        # 场景1: 餐厅菜单
        if scenario == MealScenario.RESTAURANT_MENU and image_url:
            vision_skill = self.skills.get("vision_food_detection")
            db_skill = self.skills.get("food_database_matching")

            if vision_skill and db_skill:
                try:
                    vision_result = await vision_skill.execute({"image_url": image_url})
                    detected = vision_result.get("detected_foods", [])
                    db_result = await db_skill.execute({"detected_foods": detected})
                    return self._normalize_dishes(db_result.get("matched_foods", []))
                except Exception as e:
                    logger.error(f"Restaurant menu detection failed: {e}", exc_info=True)

            # 尝试OpenAI Vision直接识别
            return await self._call_openai_vision(image_url, "识别这张菜单中的所有菜品，返回菜品名称列表")

        # 场景2: 外卖平台
        elif scenario == MealScenario.TAKEOUT_PLATFORM and image_url:
            ocr_skill = self.skills.get("ocr_menu_parser")
            if ocr_skill:
                try:
                    ocr_result = await ocr_skill.execute({"image_url": image_url})
                    return self._normalize_dishes(ocr_result.get("parsed_dishes", []))
                except Exception as e:
                    logger.error(f"OCR menu parsing failed: {e}", exc_info=True)

            return await self._call_openai_vision(image_url, "从这张外卖平台截图中提取菜品名称和价格")

        # 场景3: 用户拍照
        elif scenario == MealScenario.USER_PHOTO and image_url:
            portion_skill = self.skills.get("vision_portion_estimation")
            if portion_skill:
                try:
                    portion_result = await portion_skill.execute({"image_url": image_url})
                    return self._normalize_dishes(portion_result.get("portion_estimates", []))
                except Exception as e:
                    logger.error(f"Portion estimation failed: {e}", exc_info=True)

            return await self._call_openai_vision(image_url, "识别这张照片中的食物，估算重量和营养")

        # 兜底：返回默认模拟菜品
        return [
            {"name": "清蒸鱼", "calories": 250, "protein": 35, "sodium": 400, "carbs": 0, "fat": 12},
            {"name": "炒青菜", "calories": 80, "protein": 3, "sodium": 200, "carbs": 8, "fat": 4},
            {"name": "米饭", "calories": 116, "protein": 2.6, "sodium": 2, "carbs": 25.6, "fat": 0.3},
            {"name": "红烧肉", "calories": 450, "protein": 20, "sodium": 800, "carbs": 10, "fat": 35},
        ]

    def _normalize_dishes(self, dishes: List[Any]) -> List[Dict[str, Any]]:
        """统一菜品数据格式"""
        normalized = []
        for dish in dishes:
            if isinstance(dish, str):
                normalized.append({
                    "name": dish,
                    "calories": 200,
                    "protein": 10,
                    "carbs": 20,
                    "fat": 8,
                    "sodium": 300,
                    "fiber": 2,
                    "vegetables": 0
                })
            elif isinstance(dish, dict):
                norm = {"name": dish.get("name", "未知菜品")}
                # 支持nutrition嵌套和扁平两种格式
                nutrition = dish.get("nutrition", dish)
                for key in ["calories", "protein", "carbs", "fat", "sodium", "fiber", "vegetables"]:
                    norm[key] = float(nutrition.get(key, 0)) if isinstance(nutrition, dict) else 0
                # 份量估算
                if "weight_g" in dish:
                    factor = dish["weight_g"] / 100
                    for key in ["calories", "protein", "carbs", "fat", "sodium", "fiber"]:
                        norm[key] = round(norm[key] * factor, 1)
                normalized.append(norm)
        return normalized

    async def _call_openai_vision(self, image_url: str, prompt: str) -> List[Dict[str, Any]]:
        """使用OpenAI Vision识别图片"""
        if not self._openai_client:
            return []

        try:
            response = await self._openai_client.chat.completions.create(
                model=os.getenv("VISION_MODEL", "gpt-4-vision-preview"),
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt + " 以JSON数组返回，每项包含name, calories, protein, carbs, fat, sodium。"},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            dishes = data.get("dishes", data if isinstance(data, list) else [])
            return self._normalize_dishes(dishes)
        except Exception as e:
            logger.error(f"OpenAI Vision call failed: {e}", exc_info=True)
            return []

    async def _generate_combinations(
        self,
        dishes: List[Dict[str, Any]],
        nutrition_gap: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        生成菜品组合方案

        评分函数：
        score = 0.30 * nutrition_gap_match +
                0.20 * calorie_budget_fit +
                0.15 * user_preference +
                0.10 * food_diversity +
                0.10 * satiety_index +
                0.05 * price_fit -
                0.10 * risk_penalty
        """
        combinations_list = []

        # 生成1-3道菜的所有组合
        for r in range(1, min(4, len(dishes) + 1)):
            for combo in combinations(dishes, r):
                nutrition = self._sum_nutrition(list(combo))
                score = self._calculate_score(nutrition, nutrition_gap, list(combo))
                combinations_list.append({
                    "dishes": [d["name"] for d in combo],
                    "nutrition": nutrition,
                    "score": score
                })

        # 按分数排序
        combinations_list.sort(key=lambda x: x["score"], reverse=True)
        return combinations_list

    def _sum_nutrition(self, dishes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算组合营养总和"""
        total = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "sodium": 0, "fiber": 0, "vegetables": 0}
        for dish in dishes:
            for key in total:
                total[key] += dish.get(key, 0)
        return {key: round(value, 1) for key, value in total.items()}

    def _calculate_score(
        self,
        combo_nutrition: Dict[str, Any],
        nutrition_gap: Dict[str, Any],
        dishes: List[Dict[str, Any]]
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
        # 营养素缺口匹配（蛋白质、蔬菜、碳水等）
        gap = nutrition_gap
        matches = 0
        weights = {"protein": 0.4, "vegetables": 0.3, "carbs": 0.2, "fat": 0.1}
        for nutrient, weight in weights.items():
            gap_value = gap.get(nutrient, 0)
            provided = combo_nutrition.get(nutrient, 0)
            if gap_value > 0:
                # 正缺口：提供越接近缺口越好，但不要超过太多
                ratio = min(provided / max(gap_value, 1), 1.5)
                matches += weight * (1 - abs(1 - ratio))
            else:
                # 已超标：提供越少越好
                matches += weight * (1 if provided < 10 else 0.3)

        # 热量预算匹配
        calorie_gap = gap.get("calories", 0)
        combo_calories = combo_nutrition.get("calories", 0)
        if calorie_gap > 0:
            calorie_fit = max(0, 1 - abs(calorie_gap - combo_calories) / max(calorie_gap, 200))
        else:
            calorie_fit = 1 if combo_calories < 200 else 0.3

        # 多样性：菜品数量、蛋白质/蔬菜/主食覆盖
        diversity = 0.0
        categories = set()
        for dish in dishes:
            name = dish.get("name", "")
            if any(k in name for k in ["饭", "面", "粥", "馒头", "红薯", "玉米"]):
                categories.add("staple")
            elif any(k in name for k in ["鱼", "肉", "鸡", "蛋", "虾", "豆腐"]):
                categories.add("protein")
            elif any(k in name for k in ["菜", "蔬", "瓜", "菇", "豆芽"]):
                categories.add("vegetable")
        diversity = len(categories) / 3.0

        # 饱腹感：蛋白质和纤维占比
        satiety = 0.0
        if combo_nutrition.get("calories", 0) > 0:
            protein_ratio = combo_nutrition.get("protein", 0) * 4 / combo_nutrition["calories"]
            fiber_score = min(combo_nutrition.get("fiber", 0) / 10, 1.0)
            satiety = min(protein_ratio * 2 + fiber_score * 0.3, 1.0)

        # 风险惩罚（钠超标等）
        risk_penalty = 0.0
        sodium_available = gap.get("sodium_available", 2300)
        if combo_nutrition.get("sodium", 0) > sodium_available:
            risk_penalty = min((combo_nutrition["sodium"] - sodium_available) / 1000, 1.0)

        # 价格适配（当前无价格数据，默认0.8）
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

    async def _explain_recommendations(
        self,
        combinations: List[Dict[str, Any]],
        health_state: Dict[str, Any],
        memories: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        生成推荐解释

        使用LLM生成人类可读的推荐理由
        """
        explained = []

        for combo in combinations:
            explanation = await self._generate_explanation_text(combo, health_state, memories)
            warnings = self._generate_warnings(combo, health_state)

            explained.append({
                "dishes": combo["dishes"],
                "score": combo["score"],
                "nutrition": combo["nutrition"],
                "explanation": explanation,
                "warnings": warnings
            })

        return explained

    async def _generate_explanation_text(
        self,
        combo: Dict[str, Any],
        health_state: Dict[str, Any],
        memories: Dict[str, Any]
    ) -> str:
        """生成推荐理由"""
        gap = health_state["gap"]
        nutrition = combo["nutrition"]

        # 尝试LLM生成
        if self._openai_client:
            try:
                prompt = (
                    f"为用户推荐菜品组合：{', '.join(combo['dishes'])}。"
                    f"组合营养：{nutrition}。"
                    f"用户当前营养缺口：{gap}。"
                    f"用户目标：{memories.get('profile', {}).get('goal', '维持')}。"
                    "请用1-2句话解释为什么推荐这个组合，简洁自然。"
                )
                response = await self._openai_client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=120
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"LLM explanation failed: {e}")

        # 模板化解释
        reasons = []
        if gap.get("protein", 0) > 0 and nutrition.get("protein", 0) >= 20:
            reasons.append(f"补充蛋白质缺口约{nutrition['protein']:.0f}g")

        if gap.get("vegetables", 0) > 0 and nutrition.get("vegetables", 0) >= 100:
            reasons.append(f"补充蔬菜约{nutrition['vegetables']:.0f}g")

        if gap.get("calories", 0) > 0:
            reasons.append(f"提供约{nutrition['calories']:.0f}kcal，匹配剩余热量预算")

        if nutrition.get("sodium", 0) < 600:
            reasons.append("整体低钠，适合长期健康管理")

        if combo["score"] > 0.85:
            reasons.append("营养均衡度高")

        return "；".join(reasons) if reasons else "营养均衡，适合当前需求"

    def _generate_warnings(
        self,
        combo: Dict[str, Any],
        health_state: Dict[str, Any]
    ) -> List[str]:
        """生成注意事项"""
        warnings = []
        nutrition = combo["nutrition"]
        gap = health_state["gap"]

        if nutrition.get("sodium", 0) > 1000:
            warnings.append("⚠️ 钠含量较高，建议减少酱料")

        if nutrition.get("calories", 0) > gap.get("calories", 0) > 0:
            warnings.append("⚠️ 热量略超预算，建议减少主食或控制份量")

        if nutrition.get("fat", 0) > gap.get("fat", 0) * 1.5 and gap.get("fat", 0) > 0:
            warnings.append("⚠️ 脂肪偏高，建议减少油腻菜品")

        return warnings

    async def adjust_plan(
        self,
        user_id: int,
        reason: str,
        adjustments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调整餐食计划

        例如：暴食后补偿、目标变更
        """
        health_state = await self.health_agent.get_current_state(user_id)
        gap = health_state["gap"]

        if reason == "overeating_compensation":
            # 下一餐适当减少热量，但不过度
            adjusted_target = {
                "calories": max(int(gap.get("calories", 0) * 0.7), 300),
                "protein": max(int(gap.get("protein", 0) * 0.8), 20),
                "carbs": max(int(gap.get("carbs", 0) * 0.6), 30),
                "fat": max(int(gap.get("fat", 0) * 0.7), 10)
            }
            suggestions = [
                "下一餐以蔬菜和蛋白质为主",
                "不要跳过正餐，避免引发暴食",
                "多喝水，帮助代谢"
            ]
        else:
            adjusted_target = {
                "calories": int(gap.get("calories", 0)),
                "protein": int(gap.get("protein", 0)),
                "carbs": int(gap.get("carbs", 0)),
                "fat": int(gap.get("fat", 0))
            }
            suggestions = ["按当前营养缺口正常安排即可"]

        return {
            "adjusted_target": adjusted_target,
            "reason": reason,
            "suggestions": suggestions
        }
