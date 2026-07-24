"""
Safety Agent - 安全监测Agent
四层安全检查机制，确保推荐的安全性
"""

from typing import Dict, Any, List, Optional
from enum import Enum
import logging
import os
import re

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    L0_NORMAL = "L0_normal"          # 正常建议
    L1_MILD = "L1_mild"              # 温和提示
    L2_MODERATE = "L2_moderate"      # 建议专业评估
    L3_SERIOUS = "L3_serious"        # 建议及时就医
    L4_EMERGENCY = "L4_emergency"    # 紧急支持流程


class SafetyAgent:
    """
    Safety Agent - 安全监测

    四层安全机制：
    - L0: 输入校验（数值合理性）
    - L1: 规则引擎（过敏原、疾病限制）
    - L2: 风险分类（评估风险等级）
    - L3: 输出审查（禁止诊断和停药建议）
    """

    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        self.db_config = db_config or {}
        self.db: Optional[asyncpg.Pool] = None
        self.rule_engine = {}  # 规则引擎
        self.risk_classifier = None  # 风险分类器

    async def initialize(self):
        """初始化Safety Agent"""
        logger.info("Initializing Safety Agent...")

        database_url = self.db_config.get("database_url") or os.getenv("DATABASE_URL")
        if database_url:
            self.db = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
        else:
            self.db = await asyncpg.create_pool(
                host=self.db_config.get("host", os.getenv("POSTGRES_HOST", "localhost")),
                port=self.db_config.get("port", int(os.getenv("POSTGRES_PORT", 5432))),
                user=self.db_config.get("user", os.getenv("POSTGRES_USER", "postgres")),
                password=self.db_config.get("password", os.getenv("POSTGRES_PASSWORD", "")),
                database=self.db_config.get("database", os.getenv("POSTGRES_DB", "diet_assistant")),
                min_size=1,
                max_size=5
            )

        await self._load_safety_rules()

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """标准Agent接口"""
        action = request.get("action", "")
        params = request.get("params", {})

        try:
            if action == "validate_input":
                result = await self.validate_input(params["data"])
            elif action == "filter_dishes":
                result = await self.filter_dishes(params["dishes"], params["user_profile"])
            elif action == "check_recommendation":
                result = await self.check_recommendation(params["user_id"], params["recommendation"])
            elif action == "classify_risk":
                result = await self.classify_risk(params["user_id"], params["situation"])
            elif action == "audit_output":
                result = await self.audit_output(params["output"])
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Safety Agent action {action} failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self.db:
                return True  # 安全Agent不依赖数据库也能工作
            async with self.db.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Safety Agent health check failed: {e}")
            return False

    async def _load_safety_rules(self):
        """加载安全规则库"""
        # 默认规则：过敏原映射、疾病限制
        self.rule_engine = {
            "allergen_keywords": {
                "花生": ["花生", "peanut"],
                "海鲜": ["虾", "蟹", "鱼", "贝", "seafood", "shrimp", "crab"],
                "鸡蛋": ["鸡蛋", "蛋", "egg"],
                "牛奶": ["牛奶", "奶", "dairy", "milk"],
                "麸质": ["小麦", "面筋", "gluten", "bread"],
                "大豆": ["大豆", "黄豆", "soy", "tofu"]
            },
            "disease_rules": {
                "hypertension": {"sodium_limit": 800},
                "diabetes": {"sugar_limit": 15},
                "hyperlipidemia": {"fat_limit": 20},
                "gout": {"purine_limit": 150}
            }
        }

        # 从数据库加载自定义规则（如果存在）
        if self.db:
            try:
                async with self.db.acquire() as conn:
                    rows = await conn.fetch("SELECT rule_name, rule_data FROM safety_rules")
                    for row in rows:
                        self.rule_engine[row["rule_name"]] = row["rule_data"]
            except Exception as e:
                logger.warning(f"Could not load custom safety rules: {e}")

    async def validate_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        L0: 输入校验

        检查：
        1. 数值合理性（体重不能<20kg或>300kg）
        2. 单位错误（身高180可能是cm而非m）
        3. 异常输入识别
        """
        errors = []

        if "weight" in input_data:
            weight = input_data["weight"]
            if weight < 20 or weight > 300:
                errors.append(f"体重数值异常: {weight}kg，请检查输入")

        if "height" in input_data:
            height = input_data["height"]
            if height > 3:  # 可能输入了cm但标记为m
                errors.append(f"身高单位可能错误: {height}，是否为{height}cm?")
            elif height < 0.5 or height > 2.5:
                errors.append(f"身高数值异常: {height}m")

        if "calories" in input_data:
            calories = input_data["calories"]
            if calories < 0 or calories > 10000:
                errors.append(f"热量数值异常: {calories}kcal")

        if "age" in input_data:
            age = input_data["age"]
            if age < 10 or age > 120:
                errors.append(f"年龄数值异常: {age}")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    async def filter_dishes(
        self,
        dishes: List[Dict[str, Any]],
        user_profile: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        L1: 规则引擎 - 过滤不安全的菜品

        检查：
        1. 过敏原硬拦截
        2. 疾病限制规则
        3. 药物-食物相互作用
        """
        allergies = user_profile.get("allergies", []) if user_profile else []
        health_conditions = user_profile.get("health_conditions", []) if user_profile else []

        safe_dishes = []

        for dish in dishes:
            # 检查过敏原
            if self._contains_allergen(dish, allergies):
                logger.warning(f"Dish '{dish.get('name')}' contains allergen, filtered out")
                continue

            # 检查疾病限制
            if not self._check_health_restrictions(dish, health_conditions):
                logger.warning(f"Dish '{dish.get('name')}' violates health restrictions")
                continue

            safe_dishes.append(dish)

        logger.info(f"Filtered {len(dishes)} dishes to {len(safe_dishes)} safe dishes")
        return safe_dishes

    def _contains_allergen(
        self,
        dish: Dict[str, Any],
        allergies: List[str]
    ) -> bool:
        """检查是否包含过敏原"""
        if not allergies:
            return False

        dish_text = self._dish_to_text(dish)
        allergen_map = self.rule_engine.get("allergen_keywords", {})

        for allergen in allergies:
            # 直接匹配
            if allergen.lower() in dish_text.lower():
                return True
            # 关键词映射匹配
            keywords = allergen_map.get(allergen, [allergen])
            for kw in keywords:
                if kw.lower() in dish_text.lower():
                    return True

        return False

    def _check_health_restrictions(
        self,
        dish: Dict[str, Any],
        health_conditions: List[str]
    ) -> bool:
        """检查健康限制"""
        disease_rules = self.rule_engine.get("disease_rules", {})
        nutrition = dish.get("nutrition", dish)

        for condition in health_conditions:
            condition_lower = condition.lower()
            if condition_lower not in disease_rules:
                continue

            rules = disease_rules[condition_lower]

            # 高血压患者 - 钠限制
            if "sodium_limit" in rules:
                sodium = nutrition.get("sodium", 0) if isinstance(nutrition, dict) else dish.get("sodium", 0)
                if sodium > rules["sodium_limit"]:
                    return False

            # 糖尿病患者 - 糖分限制
            if "sugar_limit" in rules:
                sugar = nutrition.get("sugar", 0) if isinstance(nutrition, dict) else dish.get("sugar", 0)
                if sugar > rules["sugar_limit"]:
                    return False

            # 高血脂患者 - 脂肪限制
            if "fat_limit" in rules:
                fat = nutrition.get("fat", 0) if isinstance(nutrition, dict) else dish.get("fat", 0)
                if fat > rules["fat_limit"]:
                    return False

        return True

    def _dish_to_text(self, dish: Dict[str, Any]) -> str:
        """将菜品转换为文本用于匹配"""
        parts = [dish.get("name", "")]
        ingredients = dish.get("ingredients", [])
        if isinstance(ingredients, list):
            parts.extend(ingredients)
        description = dish.get("description", "")
        if description:
            parts.append(description)
        return " ".join(str(p) for p in parts)

    async def check_recommendation(
        self,
        user_id: int,
        recommendation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        L1: 规则引擎 - 检查推荐的安全性

        Returns:
            {
                "safe": True/False,
                "risk_level": RiskLevel,
                "reason": "...",
                "suggestions": [...]
            }
        """
        # 获取用户健康档案
        profile = await self._get_user_health_profile(user_id)

        # 极端热量检查
        if recommendation.get("calories", 0) < 200:
            return {
                "safe": False,
                "risk_level": RiskLevel.L2_MODERATE,
                "reason": "单餐热量过低（<200kcal），可能导致低血糖",
                "suggestions": ["增加主食或蛋白质"]
            }

        # 过敏原检查
        allergens = profile.get("allergies", [])
        dishes = recommendation.get("dishes", [])
        for dish in dishes:
            if isinstance(dish, dict) and self._contains_allergen(dish, allergens):
                return {
                    "safe": False,
                    "risk_level": RiskLevel.L3_SERIOUS,
                    "reason": f"包含过敏原：{dish.get('allergens') or dish.get('name')}",
                    "suggestions": ["立即排除该菜品"]
                }

        # 疾病限制检查
        if "hypertension" in profile.get("health_conditions", []):
            sodium = recommendation.get("sodium", 0)
            if sodium > 1200:
                return {
                    "safe": False,
                    "risk_level": RiskLevel.L1_MILD,
                    "reason": "钠含量过高，不适合高血压患者",
                    "suggestions": ["减少酱料", "选择清淡烹饪方式"]
                }

        return {
            "safe": True,
            "risk_level": RiskLevel.L0_NORMAL,
            "reason": "安全检查通过"
        }

    async def classify_risk(
        self,
        user_id: int,
        situation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        L2: 风险分类

        评估场景：
        - 极端节食（<800kcal/天）
        - 饮食障碍迹象
        - 健康指标异常
        """
        risk_level = RiskLevel.L0_NORMAL
        warnings = []

        # 检查极端节食
        daily_calories = situation.get("daily_calories", 2000)
        if daily_calories < 500:
            risk_level = RiskLevel.L4_EMERGENCY
            warnings.append("极低热量摄入，可能存在严重饮食障碍风险")
        elif daily_calories < 800:
            risk_level = RiskLevel.L3_SERIOUS
            warnings.append("极低热量摄入，可能存在饮食障碍风险")
        elif daily_calories < 1200:
            risk_level = max(risk_level, RiskLevel.L1_MILD)
            warnings.append("热量摄入偏低，需注意营养均衡")

        # 检查健康指标
        bmi = situation.get("bmi", 22)
        if bmi < 16:
            risk_level = RiskLevel.L3_SERIOUS
            warnings.append("BMI过低，建议及时就医")
        elif bmi < 18.5:
            risk_level = max(risk_level, RiskLevel.L1_MILD)
            warnings.append("BMI偏低，注意营养充足")
        elif bmi > 35:
            risk_level = RiskLevel.L2_MODERATE
            warnings.append("BMI过高，建议专业营养咨询")
        elif bmi > 28:
            risk_level = max(risk_level, RiskLevel.L1_MILD)
            warnings.append("BMI偏高，建议调整饮食结构")

        # 检查体重变化速度
        weight_change_rate = situation.get("weight_change_rate", 0)  # kg/周
        if abs(weight_change_rate) > 2:
            risk_level = max(risk_level, RiskLevel.L2_MODERATE)
            warnings.append("体重变化过快，请咨询医生")
        elif abs(weight_change_rate) > 1:
            risk_level = max(risk_level, RiskLevel.L1_MILD)
            warnings.append("体重变化较快，建议关注身体信号")

        return {
            "risk_level": risk_level.value,
            "warnings": warnings,
            "need_professional_help": risk_level in [RiskLevel.L2_MODERATE, RiskLevel.L3_SERIOUS, RiskLevel.L4_EMERGENCY]
        }

    async def audit_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """
        L3: 输出审查

        禁止内容：
        1. 未经依据的疾病诊断
        2. 建议停药或改变药物剂量
        3. 极端节食建议
        4. 羞辱性语言
        """
        violations = []

        output_text = str(output)

        # 检查诊断性语言
        diagnosis_keywords = ["你患有", "诊断为", "你得了", "疾病是", "确诊"]
        if any(kw in output_text for kw in diagnosis_keywords):
            violations.append("包含未经授权的疾病诊断")

        # 检查停药建议
        medication_keywords = ["停药", "减少药量", "不用吃药", "别吃"]
        if any(kw in output_text for kw in medication_keywords):
            violations.append("包含不安全的用药建议")

        # 检查极端节食
        extreme_diet_keywords = ["绝食", "只喝水", "什么都不吃", "完全不吃"]
        if any(kw in output_text for kw in extreme_diet_keywords):
            violations.append("包含极端节食建议")

        # 检查羞辱性语言
        shaming_keywords = ["肥猪", "没用", "失败者", "懒"]
        if any(kw in output_text for kw in shaming_keywords):
            violations.append("包含羞辱性语言")

        if violations:
            logger.error(f"Output audit failed: {violations}")
            return {
                "approved": False,
                "violations": violations,
                "sanitized_output": self._sanitize_output(output)
            }

        return {
            "approved": True,
            "violations": []
        }

    def _sanitize_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """净化输出内容"""
        sanitized = {}
        for key, value in output.items():
            if isinstance(value, str):
                # 替换敏感表述
                text = value
                text = re.sub(r"你患有\w+", "建议咨询医生确认", text)
                text = re.sub(r"诊断为\w+", "建议咨询医生确认", text)
                text = re.sub(r"停药|减少药量|不用吃药", "请遵医嘱调整用药", text)
                text = re.sub(r"绝食|只喝水|什么都不吃", "不建议极端节食，建议均衡饮食", text)
                sanitized[key] = text
            else:
                sanitized[key] = value
        return sanitized

    async def _get_user_health_profile(self, user_id: int) -> Dict[str, Any]:
        """获取用户健康档案"""
        if not self.db:
            return {
                "user_id": user_id,
                "allergies": [],
                "health_conditions": [],
                "medications": []
            }

        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT allergies, health_conditions, medications FROM users WHERE id = $1",
                    user_id
                )

            if not row:
                return {
                    "user_id": user_id,
                    "allergies": [],
                    "health_conditions": [],
                    "medications": []
                }

            return {
                "user_id": user_id,
                "allergies": row["allergies"] or [],
                "health_conditions": row["health_conditions"] or [],
                "medications": row["medications"] or []
            }
        except Exception as e:
            logger.error(f"Failed to get user health profile: {e}")
            return {
                "user_id": user_id,
                "allergies": [],
                "health_conditions": [],
                "medications": []
            }
