"""
FastAPI主应用入口
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from typing import Dict, Any
import os

import asyncpg
import redis.asyncio as redis
from dotenv import load_dotenv

from agents.orchestrator.orchestrator import AgentOrchestrator

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("Starting Diet Assistant...")

    # 初始化数据库连接
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        app.state.db_pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    else:
        app.state.db_pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            database=os.getenv("POSTGRES_DB", "diet_assistant"),
            min_size=2,
            max_size=10
        )
    logger.info("Database pool initialized")

    # 初始化Redis连接
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        app.state.redis = redis.from_url(redis_url, decode_responses=True)
        await app.state.redis.ping()
        logger.info("Redis connection initialized")
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        app.state.redis = None

    # 初始化Milvus连接（可选）
    try:
        from pymilvus import connections
        connections.connect(
            "default",
            host=os.getenv("MILVUS_HOST", "localhost"),
            port=os.getenv("MILVUS_PORT", "19530")
        )
        logger.info("Milvus connection initialized")
    except Exception as e:
        logger.warning(f"Milvus not available: {e}")

    # 初始化Orchestrator
    app.state.orchestrator = AgentOrchestrator(config={
        "db": {"database_url": database_url} if database_url else {},
        "cookhero": {
            "api_url": os.getenv("COOKHERO_API_URL", "http://localhost:8000"),
            "api_key": os.getenv("COOKHERO_API_KEY")
        }
    })
    await app.state.orchestrator.initialize()
    logger.info("Orchestrator initialized")

    logger.info("All agents initialized successfully")

    yield

    # 关闭时清理
    logger.info("Shutting down Diet Assistant...")
    if app.state.db_pool:
        await app.state.db_pool.close()
    if app.state.redis:
        await app.state.redis.close()


app = FastAPI(
    title="Diet Assistant API",
    description="多Agent协作的智能饮食健康助手",
    version="0.1.0",
    lifespan=lifespan
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "Diet Assistant",
        "version": "0.1.0",
        "status": "running",
        "description": "多Agent协作的智能饮食健康助手"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        orchestrator = app.state.orchestrator
        agent_health = await orchestrator.health_check_all()
        db_healthy = app.state.db_pool is not None

        return {
            "status": "healthy" if db_healthy else "degraded",
            "database": db_healthy,
            "agents": agent_health
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.post("/api/v1/chat")
async def chat(request: Dict[str, Any]):
    """
    统一聊天接口

    Request:
    {
        "user_id": 1001,
        "message": "今天晚上吃什么？",
        "image_url": "...",  # 可选
        "metadata": {...}     # 可选
    }
    """
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    orchestrator = app.state.orchestrator
    result = await orchestrator.process(
        user_id=user_id,
        user_input={
            "text": request.get("message", ""),
            "image_url": request.get("image_url"),
            "metadata": request.get("metadata", {})
        }
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))

    return {
        "success": True,
        "intent": result.get("intent"),
        "response": result.get("response"),
        "data": result.get("data", {})
    }


@app.post("/api/v1/health/daily")
async def update_daily_health(request: Dict[str, Any]):
    """
    更新每日健康数据

    Request:
    {
        "user_id": 1001,
        "date": "2026-07-23",
        "weight": 74.5,
        "blood_pressure": "128/82",
        "sleep_hours": 7.5,
        "exercise_log": {...}
    }
    """
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    from datetime import date, datetime
    date_str = request.get("date", date.today().isoformat())
    date_target = datetime.strptime(date_str, "%Y-%m-%d").date()

    health_agent = app.state.orchestrator.agents["health"]
    result = await health_agent.update_daily_health(
        user_id=user_id,
        date_target=date_target,
        data={
            "weight": request.get("weight"),
            "blood_pressure": request.get("blood_pressure"),
            "sleep_hours": request.get("sleep_hours"),
            "sleep_quality": request.get("sleep_quality"),
            "exercise_log": request.get("exercise_log"),
            "notes": request.get("notes")
        }
    )

    if not result.get("updated"):
        raise HTTPException(status_code=500, detail=result.get("error", "Update failed"))

    return {
        "success": True,
        "message": "健康数据已更新",
        "data": result
    }


@app.get("/api/v1/health/state")
async def get_health_state(user_id: int):
    """获取用户当前健康状态"""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    health_agent = app.state.orchestrator.agents["health"]
    state = await health_agent.get_current_state(user_id)

    return {
        "success": True,
        "user_id": user_id,
        "today_intake": state["today_intake"],
        "target": state["target"],
        "gap": state["gap"],
        "calorie_budget": state["calorie_budget"],
        "profile": state["profile"]
    }


@app.post("/api/v1/meal/recommend")
async def recommend_meal(request: Dict[str, Any]):
    """
    智能选菜推荐

    Request:
    {
        "user_id": 1001,
        "scenario": "restaurant_menu",
        "image_url": "...",
        "available_dishes": [...]  # 可选
    }
    """
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    from agents.meal_decision_agent.meal_decision_agent import MealScenario
    scenario_map = {
        "restaurant_menu": MealScenario.RESTAURANT_MENU,
        "takeout_platform": MealScenario.TAKEOUT_PLATFORM,
        "user_photo": MealScenario.USER_PHOTO,
        "recipe_based": MealScenario.RECIPE_BASED
    }
    scenario = scenario_map.get(
        request.get("scenario", "restaurant_menu"),
        MealScenario.RESTAURANT_MENU
    )

    meal_agent = app.state.orchestrator.agents["meal_decision"]
    result = await meal_agent.recommend_dishes(
        user_id=user_id,
        scenario=scenario,
        input_data={
            "image_url": request.get("image_url"),
            "text": request.get("text", ""),
            "available_dishes": request.get("available_dishes", [])
        }
    )

    return {
        "success": True,
        "recommendations": result.get("recommendations", []),
        "health_state": result.get("health_state", {}),
        "context": result.get("context", {})
    }


@app.post("/api/v1/meal/record")
async def record_meal(request: Dict[str, Any]):
    """记录餐食"""
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    from datetime import datetime
    memory_agent = app.state.orchestrator.agents["memory"]

    # 存储到raw_memory
    memory_id = await memory_agent.store(
        user_id=user_id,
        memory_type=request.get("source", "manual"),
        data={
            "meal_type": request.get("meal_type", "snack"),
            "dishes": request.get("dishes", []),
            "total_nutrition": request.get("total_nutrition", {}),
            "image_url": request.get("image_url"),
            "source": request.get("source", "manual"),
            "meal_time": request.get("meal_time", datetime.now().isoformat())
        },
        importance_score=0.6
    )

    # 可选：写入meal_records表
    if app.state.db_pool and request.get("dishes"):
        try:
            async with app.state.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO meal_records (user_id, meal_type, meal_time, dishes, total_nutrition, source, image_url)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    user_id,
                    request.get("meal_type", "snack"),
                    request.get("meal_time", datetime.now()),
                    request.get("dishes", []),
                    request.get("total_nutrition", {}),
                    request.get("source", "manual"),
                    request.get("image_url")
                )
        except Exception as e:
            logger.error(f"Failed to write meal record: {e}", exc_info=True)

    return {
        "success": True,
        "message": "餐食记录成功",
        "memory_id": memory_id
    }


@app.get("/api/v1/memory/summary")
async def get_memory_summary(user_id: int, days: int = 7):
    """获取用户记忆摘要"""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    memory_agent = app.state.orchestrator.agents["memory"]
    memories = await memory_agent.recall(
        user_id=user_id,
        context={"intent": "general_summary", "days": days},
        limit=10
    )

    return {
        "success": True,
        "user_id": user_id,
        "recent": memories.get("recent", []),
        "semantic": memories.get("semantic", []),
        "events": memories.get("events", []),
        "profile": memories.get("profile", {})
    }


@app.post("/api/v1/recipes/search")
async def search_recipes(request: Dict[str, Any]):
    """搜索菜谱"""
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    recipe_agent = app.state.orchestrator.agents["recipe"]
    recipes = await recipe_agent.search_recipes(
        user_id=user_id,
        query=request.get("query", ""),
        filters=request.get("filters")
    )

    return {
        "success": True,
        "recipes": recipes
    }


@app.post("/api/v1/emotion/support")
async def emotion_support(request: Dict[str, Any]):
    """情绪支持"""
    user_id = request.get("user_id")
    message = request.get("message", "")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    emotion_agent = app.state.orchestrator.agents["emotion_support"]
    emotion = await emotion_agent.detect_emotion(user_id, message, {})
    support = await emotion_agent.provide_support(user_id, emotion, {"trigger": message})

    return {
        "success": True,
        "emotion": emotion.value,
        "support": support
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,  # CookHero使用8000，我们使用8001
        reload=True
    )
