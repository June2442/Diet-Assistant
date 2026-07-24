"""
Health Agent - 健康状态管理Agent
负责健康数据追踪、营养状态计算、营养缺口分析
"""

from typing import Dict, Any, Optional
from datetime import date, datetime, timedelta
import logging
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class HealthAgent:
    """
    Health Agent - 健康管理

    职责：
    1. 每日健康数据收集（体重、血压、运动）
    2. 营养状态计算
    3. 营养缺口分析
    4. 动态热量预算
    """

    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        self.db_config = db_config or {}
        self.db: Optional[asyncpg.Pool] = None

    async def initialize(self, memory_agent=None):
        """初始化Health Agent"""
        logger.info("Initializing Health Agent...")
        self.memory_agent = memory_agent

        # 优先使用传入配置，否则从环境变量读取
        database_url = self.db_config.get("database_url") or os.getenv("DATABASE_URL")
        if database_url:
            self.db = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
        else:
            self.db = await asyncpg.create_pool(
                host=self.db_config.get("host", os.getenv("POSTGRES_HOST", "localhost")),
                port=self.db_config.get("port", int(os.getenv("POSTGRES_PORT", 5432))),
                user=self.db_config.get("user", os.getenv("POSTGRES_USER", "postgres")),
                password=self.db_config.get("password", os.getenv("POSTGRES_PASSWORD", "")),
                database=self.db_config.get("database", os.getenv("POSTGRES_DB", "diet_assistant")),
                min_size=1,
                max_size=10
            )
        logger.info("Health Agent database pool initialized")

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准Agent接口：处理请求

        Request:
            {"action": str, "params": dict, "context": dict}
        """
        action = request.get("action", "")
        params = request.get("params", {})

        try:
            if action == "get_current_state":
                result = await self.get_current_state(params["user_id"])
            elif action == "update_daily_health":
                result = await self.update_daily_health(
                    params["user_id"],
                    datetime.strptime(params["date"], "%Y-%m-%d").date() if "date" in params else date.today(),
                    params["data"]
                )
            elif action == "calculate_gap":
                today_intake = await self.get_daily_intake(
                    params["user_id"],
                    datetime.strptime(params["date"], "%Y-%m-%d").date() if "date" in params else date.today()
                )
                target = await self.calculate_daily_target(
                    params["user_id"],
                    datetime.strptime(params["date"], "%Y-%m-%d").date() if "date" in params else date.today()
                )
                result = self.calculate_nutrition_gap(today_intake, target)
            elif action == "get_weight_trend":
                result = await self.get_weight_trend(params["user_id"], params.get("days", 30))
            elif action == "calculate_bmi":
                result = {"bmi": await self.calculate_bmi(params["weight"], params["height"])}
            elif action == "get_user_profile":
                result = await self.get_user_profile(params["user_id"])
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Health Agent action {action} failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self.db:
                return False
            async with self.db.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Health Agent health check failed: {e}")
            return False

    async def get_current_state(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户当前健康状态

        Returns:
            {
                "profile": {...},           # 用户画像
                "today_intake": {...},      # 今日摄入
                "target": {...},            # 今日目标
                "gap": {...},               # 营养缺口
                "calorie_budget": 700       # 剩余热量预算
            }
        """
        profile = await self.get_user_profile(user_id)
        today_intake = await self.get_daily_intake(user_id, date.today())
        target = await self.calculate_daily_target(user_id, date.today())
        gap = self.calculate_nutrition_gap(today_intake, target)

        return {
            "profile": profile,
            "today_intake": today_intake,
            "target": target,
            "gap": gap,
            "calorie_budget": gap.get("calories", 0)
        }

    async def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """获取用户基础画像"""
        if not self.db:
            return self._default_profile(user_id)

        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT id, username, email, age, gender, height,
                           goal, target_weight, health_conditions, allergies,
                           medications, preferences
                    FROM users
                    WHERE id = $1
                    """,
                    user_id
                )

            if not row:
                return self._default_profile(user_id)

            current_weight = await self._get_latest_weight(user_id)

            profile = {
                "user_id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "age": row["age"] or 29,
                "gender": (row["gender"] or "male").lower(),
                "height": row["height"] or 178,
                "current_weight": current_weight,
                "target_weight": row["target_weight"],
                "bmi": await self.calculate_bmi(current_weight, row["height"] or 178),
                "goal": row["goal"] or "维持",
                "health_conditions": row["health_conditions"] or [],
                "allergies": row["allergies"] or [],
                "medications": row["medications"] or [],
                "preferences": row["preferences"] or {}
            }
            return profile

        except Exception as e:
            logger.error(f"Failed to get user profile for {user_id}: {e}", exc_info=True)
            return self._default_profile(user_id)

    def _default_profile(self, user_id: int) -> Dict[str, Any]:
        """默认用户画像（当数据库不可用时）"""
        return {
            "user_id": user_id,
            "age": 29,
            "gender": "male",
            "height": 178,
            "current_weight": 74,
            "target_weight": 70,
            "bmi": 23.4,
            "goal": "减脂保肌",
            "health_conditions": [],
            "allergies": []
        }

    async def _get_latest_weight(self, user_id: int) -> float:
        """获取用户最新体重"""
        if not self.db:
            return 74.0

        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT weight FROM daily_health_state
                    WHERE user_id = $1 AND weight IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    user_id
                )
            return row["weight"] if row else 74.0
        except Exception as e:
            logger.error(f"Failed to get latest weight: {e}")
            return 74.0

    async def get_daily_intake(self, user_id: int, date_target: date) -> Dict[str, Any]:
        """
        获取某日的营养摄入

        Returns:
            {
                "calories": 1300,
                "protein": 45,
                "carbs": 120,
                "fat": 40,
                "fiber": 12,
                "vegetables": 180,
                "sodium": 1800
            }
        """
        if not self.db:
            return self._empty_intake()

        try:
            start = datetime.combine(date_target, datetime.min.time())
            end = start + timedelta(days=1)

            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT total_nutrition FROM meal_records
                    WHERE user_id = $1 AND meal_time >= $2 AND meal_time < $3
                    """,
                    user_id, start, end
                )

            total = self._empty_intake()
            for row in rows:
                nutrition = row["total_nutrition"] or {}
                for key in total:
                    if key in nutrition:
                        total[key] += float(nutrition[key])

            # 四舍五入
            for key in total:
                total[key] = round(total[key], 1)

            return total

        except Exception as e:
            logger.error(f"Failed to get daily intake for {user_id}: {e}", exc_info=True)
            return self._empty_intake()

    def _empty_intake(self) -> Dict[str, Any]:
        """空摄入数据"""
        return {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            "fiber": 0,
            "vegetables": 0,
            "sodium": 0
        }

    async def calculate_daily_target(
        self,
        user_id: int,
        date_target: date
    ) -> Dict[str, Any]:
        """
        计算每日营养目标

        考虑因素：
        1. 基础代谢率（BMR）
        2. 活动系数
        3. 目标（减脂/增肌/维持）
        4. 当日运动消耗
        """
        profile = await self.get_user_profile(user_id)
        exercise = await self.get_daily_exercise(user_id, date_target)

        age = profile.get("age", 29)
        gender = profile.get("gender", "male")
        weight = profile.get("current_weight", 74)
        height = profile.get("height", 178)
        goal = profile.get("goal", "维持")

        # 计算基础代谢率（Harris-Benedict公式）
        if gender == "male":
            bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
        else:
            bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

        # 活动系数（优先从用户偏好读取，默认轻度活动）
        activity_factor = profile.get("preferences", {}).get("activity_factor", 1.375)
        tdee = bmr * activity_factor

        # 根据目标调整
        goal_mapping = {"减脂": -500, "减脂保肌": -400, "增肌": 300, "维持": 0, "健康改善": -200}
        adjustment = goal_mapping.get(goal, 0)
        target_calories = tdee + adjustment

        # 加上运动消耗
        if exercise:
            target_calories += exercise.get("calorie_burned", 0)

        # 宏量营养素分配（减脂期：高蛋白、中碳水、低脂）
        target = {
            "calories": int(target_calories),
            "protein": int(weight * 2),  # 2g/kg体重
            "carbs": int(target_calories * 0.4 / 4),
            "fat": int(target_calories * 0.25 / 9),
            "fiber": 25,
            "vegetables": 500,  # 克
            "sodium_limit": 2300  # mg
        }

        # 缓存到daily_health_state
        await self._cache_target(user_id, date_target, target)
        return target

    async def _cache_target(self, user_id: int, date_target: date, target: Dict[str, Any]):
        """缓存营养目标到daily_health_state"""
        if not self.db:
            return

        try:
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO daily_health_state (user_id, date, nutrition_target)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, date)
                    DO UPDATE SET nutrition_target = EXCLUDED.nutrition_target,
                                  updated_at = NOW()
                    """,
                    user_id, date_target, target
                )
        except Exception as e:
            logger.error(f"Failed to cache target: {e}")

    def calculate_nutrition_gap(
        self,
        intake: Dict[str, Any],
        target: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        计算营养缺口

        正值表示还需摄入，负值表示已超标
        """
        gap = {}

        for nutrient in ["calories", "protein", "carbs", "fat", "fiber", "vegetables"]:
            gap[nutrient] = target.get(nutrient, 0) - intake.get(nutrient, 0)

        # 限制性营养素（钠、糖）- 计算剩余额度
        gap["sodium_available"] = target.get("sodium_limit", 2300) - intake.get("sodium", 0)

        return gap

    async def get_daily_exercise(self, user_id: int, date_target: date) -> Optional[Dict[str, Any]]:
        """获取当日运动记录"""
        if not self.db:
            return None

        try:
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT exercise_log FROM daily_health_state
                    WHERE user_id = $1 AND date = $2
                    """,
                    user_id, date_target
                )
            return row["exercise_log"] if row else None
        except Exception as e:
            logger.error(f"Failed to get daily exercise: {e}")
            return None

    async def update_daily_health(
        self,
        user_id: int,
        date_target: date,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新每日健康数据

        Args:
            data: {
                "weight": 74.5,
                "blood_pressure": "128/82",
                "sleep_hours": 7.5,
                "sleep_quality": 4,
                "exercise_log": {...}
            }
        """
        if not self.db:
            return {"updated": False, "error": "Database not initialized"}

        try:
            weight = data.get("weight")
            bmi = None
            if weight:
                profile = await self.get_user_profile(user_id)
                bmi = await self.calculate_bmi(weight, profile.get("height", 178))

            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO daily_health_state (
                        user_id, date, weight, bmi, blood_pressure,
                        sleep_hours, sleep_quality, exercise_log, notes
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (user_id, date)
                    DO UPDATE SET
                        weight = COALESCE(EXCLUDED.weight, daily_health_state.weight),
                        bmi = COALESCE(EXCLUDED.bmi, daily_health_state.bmi),
                        blood_pressure = COALESCE(EXCLUDED.blood_pressure, daily_health_state.blood_pressure),
                        sleep_hours = COALESCE(EXCLUDED.sleep_hours, daily_health_state.sleep_hours),
                        sleep_quality = COALESCE(EXCLUDED.sleep_quality, daily_health_state.sleep_quality),
                        exercise_log = COALESCE(EXCLUDED.exercise_log, daily_health_state.exercise_log),
                        notes = COALESCE(EXCLUDED.notes, daily_health_state.notes),
                        updated_at = NOW()
                    """,
                    user_id,
                    date_target,
                    weight,
                    bmi,
                    data.get("blood_pressure"),
                    data.get("sleep_hours"),
                    data.get("sleep_quality"),
                    data.get("exercise_log"),
                    data.get("notes")
                )

            # 记录到Memory
            if self.memory_agent:
                await self.memory_agent.store(
                    user_id=user_id,
                    memory_type="health_update",
                    data={"weight": weight, "bmi": bmi, "date": date_target.isoformat()},
                    importance_score=0.6
                )

            logger.info(f"Updated health data for user {user_id} on {date_target}")
            return {"updated": True, "changes": {"weight": weight, "bmi": bmi}}

        except Exception as e:
            logger.error(f"Failed to update daily health: {e}", exc_info=True)
            return {"updated": False, "error": str(e)}

    async def get_weight_trend(
        self,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        获取体重趋势

        Returns:
            {
                "data_points": [...],
                "trend": "下降",
                "change": -3.2,
                "change_rate": -1.1  # kg/月
            }
        """
        if not self.db:
            return {"data_points": [], "trend": "stable", "change": 0, "change_rate": 0}

        try:
            start_date = date.today() - timedelta(days=days)
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT date, weight FROM daily_health_state
                    WHERE user_id = $1 AND date >= $2 AND weight IS NOT NULL
                    ORDER BY date ASC
                    """,
                    user_id, start_date
                )

            data_points = [{"date": row["date"].isoformat(), "weight": row["weight"]} for row in rows]

            if len(rows) < 2:
                return {"data_points": data_points, "trend": "stable", "change": 0, "change_rate": 0}

            first_weight = rows[0]["weight"]
            last_weight = rows[-1]["weight"]
            change = round(last_weight - first_weight, 2)

            # 月均变化（按实际天数比例）
            actual_days = (rows[-1]["date"] - rows[0]["date"]).days or 1
            change_rate = round(change / actual_days * 30, 2)

            if change_rate < -0.5:
                trend = "下降"
            elif change_rate > 0.5:
                trend = "上升"
            else:
                trend = "稳定"

            return {
                "data_points": data_points,
                "trend": trend,
                "change": change,
                "change_rate": change_rate
            }

        except Exception as e:
            logger.error(f"Failed to get weight trend: {e}", exc_info=True)
            return {"data_points": [], "trend": "stable", "change": 0, "change_rate": 0}

    async def calculate_bmi(self, weight: float, height: float) -> float:
        """计算BMI"""
        if not height:
            return 0.0
        return round(weight / ((height / 100) ** 2), 1)
