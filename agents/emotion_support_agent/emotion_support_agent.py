"""
Emotion Support Agent - 情绪支持Agent
提供非评判性、支持性的情绪引导，帮助用户建立健康的饮食心态
"""

from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class EmotionState(Enum):
    """情绪状态类型"""
    GUILT = "guilt"                    # 内疚（吃多了）
    ANXIETY = "anxiety"                # 焦虑（担心体重）
    FRUSTRATION = "frustration"        # 挫败（减重停滞）
    STRESS = "stress"                  # 压力（工作压力导致暴食）
    SATISFACTION = "satisfaction"      # 满足（进展顺利）
    NEUTRAL = "neutral"                # 中性


class RiskLevel(Enum):
    """饮食障碍风险等级"""
    NONE = "none"                      # 无风险
    LOW = "low"                        # 低风险
    MODERATE = "moderate"              # 中风险
    HIGH = "high"                      # 高风险（需要专业干预）


class EmotionSupportAgent:
    """
    Emotion Support Agent - 情绪支持

    核心原则：
    1. 不羞辱、不责备
    2. 允许合理放纵（弹性饮食）
    3. 提供具体的下一步建议
    4. 识别饮食障碍风险

    职责：
    1. 识别用户情绪状态
    2. 提供支持性回复
    3. 重构认知偏差
    4. 检测饮食障碍风险
    5. 必要时引导专业帮助
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.memory_agent = None
        self.safety_agent = None

    async def initialize(self, memory_agent, safety_agent):
        """初始化并注入依赖的Agent"""
        self.memory_agent = memory_agent
        self.safety_agent = safety_agent
        logger.info("Initialized Emotion Support Agent")

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """标准Agent接口"""
        action = request.get("action", "")
        params = request.get("params", {})

        try:
            if action == "detect_emotion":
                emotion = await self.detect_emotion(
                    user_id=params["user_id"],
                    user_message=params["message"],
                    context=params.get("context", {})
                )
                result = {"emotion": emotion.value, "confidence": 0.8}
            elif action == "provide_support":
                emotion = EmotionState(params.get("emotion", "neutral"))
                result = await self.provide_support(
                    user_id=params["user_id"],
                    emotion=emotion,
                    context=params.get("context", {})
                )
            elif action == "assess_eating_disorder_risk":
                emotion = EmotionState(params.get("emotion", "neutral"))
                risk = await self._assess_eating_disorder_risk(params["user_id"], emotion)
                result = {
                    "risk_level": risk.value,
                    "risk_factors": [],
                    "recommendations": []
                }
            elif action == "flexible_eating":
                result = await self.handle_flexible_eating(params["user_id"], params.get("situation", ""))
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Emotion Support Agent action {action} failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """健康检查"""
        return True

    async def detect_emotion(
        self,
        user_id: int,
        user_message: str,
        context: Dict[str, Any]
    ) -> EmotionState:
        """
        检测用户情绪状态

        通过关键词、语气、上下文判断情绪
        """
        message_lower = user_message.lower()

        # 内疚关键词
        guilt_keywords = ["吃多了", "又失败了", "控制不住", "后悔", "不该", "暴食", "破功"]
        if any(kw in message_lower for kw in guilt_keywords):
            return EmotionState.GUILT

        # 焦虑关键词
        anxiety_keywords = ["担心", "害怕", "紧张", "会不会", "怎么办", "焦虑", "反弹"]
        if any(kw in message_lower for kw in anxiety_keywords):
            return EmotionState.ANXIETY

        # 挫败关键词
        frustration_keywords = ["没用", "不行", "失败", "放弃", "太难了", "瓶颈", "停滞"]
        if any(kw in message_lower for kw in frustration_keywords):
            return EmotionState.FRUSTRATION

        # 压力关键词
        stress_keywords = ["压力", "烦", "累", "忙", "崩溃", "受不了"]
        if any(kw in message_lower for kw in stress_keywords):
            return EmotionState.STRESS

        # 满足/积极关键词
        satisfaction_keywords = ["开心", "满意", "瘦了", "成功", "顺利", "感谢"]
        if any(kw in message_lower for kw in satisfaction_keywords):
            return EmotionState.SATISFACTION

        return EmotionState.NEUTRAL

    async def provide_support(
        self,
        user_id: int,
        emotion: EmotionState,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        提供情绪支持

        Args:
            user_id: 用户ID
            emotion: 检测到的情绪
            context: 上下文（包括具体事件）

        Returns:
            {
                "message": "支持性回复",
                "action_suggestions": [...],
                "cognitive_reframe": "认知重构",
                "risk_level": RiskLevel
            }
        """
        # 1. 检查饮食障碍风险
        risk_level = await self._assess_eating_disorder_risk(user_id, emotion)

        # 2. 生成支持性回复
        response_text = self._generate_supportive_response(emotion, context, risk_level)

        # 3. 提供具体建议
        suggestions = self._generate_action_suggestions(emotion, context)

        # 4. 认知重构
        reframe = self._cognitive_reframe(emotion, context)

        result = {
            "message": response_text,
            "action_suggestions": suggestions,
            "cognitive_reframe": reframe,
            "risk_level": risk_level.value,
            "tone": "supportive"
        }

        # 5. 如果风险高，引导专业帮助
        if risk_level in [RiskLevel.MODERATE, RiskLevel.HIGH]:
            result["professional_help"] = self._generate_help_guidance(risk_level)

        # 记录情绪到Memory
        await self.track_emotion_pattern(user_id, emotion, trigger=context.get("trigger"))

        return result

    def _generate_supportive_response(
        self,
        emotion: EmotionState,
        context: Dict[str, Any],
        risk_level: RiskLevel
    ) -> str:
        """
        生成支持性回复

        根据不同情绪状态，提供不同的支持策略
        """
        if emotion == EmotionState.GUILT:
            return self._respond_to_guilt(context)
        elif emotion == EmotionState.ANXIETY:
            return self._respond_to_anxiety(context)
        elif emotion == EmotionState.FRUSTRATION:
            return self._respond_to_frustration(context)
        elif emotion == EmotionState.STRESS:
            return self._respond_to_stress(context)
        elif emotion == EmotionState.SATISFACTION:
            return "真为你高兴！继续保持，记得把这份成就感也记录下来。"
        else:
            return "我在这里陪伴你，随时可以和我聊聊。"

    def _respond_to_guilt(self, context: Dict[str, Any]) -> str:
        """
        回应内疚情绪

        核心策略：
        1. 验证情绪（acknowledge）
        2. 正常化经历（normalize）
        3. 重构认知（reframe）
        4. 提供前进方向（forward focus）
        """
        return (
            "今天吃得比计划多，这种感觉我理解。"
            "但这不代表你之前的努力失效了，也不需要通过少吃下一顿来'补偿'。"
            "\n\n"
            "身体需要稳定的能量供应。明天正常安排三餐，我会帮你调整搭配和份量。"
        )

    def _respond_to_anxiety(self, context: Dict[str, Any]) -> str:
        """回应焦虑情绪"""
        return (
            "担心体重变化是很正常的，但体重波动1-2kg是正常的生理现象（水分、食物残渣等）。"
            "\n\n"
            "我们更应该关注：你的精力如何？睡眠质量怎样？长期趋势是什么？"
            "这些比单次体重数字更重要。"
        )

    def _respond_to_frustration(self, context: Dict[str, Any]) -> str:
        """回应挫败情绪"""
        return (
            "遇到平台期或进展不如预期，确实让人沮丧。但这不是失败，而是身体在适应。"
            "\n\n"
            "我们可以一起回顾：\n"
            "- 睡眠是否充足？\n"
            "- 压力是否较大？\n"
            "- 营养搭配是否需要调整？\n"
            "\n小小的调整可能就能突破瓶颈。"
        )

    def _respond_to_stress(self, context: Dict[str, Any]) -> str:
        """回应压力情绪"""
        return (
            "压力大的时候想吃东西是身体的正常反应。"
            "\n\n"
            "除了饮食，你还可以尝试：\n"
            "- 深呼吸5分钟\n"
            "- 短暂散步\n"
            "- 喝一杯温水\n"
            "\n如果还是想吃，选择一些健康的零食是完全可以的。"
        )

    def _generate_action_suggestions(
        self,
        emotion: EmotionState,
        context: Dict[str, Any]
    ) -> List[str]:
        """
        生成具体行动建议

        避免空洞的鼓励，提供可执行的下一步
        """
        suggestions = []

        if emotion == EmotionState.GUILT:
            suggestions = [
                "正常安排下一餐，不要跳过或大幅减少",
                "今天多喝水，帮助身体代谢",
                "记录这次经历，思考触发因素（聚餐、压力、特殊场合）"
            ]
        elif emotion == EmotionState.ANXIETY:
            suggestions = [
                "把称重频率降低到每周1-2次",
                "每天记录睡眠质量和精力状态",
                "关注非体重指标：腰围、体脂率、照片对比"
            ]
        elif emotion == EmotionState.FRUSTRATION:
            suggestions = [
                "回顾过去一周的饮食记录，寻找模式",
                "增加一种新的运动形式",
                "调整宏量营养素比例（如提高蛋白质）"
            ]
        elif emotion == EmotionState.STRESS:
            suggestions = [
                "准备一些健康零食（坚果、水果）",
                "找到3种非食物的压力缓解方式",
                "考虑今天早点休息"
            ]
        elif emotion == EmotionState.SATISFACTION:
            suggestions = [
                "记录下这次成功的原因",
                "给自己一个小奖励（非食物类）",
                "把有效的做法固化到日常中"
            ]

        return suggestions

    def _cognitive_reframe(
        self,
        emotion: EmotionState,
        context: Dict[str, Any]
    ) -> str:
        """
        认知重构

        挑战不健康的思维模式
        """
        reframes = {
            EmotionState.GUILT: (
                "❌ \"我又失败了，我太没用了\"\n"
                "✅ \"我今天吃多了，但这不代表我是失败者。明天继续就好。\""
            ),
            EmotionState.ANXIETY: (
                "❌ \"体重涨了0.5kg，我的努力白费了\"\n"
                "✅ \"体重每天有波动是正常的，关注长期趋势更重要。\""
            ),
            EmotionState.FRUSTRATION: (
                "❌ \"一周都没变化，这个方法不适合我\"\n"
                "✅ \"平台期是减重过程的一部分，身体正在适应，我可以微调策略。\""
            ),
            EmotionState.STRESS: (
                "❌ \"我不该在压力下吃东西\"\n"
                "✅ \"压力下想吃是正常的，我可以选择更健康的方式缓解压力。\""
            )
        }

        return reframes.get(emotion, "")

    async def _assess_eating_disorder_risk(
        self,
        user_id: int,
        current_emotion: EmotionState
    ) -> RiskLevel:
        """
        评估饮食障碍风险

        风险信号：
        1. 频繁的内疚、焦虑情绪（每周>5次）
        2. 极端节食行为（<800 kcal/天持续>3天）
        3. 暴食-补偿循环
        4. 体重过低（BMI < 16）
        5. 对体重的过度关注（每日多次称重）
        """
        # 获取用户历史情绪记录
        memories = await self.memory_agent.recall(
            user_id,
            context={"intent": "emotion_history", "days": 7}
        )

        risk_factors = []
        risk_score = 0

        # 1. 统计近期负面情绪频率
        recent_emotions = memories.get("recent", [])
        negative_emotions = ["guilt", "anxiety", "frustration", "stress"]
        negative_count = sum(
            1 for e in recent_emotions
            if e.get("data", {}).get("emotion") in negative_emotions
        )

        if negative_count > 10:
            risk_score += 3
            risk_factors.append("一周内负面情绪超过10次")
        elif negative_count > 5:
            risk_score += 2
            risk_factors.append("一周内负面情绪超过5次")

        # 2. 检查极端行为模式
        # 从近期记忆中查找极低热量记录
        low_calorie_days = 0
        for mem in recent_emotions:
            data = mem.get("data", {})
            if data.get("daily_calories", 2000) < 800:
                low_calorie_days += 1
        if low_calorie_days >= 3:
            risk_score += 3
            risk_factors.append("连续多日极低热量摄入")

        # 3. 分析体重-情绪关联
        profile = memories.get("profile", {})
        current_bmi = profile.get("current_bmi", 22)
        if current_bmi < 16:
            risk_score += 4
            risk_factors.append("BMI过低")
        elif current_bmi < 18.5:
            risk_score += 1
            risk_factors.append("BMI偏低")

        # 4. 当前情绪严重度
        if current_emotion in [EmotionState.GUILT, EmotionState.ANXIETY]:
            risk_score += 1

        # 映射风险等级
        if risk_score >= 6:
            return RiskLevel.HIGH
        elif risk_score >= 3:
            return RiskLevel.MODERATE
        elif risk_score >= 1:
            return RiskLevel.LOW
        return RiskLevel.NONE

    def _generate_help_guidance(self, risk_level: RiskLevel) -> Dict[str, Any]:
        """
        生成专业帮助引导

        风险等级达到中高时，温和建议寻求专业支持
        """
        if risk_level == RiskLevel.HIGH:
            return {
                "message": (
                    "我注意到你最近的状态可能需要更专业的支持。"
                    "建议咨询营养师或心理咨询师，他们可以提供更深入的帮助。"
                ),
                "resources": [
                    "营养门诊挂号平台",
                    "心理咨询平台推荐",
                    "饮食障碍支持组织"
                ],
                "urgency": "建议尽快咨询"
            }
        elif risk_level == RiskLevel.MODERATE:
            return {
                "message": (
                    "如果这种状态持续，考虑和专业人士聊聊可能会有帮助。"
                ),
                "resources": [],
                "urgency": "可以考虑咨询"
            }
        else:
            return {}

    async def handle_flexible_eating(
        self,
        user_id: int,
        situation: str
    ) -> Dict[str, Any]:
        """
        处理弹性饮食场景

        允许用户在特殊场合合理"放纵"，避免过度限制导致暴食

        场景：
        - 朋友聚餐
        - 节日庆祝
        - 特殊场合
        """
        return {
            "permission": "是的，特殊场合可以享受美食",
            "guidance": [
                "不需要因为一顿聚餐而内疚",
                "明天恢复正常饮食即可",
                "享受当下，不要过度补偿"
            ],
            "boundaries": [
                "如果感觉不舒服可以停下",
                "喝酒要注意安全",
                "第二天不要跳过早餐"
            ]
        }

    async def track_emotion_pattern(
        self,
        user_id: int,
        emotion: EmotionState,
        trigger: Optional[str] = None
    ):
        """
        追踪情绪模式

        存储到Memory系统，用于：
        1. 识别情绪触发因素
        2. 评估饮食障碍风险
        3. 个性化情绪支持
        """
        await self.memory_agent.store(
            user_id=user_id,
            memory_type="emotion",
            data={
                "emotion": emotion.value,
                "trigger": trigger,
                "timestamp": datetime.now().isoformat()
            },
            importance_score=0.7 if emotion != EmotionState.NEUTRAL else 0.3
        )

        logger.info(f"Tracked emotion: user={user_id}, emotion={emotion.value}")
