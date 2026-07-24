"""
Agent Orchestrator - 总调度器
负责接收用户输入，进行意图分类，并协调各个专业Agent的工作
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime, date
import logging
import os

from dotenv import load_dotenv

from agents.memory_agent.memory_agent import MemoryAgent
from agents.health_agent.health_agent import HealthAgent
from agents.meal_decision_agent.meal_decision_agent import MealDecisionAgent, MealScenario
from agents.recipe_agent.recipe_agent import RecipeAgent
from agents.emotion_support_agent.emotion_support_agent import EmotionSupportAgent
from agents.safety_agent.safety_agent import SafetyAgent
from skills import skill_registry
from skills.vision.vision_skills import VisionFoodDetectionSkill, VisionPortionEstimationSkill, OCRMenuParserSkill
from skills.database.database_skills import FoodDatabaseMatchingSkill, NutritionCalculationSkill, RecipeSearchSkill, CombinationScorerSkill

load_dotenv()

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """用户意图类型"""
    MEAL_RECORD_TEXT = "meal_record_text"          # 文字记录餐食
    MEAL_RECORD_PHOTO = "meal_record_photo"        # 拍照记录餐食
    MEAL_DECISION_MENU = "meal_decision_menu"      # 餐厅菜单选菜
    MEAL_DECISION_TAKEOUT = "meal_decision_takeout"  # 外卖平台选菜
    MEAL_DECISION_PHOTO = "meal_decision_photo"    # 用户拍的菜品照片
    RECIPE_QUERY = "recipe_query"                  # 查询菜谱做法
    HEALTH_UPDATE = "health_update"                # 更新健康数据
    NUTRITION_QUERY = "nutrition_query"            # 查询营养信息
    EMOTION_SUPPORT = "emotion_support"            # 情绪支持
    GENERAL_CHAT = "general_chat"                  # 一般对话


class AgentOrchestrator:
    """
    Agent总调度器

    职责：
    1. 接收用户输入
    2. 调用Intent Classification识别意图
    3. 根据意图动态路由到相应的Agent
    4. 聚合多个Agent的结果
    5. 返回最终响应
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.agents: Dict[str, Any] = {}
        self._openai_client = None

    async def initialize(self):
        """初始化所有Agent"""
        logger.info("Initializing Agent Orchestrator...")

        # 初始化OpenAI客户端（用于意图分类）
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=openai_key)
            except Exception as e:
                logger.warning(f"OpenAI client init failed in orchestrator: {e}")

        # 注册Skills
        self._register_skills()

        # 初始化Memory Agent
        memory_agent = MemoryAgent(
            db_config=self.config.get("db", {}),
            vector_store_config=self.config.get("vector_store", {})
        )
        await memory_agent.initialize()
        self.agents["memory"] = memory_agent

        # 初始化Health Agent
        health_agent = HealthAgent(db_config=self.config.get("db", {}))
        await health_agent.initialize(memory_agent=memory_agent)
        self.agents["health"] = health_agent

        # 初始化Safety Agent
        safety_agent = SafetyAgent(db_config=self.config.get("db", {}))
        await safety_agent.initialize()
        self.agents["safety"] = safety_agent

        # 初始化Meal Decision Agent
        meal_decision_agent = MealDecisionAgent(skill_registry=self.agents.get("skills", skill_registry))
        await meal_decision_agent.initialize(
            memory_agent=memory_agent,
            health_agent=health_agent,
            safety_agent=safety_agent
        )
        self.agents["meal_decision"] = meal_decision_agent

        # 初始化Recipe Agent
        recipe_agent = RecipeAgent(cookhero_config=self.config.get("cookhero", {}))
        await recipe_agent.initialize(memory_agent=memory_agent, health_agent=health_agent)
        self.agents["recipe"] = recipe_agent

        # 初始化Emotion Support Agent
        emotion_agent = EmotionSupportAgent(config=self.config.get("emotion", {}))
        await emotion_agent.initialize(memory_agent=memory_agent, safety_agent=safety_agent)
        self.agents["emotion_support"] = emotion_agent

        logger.info("All agents initialized successfully")

    def _register_skills(self):
        """注册所有可用Skill"""
        # Vision Skills
        skill_registry.register(VisionFoodDetectionSkill())
        skill_registry.register(VisionPortionEstimationSkill())
        skill_registry.register(OCRMenuParserSkill())

        # Database Skills
        skill_registry.register(FoodDatabaseMatchingSkill())
        skill_registry.register(NutritionCalculationSkill())
        skill_registry.register(RecipeSearchSkill())
        skill_registry.register(CombinationScorerSkill())

        # 让MealDecisionAgent可以使用skill_registry
        self.config.setdefault("skills", skill_registry)

    async def process(
        self,
        user_id: int,
        user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        处理用户输入的主入口

        Args:
            user_id: 用户ID
            user_input: 用户输入 {
                "text": "今天晚上吃什么？",
                "image_url": "...",
                "metadata": {...}
            }

        Returns:
            响应结果
        """
        try:
            # 1. 意图分类
            intent = await self.classify_intent(user_input)
            logger.info(f"Classified intent: {intent}")

            # 2. 根据意图路由到相应处理流程
            if intent == IntentType.MEAL_DECISION_MENU:
                return await self.handle_meal_decision(user_id, user_input, intent)
            elif intent == IntentType.MEAL_DECISION_TAKEOUT:
                return await self.handle_meal_decision(user_id, user_input, intent)
            elif intent == IntentType.MEAL_DECISION_PHOTO:
                return await self.handle_meal_decision(user_id, user_input, intent)
            elif intent == IntentType.MEAL_RECORD_TEXT or intent == IntentType.MEAL_RECORD_PHOTO:
                return await self.handle_meal_record(user_id, user_input, intent)
            elif intent == IntentType.RECIPE_QUERY:
                return await self.handle_recipe_query(user_id, user_input)
            elif intent == IntentType.HEALTH_UPDATE:
                return await self.handle_health_update(user_id, user_input)
            elif intent == IntentType.EMOTION_SUPPORT:
                return await self.handle_emotion_support(user_id, user_input)
            elif intent == IntentType.NUTRITION_QUERY:
                return await self.handle_nutrition_query(user_id, user_input)
            else:
                return await self.handle_general(user_id, user_input, intent)

        except Exception as e:
            logger.error(f"Error processing user input: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def classify_intent(self, user_input: Dict[str, Any]) -> IntentType:
        """
        意图分类

        优先使用LLM分类，失败时回退到规则分类
        """
        text = user_input.get("text", "")
        has_image = bool(user_input.get("image_url"))

        # 尝试LLM分类
        if self._openai_client:
            try:
                intent = await self._classify_with_llm(text, has_image)
                if intent:
                    return intent
            except Exception as e:
                logger.warning(f"LLM intent classification failed: {e}")

        # 规则分类
        text_lower = text.lower()

        if has_image:
            if any(k in text_lower for k in ["选", "吃什么", "推荐", "菜单", "点菜"]):
                return IntentType.MEAL_DECISION_MENU
            elif any(k in text_lower for k in ["外卖", "平台", "订餐"]):
                return IntentType.MEAL_DECISION_TAKEOUT
            elif any(k in text_lower for k in ["拍了", "照片", "这是什么", "吃了"]):
                return IntentType.MEAL_DECISION_PHOTO

        if any(k in text_lower for k in ["怎么做", "菜谱", "做法", "步骤", "烹饪"]):
            return IntentType.RECIPE_QUERY

        if any(k in text_lower for k in ["体重", "血压", "运动", "睡眠", "血糖", "体脂"]):
            return IntentType.HEALTH_UPDATE

        if any(k in text_lower for k in ["难受", "焦虑", "愧疚", "失败", "压力大", "吃多了", "后悔"]):
            return IntentType.EMOTION_SUPPORT

        if any(k in text_lower for k in ["热量", "蛋白质", "碳水", "脂肪", "营养", "吃了多少"]):
            return IntentType.NUTRITION_QUERY

        if any(k in text_lower for k in ["吃了", "记录", "早餐", "午餐", "晚餐", "加餐"]):
            return IntentType.MEAL_RECORD_TEXT

        return IntentType.GENERAL_CHAT

    async def _classify_with_llm(self, text: str, has_image: bool) -> Optional[IntentType]:
        """使用LLM进行意图分类"""
        intent_map = {
            "meal_record_text": IntentType.MEAL_RECORD_TEXT,
            "meal_record_photo": IntentType.MEAL_RECORD_PHOTO,
            "meal_decision_menu": IntentType.MEAL_DECISION_MENU,
            "meal_decision_takeout": IntentType.MEAL_DECISION_TAKEOUT,
            "meal_decision_photo": IntentType.MEAL_DECISION_PHOTO,
            "recipe_query": IntentType.RECIPE_QUERY,
            "health_update": IntentType.HEALTH_UPDATE,
            "nutrition_query": IntentType.NUTRITION_QUERY,
            "emotion_support": IntentType.EMOTION_SUPPORT,
            "general_chat": IntentType.GENERAL_CHAT
        }

        prompt = (
            "请根据用户输入判断意图，只返回一个JSON对象：{\"intent\": \"...\"}。"
            "可选意图：meal_record_text, meal_record_photo, meal_decision_menu, "
            "meal_decision_takeout, meal_decision_photo, recipe_query, health_update, "
            "nutrition_query, emotion_support, general_chat。\n\n"
            f"用户输入：{text}\n是否有图片：{'是' if has_image else '否'}"
        )

        response = await self._openai_client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=50
        )

        content = response.choices[0].message.content
        import json
        data = json.loads(content)
        intent_str = data.get("intent", "general_chat")
        return intent_map.get(intent_str)

    async def handle_meal_decision(
        self,
        user_id: int,
        user_input: Dict[str, Any],
        intent: IntentType
    ) -> Dict[str, Any]:
        """
        处理选菜决策

        工作流：
        1. Memory Agent召回相关记忆
        2. Health Agent获取营养状态
        3. Vision识别菜品（如果有图片）
        4. Safety Agent安全检查
        5. Meal Decision Agent生成推荐
        """
        scenario_map = {
            IntentType.MEAL_DECISION_MENU: MealScenario.RESTAURANT_MENU,
            IntentType.MEAL_DECISION_TAKEOUT: MealScenario.TAKEOUT_PLATFORM,
            IntentType.MEAL_DECISION_PHOTO: MealScenario.USER_PHOTO
        }
        scenario = scenario_map.get(intent, MealScenario.RESTAURANT_MENU)

        meal_agent = self.agents["meal_decision"]
        result = await meal_agent.recommend_dishes(
            user_id=user_id,
            scenario=scenario,
            input_data={
                "image_url": user_input.get("image_url"),
                "text": user_input.get("text"),
                "available_dishes": user_input.get("metadata", {}).get("available_dishes", [])
            }
        )

        # 安全检查推荐结果
        safety_agent = self.agents["safety"]
        if result.get("recommendations"):
            top_recommendation = result["recommendations"][0]
            safety_check = await safety_agent.check_recommendation(user_id, top_recommendation)
            result["safety_check"] = safety_check

        return {
            "success": True,
            "intent": intent.value,
            "response": self._format_meal_recommendation(result),
            "data": result
        }

    def _format_meal_recommendation(self, result: Dict[str, Any]) -> str:
        """格式化推荐结果为自然语言"""
        recommendations = result.get("recommendations", [])
        if not recommendations:
            return "抱歉，暂时没有合适的推荐。"

        top = recommendations[0]
        dishes = "、".join(top["dishes"])
        score = top.get("score", 0)
        explanation = top.get("explanation", "")
        warnings = top.get("warnings", [])

        text = f"推荐你选择：{dishes}\n\n"
        if explanation:
            text += f"推荐理由：{explanation}\n\n"
        text += f"营养匹配度：{score * 100:.0f}%\n"
        if warnings:
            text += "\n注意事项：\n" + "\n".join(warnings)

        return text

    async def handle_meal_record(
        self,
        user_id: int,
        user_input: Dict[str, Any],
        intent: IntentType
    ) -> Dict[str, Any]:
        """处理餐食记录"""
        memory_agent = self.agents["memory"]
        health_agent = self.agents["health"]

        # 记录到Memory
        await memory_agent.store(
            user_id=user_id,
            memory_type="meal_photo" if intent == IntentType.MEAL_RECORD_PHOTO else "chat",
            data={
                "text": user_input.get("text"),
                "image_url": user_input.get("image_url"),
                "source": "photo" if intent == IntentType.MEAL_RECORD_PHOTO else "manual",
                "recorded_at": datetime.now().isoformat()
            },
            importance_score=0.6
        )

        # 更新健康状态（如果有营养数据）
        metadata = user_input.get("metadata", {})
        if "nutrition" in metadata:
            # TODO: 写入meal_records表
            pass

        return {
            "success": True,
            "intent": intent.value,
            "response": "已记录你的餐食。继续加油！",
            "data": {"recorded": True}
        }

    async def handle_recipe_query(
        self,
        user_id: int,
        user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理菜谱查询"""
        recipe_agent = self.agents["recipe"]
        query = user_input.get("text", "")

        # 提取查询关键词（简单处理）
        query = query.replace("怎么做", "").replace("菜谱", "").replace("做法", "").strip()

        recipes = await recipe_agent.search_recipes(
            user_id=user_id,
            query=query,
            filters=user_input.get("metadata", {}).get("filters")
        )

        if not recipes:
            return {
                "success": True,
                "intent": IntentType.RECIPE_QUERY.value,
                "response": "暂时没找到相关菜谱，换个关键词试试？",
                "data": {"recipes": []}
            }

        top = recipes[0]
        response = f"找到了{len(recipes)}个相关菜谱，最推荐：{top['name']}\n\n"
        response += f"食材：{', '.join(top.get('ingredients', []))}\n"
        response += f"烹饪时间：{top.get('cooking_time', '?')}分钟\n"
        response += f"难度：{top.get('difficulty', '?')}"

        return {
            "success": True,
            "intent": IntentType.RECIPE_QUERY.value,
            "response": response,
            "data": {"recipes": recipes}
        }

    async def handle_health_update(
        self,
        user_id: int,
        user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理健康数据更新"""
        health_agent = self.agents["health"]

        metadata = user_input.get("metadata", {})
        data = metadata.get("health_data", {})

        # 尝试从文本中解析一些健康数据
        text = user_input.get("text", "")
        parsed = self._parse_health_data_from_text(text)
        data.update(parsed)

        if not data:
            # 只是查询健康状态
            state = await health_agent.get_current_state(user_id)
            return {
                "success": True,
                "intent": IntentType.HEALTH_UPDATE.value,
                "response": self._format_health_state(state),
                "data": state
            }

        result = await health_agent.update_daily_health(
            user_id=user_id,
            date_target=date.today(),
            data=data
        )

        return {
            "success": result.get("updated", False),
            "intent": IntentType.HEALTH_UPDATE.value,
            "response": "健康数据已更新，我会持续关注你的状态。",
            "data": result
        }

    def _parse_health_data_from_text(self, text: str) -> Dict[str, Any]:
        """从文本中解析健康数据（简单版）"""
        import re
        data = {}

        # 体重
        weight_match = re.search(r"体重[是为:]?\s*(\d+(?:\.\d+)?)\s*kg?", text)
        if weight_match:
            data["weight"] = float(weight_match.group(1))

        # 血压
        bp_match = re.search(r"血压[是为:]?\s*(\d{2,3}/\d{2,3})", text)
        if bp_match:
            data["blood_pressure"] = bp_match.group(1)

        # 睡眠
        sleep_match = re.search(r"睡眠[是为:]?\s*(\d+(?:\.\d+)?)\s*小时", text)
        if sleep_match:
            data["sleep_hours"] = float(sleep_match.group(1))

        return data

    def _format_health_state(self, state: Dict[str, Any]) -> str:
        """格式化健康状态为自然语言"""
        profile = state.get("profile", {})
        gap = state.get("gap", {})

        text = "你的当前健康状态：\n\n"
        text += f"今日已摄入：{state.get('today_intake', {}).get('calories', 0):.0f}kcal\n"
        text += f"今日目标：{state.get('target', {}).get('calories', 0):.0f}kcal\n"
        text += f"剩余热量预算：{state.get('calorie_budget', 0):.0f}kcal\n"
        text += f"蛋白质缺口：{gap.get('protein', 0):.0f}g\n"
        text += f"蔬菜缺口：{gap.get('vegetables', 0):.0f}g\n"
        text += f"当前体重：{profile.get('current_weight', '未知')}kg\n"
        text += f"目标：{profile.get('goal', '维持')}"

        return text

    async def handle_emotion_support(
        self,
        user_id: int,
        user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理情绪支持"""
        emotion_agent = self.agents["emotion_support"]

        text = user_input.get("text", "")
        emotion = await emotion_agent.detect_emotion(user_id, text, {})
        support = await emotion_agent.provide_support(user_id, emotion, {"trigger": text})

        return {
            "success": True,
            "intent": IntentType.EMOTION_SUPPORT.value,
            "response": support["message"],
            "data": support
        }

    async def handle_nutrition_query(
        self,
        user_id: int,
        user_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理营养查询"""
        health_agent = self.agents["health"]
        state = await health_agent.get_current_state(user_id)

        return {
            "success": True,
            "intent": IntentType.NUTRITION_QUERY.value,
            "response": self._format_health_state(state),
            "data": state
        }

    async def handle_general(
        self,
        user_id: int,
        user_input: Dict[str, Any],
        intent: IntentType
    ) -> Dict[str, Any]:
        """处理一般对话"""
        # 召回记忆以提供个性化回复
        memory_agent = self.agents["memory"]
        memories = await memory_agent.recall(
            user_id,
            context={"intent": "general_chat"}
        )

        goal = memories.get("profile", {}).get("goal", "健康饮食")

        return {
            "success": True,
            "intent": intent.value,
            "response": (
                f"我是你的饮食健康助手，正在陪你实现'{goal}'的目标。"
                "你可以问我：今天吃什么、这道菜怎么做、记录体重、或者聊聊情绪。"
            ),
            "data": {}
        }

    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有Agent健康状态"""
        results = {}
        for name, agent in self.agents.items():
            if hasattr(agent, "health_check"):
                try:
                    results[name] = await agent.health_check()
                except Exception as e:
                    logger.error(f"Health check failed for {name}: {e}")
                    results[name] = False
            else:
                results[name] = True
        return results
