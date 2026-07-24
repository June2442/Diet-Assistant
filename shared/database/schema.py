"""
数据库Schema定义
包含所有表的创建SQL
"""

# 用户表
CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    phone VARCHAR(20),

    -- 基础信息
    age INT,
    gender VARCHAR(10),
    height FLOAT,  -- cm

    -- 健康目标
    goal VARCHAR(20),  -- 减脂/增肌/维持
    target_weight FLOAT,

    -- 健康状况
    health_conditions TEXT[],  -- 疾病列表
    allergies TEXT[],  -- 过敏原
    medications TEXT[],  -- 用药

    -- 偏好设置
    preferences JSONB,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
"""

# 每日健康状态表
CREATE_DAILY_HEALTH_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS daily_health_state (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- 健康指标
    weight FLOAT,
    bmi FLOAT,
    blood_pressure VARCHAR(20),
    sleep_hours FLOAT,
    sleep_quality INT CHECK (sleep_quality BETWEEN 1 AND 5),

    -- 运动记录
    exercise_log JSONB,  -- {"type": "...", "duration": 40, "calorie_burned": 350}

    -- 营养状态
    nutrition_intake JSONB,  -- 今日摄入
    nutrition_target JSONB,  -- 今日目标
    nutrition_gap JSONB,     -- 营养缺口

    -- 情绪状态
    emotion_state VARCHAR(50),
    notes TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(user_id, date)
);

CREATE INDEX idx_health_user_date ON daily_health_state(user_id, date DESC);
"""

# Raw Memory表（原始记忆）
CREATE_RAW_MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS raw_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL,  -- meal_photo, chat, sensor, order

    -- 内容
    content_url TEXT,  -- S3/MinIO URL
    metadata JSONB,    -- 额外元数据

    -- 时间管理
    created_time TIMESTAMP NOT NULL DEFAULT NOW(),
    expire_time TIMESTAMP,  -- 90天后

    -- 重要性
    importance_score FLOAT DEFAULT 0.5,

    -- 状态
    status VARCHAR(20) DEFAULT 'active'  -- active, compressed, deleted
);

CREATE INDEX idx_raw_memory_user ON raw_memory(user_id, created_time DESC);
CREATE INDEX idx_raw_memory_expire ON raw_memory(user_id, expire_time, status);
"""

# Semantic Memory表（语义记忆）
CREATE_SEMANTIC_MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS semantic_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 分类
    category VARCHAR(50) NOT NULL,  -- nutrition_pattern, food_preference, behavior, risk

    -- 内容
    summary TEXT,
    structured_data JSONB,

    -- 向量检索
    embedding VECTOR(1536),  -- 需要pgvector扩展

    -- 置信度
    confidence FLOAT,

    -- 时间范围
    time_range DATERANGE,
    source_count INT,  -- 来源于多少条原始记录

    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_semantic_user_time ON semantic_memory(user_id, time_range);
"""

# Episodic Memory表（事件记忆）
CREATE_EPISODIC_MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS episodic_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 事件类型
    event_type VARCHAR(50) NOT NULL,  -- social_eating, illness, goal_change, habit_shift

    -- 时间
    event_date DATE NOT NULL,
    duration_days INT DEFAULT 1,

    -- 描述
    description TEXT,

    -- 影响
    health_impact JSONB,
    user_response JSONB,

    -- 重要性
    importance_score FLOAT,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_episodic_user_date ON episodic_memory(user_id, event_date DESC);
"""

# Recipe Lifecycle表（食谱生命周期）
CREATE_RECIPE_LIFECYCLE_TABLE = """
CREATE TABLE IF NOT EXISTS recipe_lifecycle (
    id SERIAL PRIMARY KEY,
    recipe_id VARCHAR(50) NOT NULL,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 使用记录
    first_used DATE NOT NULL,
    last_used DATE NOT NULL,
    times_used INT DEFAULT 0,

    -- 用户反馈
    user_feedback JSONB,  -- {"taste": 5, "satisfaction": 4, "difficulty": 3}

    -- 适配度评分
    current_fit_score FLOAT,  -- 0-1，当前目标的适配度
    aging_score FLOAT,        -- 0-1，老化程度

    -- 营养适配
    nutrition_match JSONB,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(user_id, recipe_id)
);

CREATE INDEX idx_recipe_lifecycle_aging ON recipe_lifecycle(user_id, last_used, aging_score);
"""

# Meal Records表（餐食记录）
CREATE_MEAL_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS meal_records (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 餐次信息
    meal_type VARCHAR(20) NOT NULL,  -- breakfast, lunch, dinner, snack
    meal_time TIMESTAMP NOT NULL,

    -- 食物信息
    dishes JSONB NOT NULL,  -- [{"name": "...", "weight": 100, "nutrition": {...}}]

    -- 营养总计
    total_nutrition JSONB,

    -- 来源
    source VARCHAR(20),  -- photo, manual, takeout
    image_url TEXT,

    -- 记录方式
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_meal_user_time ON meal_records(user_id, meal_time DESC);
"""

# 所有建表语句
ALL_CREATE_TABLES = [
    CREATE_USERS_TABLE,
    CREATE_DAILY_HEALTH_STATE_TABLE,
    CREATE_RAW_MEMORY_TABLE,
    CREATE_SEMANTIC_MEMORY_TABLE,
    CREATE_EPISODIC_MEMORY_TABLE,
    CREATE_RECIPE_LIFECYCLE_TABLE,
    CREATE_MEAL_RECORDS_TABLE
]


def get_init_database_sql() -> str:
    """获取完整的数据库初始化SQL"""
    return "\n\n".join(ALL_CREATE_TABLES)
