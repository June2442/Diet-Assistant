"""
数据库初始化脚本
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from shared.database.schema import ALL_CREATE_TABLES

# 加载环境变量
load_dotenv()


async def init_database():
    """初始化数据库"""
    # 从环境变量获取配置
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "diet_assistant")

    print(f"Connecting to database: {user}@{host}:{port}/{database}")

    try:
        # 连接到默认postgres数据库
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database='postgres'
        )

        # 检查目标数据库是否存在
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            database
        )

        if not exists:
            print(f"Creating database: {database}")
            await conn.execute(f'CREATE DATABASE "{database}"')
            print(f"Database {database} created successfully")
        else:
            print(f"Database {database} already exists")

        await conn.close()

        # 连接到目标数据库
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )

        # 启用pgvector扩展（用于向量检索）
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            print("pgvector extension enabled")
        except Exception as e:
            print(f"Warning: Could not enable pgvector: {e}")
            print("Note: Vector search will not be available without pgvector extension")

        # 创建所有表
        print("\nCreating tables...")
        for i, sql in enumerate(ALL_CREATE_TABLES, 1):
            try:
                await conn.execute(sql)
                # 提取表名
                table_name = sql.split("CREATE TABLE IF NOT EXISTS")[1].split("(")[0].strip()
                print(f"  [{i}/{len(ALL_CREATE_TABLES)}] Created table: {table_name}")
            except Exception as e:
                print(f"  Error creating table: {e}")

        # 创建测试用户（可选）
        test_user_exists = await conn.fetchval(
            "SELECT 1 FROM users WHERE id = 1001"
        )

        if not test_user_exists:
            print("\nCreating test user...")
            await conn.execute("""
                INSERT INTO users (id, username, email, age, gender, height, goal, target_weight, health_conditions, allergies, medications)
                VALUES (1001, 'test_user', 'test@example.com', 29, 'male', 178, '减脂', 70, '{}', '{}', '{}')
            """)
            print("Test user created (id: 1001)")
        else:
            print("\nTest user already exists")

        await conn.close()

        print("\n✅ Database initialization completed successfully!")
        print(f"\nConnection string: postgresql://{user}:***@{host}:{port}/{database}")

    except Exception as e:
        print(f"\n❌ Error during database initialization: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(init_database())
