"""
Memory Agent - 独立记忆管理Agent
负责四层记忆架构的管理、压缩、召回和维护
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
import os
import json
import uuid

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class MemoryAgent:
    """
    Memory Agent - 独立记忆管理

    四层记忆架构：
    - Layer 0: Raw Memory (90天原始数据)
    - Layer 1: Semantic Memory (长期语义记忆)
    - Layer 2: Health Profile (健康画像)
    - Layer 3: Episodic Memory (事件记忆)

    职责：
    1. 短期记忆管理（Raw Memory - 90天）
    2. 长期记忆管理（Semantic Memory压缩）
    3. 记忆召回（基于上下文检索）
    4. 记忆维护（压缩、清理、老化检测）
    """

    def __init__(
        self,
        db_config: Optional[Dict[str, Any]] = None,
        vector_store_config: Optional[Dict[str, Any]] = None
    ):
        self.db_config = db_config or {}
        self.vector_store_config = vector_store_config or {}
        self.db: Optional[asyncpg.Pool] = None
        self.vector_store = None  # 优先使用pgvector，Milvus作为可选项
        self.use_milvus = False
        self._openai_client = None

    async def initialize(self):
        """初始化Memory Agent"""
        logger.info("Initializing Memory Agent...")

        # 初始化数据库连接
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

        # 初始化向量存储
        await self._init_vector_store()

        # 初始化LLM客户端（可选）
        await self._init_llm_client()

        logger.info("Memory Agent initialized")

    async def _init_vector_store(self):
        """初始化向量存储，优先pgvector，其次Milvus"""
        # 优先尝试pgvector（schema已定义VECTOR类型）
        try:
            async with self.db.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                # 测试向量操作
                await conn.execute("SELECT '[1,2,3]'::vector")
            self.vector_store = {"type": "pgvector", "table": "semantic_memory"}
            logger.info("Using pgvector for vector storage")
            return
        except Exception as e:
            logger.warning(f"pgvector not available: {e}")

        # 尝试Milvus
        try:
            from pymilvus import connections, Collection
            milvus_host = self.vector_store_config.get("host", os.getenv("MILVUS_HOST", "localhost"))
            milvus_port = self.vector_store_config.get("port", os.getenv("MILVUS_PORT", "19530"))
            connections.connect("default", host=milvus_host, port=milvus_port)
            collection_name = os.getenv("MILVUS_COLLECTION_NAME", "diet_assistant_memories")
            self.vector_store = Collection(collection_name)
            self.use_milvus = True
            logger.info("Using Milvus for vector storage")
        except Exception as e:
            logger.warning(f"Milvus not available: {e}")
            # 回退到内存向量存储
            self.vector_store = {"type": "memory", "vectors": []}
            logger.info("Using in-memory vector storage")

    async def _init_llm_client(self):
        """初始化LLM客户端（可选）"""
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=openai_key)
                logger.info("OpenAI client initialized")
            except Exception as e:
                logger.warning(f"OpenAI client init failed: {e}")

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """标准Agent接口"""
        action = request.get("action", "")
        params = request.get("params", {})

        try:
            if action == "store":
                memory_id = await self.store(
                    user_id=params["user_id"],
                    memory_type=params["memory_type"],
                    data=params["data"],
                    importance_score=params.get("importance_score")
                )
                result = {"memory_id": memory_id}
            elif action == "recall":
                result = await self.recall(
                    user_id=params["user_id"],
                    context=params.get("context", {}),
                    limit=params.get("limit", 10)
                )
            elif action == "compress_old_memories":
                result = await self.compress_old_memories()
            elif action == "get_health_profile":
                result = await self.get_health_profile(params["user_id"])
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"Memory Agent action {action} failed: {e}", exc_info=True)
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
            logger.error(f"Memory Agent health check failed: {e}")
            return False

    async def store(
        self,
        user_id: int,
        memory_type: str,
        data: Dict[str, Any],
        importance_score: Optional[float] = None
    ) -> str:
        """
        存储原始记忆

        Args:
            user_id: 用户ID
            memory_type: 记忆类型 (meal_photo, chat, sensor, order, emotion, health_update)
            data: 记忆数据
            importance_score: 重要性评分（可选，系统自动计算）

        Returns:
            memory_id
        """
        # 如果没有提供重要性评分，自动计算
        if importance_score is None:
            importance_score = await self.calculate_importance(user_id, memory_type, data)

        # 计算过期时间（90天后）
        expire_time = datetime.now() + timedelta(days=90)
        memory_id = str(uuid.uuid4())

        if self.db:
            try:
                async with self.db.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO raw_memory (id, user_id, type, content_url, metadata,
                                                created_time, expire_time, importance_score, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'active')
                        """,
                        memory_id,
                        user_id,
                        memory_type,
                        data.get("url") or data.get("image_url"),
                        json.dumps(data),
                        datetime.now(),
                        expire_time,
                        importance_score
                    )
            except Exception as e:
                logger.error(f"Failed to store memory in DB: {e}", exc_info=True)

        logger.info(f"Stored memory {memory_id} for user {user_id}, importance={importance_score:.2f}")
        return memory_id

    async def recall(
        self,
        user_id: int,
        context: Dict[str, Any],
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        召回相关记忆

        Args:
            user_id: 用户ID
            context: 当前上下文 {"intent": "...", "meal_type": "...", "embedding": [...]}
            limit: 召回数量限制

        Returns:
            {
                "recent": [...],      # 近期记忆（7天内）
                "semantic": [...],    # 语义记忆（长期模式）
                "events": [...],      # 相关事件
                "profile": {...}      # 健康画像
            }
        """
        memories = {
            "recent": await self._recall_recent(user_id, days=7),
            "semantic": await self._recall_semantic(user_id, context, limit=5),
            "events": await self._recall_events(user_id, context),
            "profile": await self.get_health_profile(user_id)
        }

        logger.info(f"Recalled memories for user {user_id}: "
                   f"{len(memories['recent'])} recent, "
                   f"{len(memories['semantic'])} semantic, "
                   f"{len(memories['events'])} events")

        return memories

    async def _recall_recent(self, user_id: int, days: int = 7) -> List[Dict]:
        """召回最近N天的记忆"""
        if not self.db:
            return []

        cutoff = datetime.now() - timedelta(days=days)
        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, type, metadata, created_time, importance_score
                    FROM raw_memory
                    WHERE user_id = $1 AND created_time >= $2 AND status = 'active'
                    ORDER BY created_time DESC
                    LIMIT 50
                    """,
                    user_id, cutoff
                )

            return [
                {
                    "memory_id": str(row["id"]),
                    "memory_type": row["type"],
                    "data": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_time": row["created_time"].isoformat(),
                    "importance_score": row["importance_score"]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to recall recent memories: {e}", exc_info=True)
            return []

    async def _recall_semantic(
        self,
        user_id: int,
        context: Dict[str, Any],
        limit: int = 5
    ) -> List[Dict]:
        """基于向量相似度召回语义记忆"""
        if not self.db:
            return []

        try:
            # 如果有embedding，优先用向量检索；否则按分类/时间检索
            if "embedding" in context and self.vector_store and self.vector_store.get("type") == "pgvector":
                embedding = context["embedding"]
                async with self.db.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, category, summary, structured_data, confidence,
                               time_range, source_count
                        FROM semantic_memory
                        WHERE user_id = $1
                        ORDER BY embedding <-> $2::vector
                        LIMIT $3
                        """,
                        user_id, embedding, limit
                    )
            else:
                # 按意图分类召回
                category = self._map_intent_to_category(context.get("intent", ""))
                async with self.db.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, category, summary, structured_data, confidence,
                               time_range, source_count
                        FROM semantic_memory
                        WHERE user_id = $1 AND ($2::text IS NULL OR category = $2)
                        ORDER BY last_updated DESC
                        LIMIT $3
                        """,
                        user_id, category, limit
                    )

            return [
                {
                    "memory_id": str(row["id"]),
                    "category": row["category"],
                    "summary": row["summary"],
                    "structured_data": row["structured_data"] or {},
                    "confidence": row["confidence"],
                    "time_range": [row["time_range"].lower.isoformat(), row["time_range"].upper.isoformat()] if row["time_range"] else None,
                    "source_count": row["source_count"]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to recall semantic memories: {e}", exc_info=True)
            return []

    def _map_intent_to_category(self, intent: str) -> Optional[str]:
        """将意图映射到语义记忆分类"""
        mapping = {
            "meal_decision": "food_preference",
            "recipe_query": "food_preference",
            "emotion_history": "behavior",
            "emotion_support": "behavior",
            "health_update": "nutrition_pattern"
        }
        return mapping.get(intent)

    async def _recall_events(
        self,
        user_id: int,
        context: Dict[str, Any]
    ) -> List[Dict]:
        """召回相关事件记忆"""
        if not self.db:
            return []

        try:
            # 根据意图选择事件类型
            intent = context.get("intent", "")
            event_types = []
            if intent in ["meal_decision", "recipe_query"]:
                event_types = ["social_eating", "habit_shift"]
            elif intent in ["emotion_support", "emotion_history"]:
                event_types = ["goal_change", "illness"]

            if event_types:
                async with self.db.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, event_type, event_date, duration_days, description,
                               health_impact, user_response, importance_score
                        FROM episodic_memory
                        WHERE user_id = $1 AND event_type = ANY($2)
                        ORDER BY event_date DESC
                        LIMIT 10
                        """,
                        user_id, event_types
                    )
            else:
                async with self.db.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT id, event_type, event_date, duration_days, description,
                               health_impact, user_response, importance_score
                        FROM episodic_memory
                        WHERE user_id = $1
                        ORDER BY event_date DESC
                        LIMIT 10
                        """,
                        user_id
                    )

            return [
                {
                    "memory_id": str(row["id"]),
                    "event_type": row["event_type"],
                    "event_date": row["event_date"].isoformat(),
                    "duration_days": row["duration_days"],
                    "description": row["description"],
                    "health_impact": row["health_impact"] or {},
                    "user_response": row["user_response"] or {},
                    "importance_score": row["importance_score"]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to recall events: {e}", exc_info=True)
            return []

    async def get_health_profile(self, user_id: int) -> Dict[str, Any]:
        """获取用户健康画像"""
        if not self.db:
            return self._default_profile(user_id)

        try:
            async with self.db.acquire() as conn:
                user_row = await conn.fetchrow(
                    "SELECT goal, target_weight, allergies, preferences FROM users WHERE id = $1",
                    user_id
                )
                health_row = await conn.fetchrow(
                    """
                    SELECT weight, bmi, nutrition_intake, nutrition_target,
                           emotion_state
                    FROM daily_health_state
                    WHERE user_id = $1
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    user_id
                )

            if not user_row:
                return self._default_profile(user_id)

            # 计算营养模式（近7天平均）
            nutrition_pattern = await self._compute_nutrition_pattern(user_id)

            return {
                "user_id": user_id,
                "goal": user_row["goal"] or "维持",
                "target_weight": user_row["target_weight"],
                "current_weight": health_row["weight"] if health_row else 0,
                "current_bmi": health_row["bmi"] if health_row else 0,
                "allergies": user_row["allergies"] or [],
                "preferences": user_row["preferences"] or {},
                "emotion_state": health_row["emotion_state"] if health_row else None,
                "nutrition_pattern": nutrition_pattern
            }
        except Exception as e:
            logger.error(f"Failed to get health profile: {e}", exc_info=True)
            return self._default_profile(user_id)

    def _default_profile(self, user_id: int) -> Dict[str, Any]:
        """默认健康画像"""
        return {
            "user_id": user_id,
            "goal": "减脂",
            "current_weight": 0,
            "nutrition_pattern": {}
        }

    async def _compute_nutrition_pattern(self, user_id: int) -> Dict[str, Any]:
        """计算近7天营养模式"""
        if not self.db:
            return {}

        try:
            start_date = date.today() - timedelta(days=7)
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT nutrition_intake FROM daily_health_state
                    WHERE user_id = $1 AND date >= $2 AND nutrition_intake IS NOT NULL
                    """,
                    user_id, start_date
                )

            if not rows:
                return {}

            totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
            count = 0
            for row in rows:
                intake = row["nutrition_intake"] or {}
                for key in totals:
                    totals[key] += float(intake.get(key, 0))
                count += 1

            return {key: round(value / count, 1) for key, value in totals.items()}
        except Exception as e:
            logger.error(f"Failed to compute nutrition pattern: {e}")
            return {}

    async def compress_old_memories(self) -> Dict[str, Any]:
        """
        压缩旧记忆（定时任务）

        流程：
        1. 查询超过90天的raw_memory
        2. 计算重要性评分
        3. 低价值记忆直接删除
        4. 高价值记忆生成摘要并保存到semantic_memory
        5. 标记原始记忆为compressed
        """
        cutoff = datetime.now() - timedelta(days=90)
        logger.info(f"Starting memory compression for records before {cutoff}")

        compressed_count = 0
        deleted_count = 0

        if not self.db:
            logger.info("Memory compression completed: no database connection")
            return {"compressed_count": 0, "deleted_count": 0}

        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, user_id, type, metadata, created_time, importance_score
                    FROM raw_memory
                    WHERE created_time < $1 AND status = 'active'
                    ORDER BY created_time ASC
                    LIMIT 100
                    """,
                    cutoff
                )

            for row in rows:
                memory_id = str(row["id"])
                user_id = row["user_id"]
                data = json.loads(row["metadata"]) if row["metadata"] else {}
                importance = row["importance_score"] or await self.calculate_importance(
                    user_id, row["type"], data
                )

                if importance < 0.3:
                    # 低价值记忆删除
                    try:
                        async with self.db.acquire() as conn:
                            await conn.execute(
                                "UPDATE raw_memory SET status = 'deleted' WHERE id = $1",
                                row["id"]
                            )
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete memory {memory_id}: {e}")
                    continue

                # 高价值记忆生成语义摘要
                try:
                    summary = await self.generate_semantic_summary([{
                        "type": row["type"],
                        "data": data,
                        "created_time": row["created_time"]
                    }])

                    async with self.db.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO semantic_memory (
                                user_id, category, summary, structured_data,
                                confidence, time_range, source_count
                            ) VALUES ($1, $2, $3, $4, $5, DATERANGE($6, $7, '[]'), $8)
                            """,
                            user_id,
                            summary["category"],
                            summary["summary"],
                            json.dumps(summary["structured_data"]),
                            summary["confidence"],
                            row["created_time"].date(),
                            row["created_time"].date(),
                            1
                        )

                        await conn.execute(
                            "UPDATE raw_memory SET status = 'compressed' WHERE id = $1",
                            row["id"]
                        )
                    compressed_count += 1
                except Exception as e:
                    logger.error(f"Failed to compress memory {memory_id}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Memory compression failed: {e}", exc_info=True)

        logger.info(f"Memory compression completed: {compressed_count} compressed, {deleted_count} deleted")
        return {
            "compressed_count": compressed_count,
            "deleted_count": deleted_count,
            "timestamp": datetime.now().isoformat()
        }

    async def calculate_importance(
        self,
        user_id: int,
        memory_type: str,
        data: Dict[str, Any]
    ) -> float:
        """
        计算记忆重要性评分

        评分模型：
        importance = 0.4 * health_change + 0.3 * abnormal_pattern +
                     0.2 * user_engagement + 0.1 * emotion_context
        """
        score = 0.5  # 基础分

        # 类型权重
        type_weights = {
            "health_update": 0.25,
            "emotion": 0.2,
            "meal_photo": 0.15,
            "order": 0.1,
            "chat": 0.05
        }
        score += type_weights.get(memory_type, 0.1)

        # 健康变化检测
        health_change = 0.0
        if "weight" in data and isinstance(data["weight"], (int, float)):
            # 体重变化超过1kg视为显著
            if abs(data.get("weight_change", 0)) >= 1:
                health_change = 0.3
        if "blood_pressure" in data:
            health_change = max(health_change, 0.2)
        score += health_change * 0.4

        # 异常模式
        abnormal = 0.0
        if data.get("emotion") in ["guilt", "anxiety", "frustration"]:
            abnormal = 0.3
        if data.get("calories", 0) > 1500 or data.get("calories", 0) < 200:
            abnormal = max(abnormal, 0.25)
        score += abnormal * 0.3

        # 用户参与度（是否有URL/图片）
        if data.get("url") or data.get("image_url"):
            score += 0.1

        # 情绪上下文
        if data.get("emotion"):
            score += 0.05

        return min(max(score, 0.0), 1.0)

    async def generate_semantic_summary(
        self,
        memories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        生成语义记忆摘要

        将一组相关的原始记忆压缩为语义描述
        """
        if not memories:
            return {
                "category": "general",
                "summary": "无内容",
                "structured_data": {},
                "confidence": 0.0
            }

        # 提取关键信息
        memory_types = [m.get("type", "unknown") for m in memories]
        texts = []
        for m in memories:
            data = m.get("data", {})
            if isinstance(data, dict):
                texts.append(json.dumps(data, ensure_ascii=False))

        combined_text = "\n".join(texts)[:2000]

        # 尝试调用LLM生成摘要
        if self._openai_client:
            try:
                response = await self._openai_client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview"),
                    messages=[{
                        "role": "user",
                        "content": (
                            "请将以下用户饮食健康相关的记忆记录总结为一条语义记忆。"
                            "返回JSON格式：{\"category\": \"...\", \"summary\": \"...\", \"structured_data\": {...}}\n\n"
                            f"记忆内容：\n{combined_text}"
                        )
                    }],
                    response_format={"type": "json_object"}
                )
                result = json.loads(response.choices[0].message.content)
                return {
                    "category": result.get("category", "general"),
                    "summary": result.get("summary", "用户记忆摘要"),
                    "structured_data": result.get("structured_data", {}),
                    "confidence": 0.85
                }
            except Exception as e:
                logger.warning(f"LLM summary failed: {e}, using fallback")

        # 模板化摘要
        primary_type = max(set(memory_types), key=memory_types.count)
        category_mapping = {
            "meal_photo": "nutrition_pattern",
            "emotion": "behavior",
            "health_update": "nutrition_pattern",
            "chat": "behavior",
            "order": "food_preference"
        }

        return {
            "category": category_mapping.get(primary_type, "general"),
            "summary": f"用户在{len(memories)}条记录中表现出{primary_type}相关模式",
            "structured_data": {"memory_types": memory_types, "count": len(memories)},
            "confidence": 0.7
        }

    async def detect_recipe_aging(self, user_id: int) -> List[Dict[str, Any]]:
        """
        检测食谱老化

        识别2个月未用且用户状态已改变的食谱
        """
        if not self.db:
            return []

        try:
            cutoff = date.today() - timedelta(days=60)
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT recipe_id, last_used, times_used, current_fit_score, aging_score
                    FROM recipe_lifecycle
                    WHERE user_id = $1 AND last_used < $2
                    ORDER BY aging_score DESC
                    LIMIT 20
                    """,
                    user_id, cutoff
                )

            return [
                {
                    "recipe_id": row["recipe_id"],
                    "last_used": row["last_used"].isoformat(),
                    "times_used": row["times_used"],
                    "current_fit_score": row["current_fit_score"],
                    "aging_score": row["aging_score"]
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to detect recipe aging: {e}", exc_info=True)
            return []
