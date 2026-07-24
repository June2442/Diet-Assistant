"""
共享数据模型
定义系统中使用的数据结构
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from enum import Enum


class GoalType(Enum):
    """健康目标类型"""
    LOSE_FAT = "减脂"
    GAIN_MUSCLE = "增肌"
    MAINTAIN = "维持"
    HEALTH_IMPROVE = "健康改善"


class MealType(Enum):
    """餐次类型"""
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


@dataclass
class UserProfile:
    """用户画像"""
    user_id: int
    age: int
    gender: str
    height: float  # cm
    current_weight: float  # kg
    target_weight: Optional[float]
    bmi: float
    goal: GoalType
    health_conditions: List[str]
    allergies: List[str]
    medications: List[str]


@dataclass
class NutritionData:
    """营养数据"""
    calories: float
    protein: float
    carbs: float
    fat: float
    fiber: float
    vegetables: float  # 克
    sodium: float  # mg
    sugar: Optional[float]


@dataclass
class NutritionGap:
    """营养缺口"""
    calories: float  # 正值=还需摄入，负值=已超标
    protein: float
    carbs: float
    fat: float
    fiber: float
    vegetables: float
    sodium_available: float  # 剩余钠额度


@dataclass
class HealthState:
    """健康状态"""
    user_id: int
    date: date
    weight: Optional[float]
    bmi: Optional[float]
    blood_pressure: Optional[str]
    sleep_hours: Optional[float]
    exercise_log: Optional[Dict[str, Any]]
    today_intake: NutritionData
    target: NutritionData
    gap: NutritionGap


@dataclass
class Dish:
    """菜品"""
    name: str
    nutrition: NutritionData
    price: Optional[float]
    allergens: List[str]
    cooking_method: Optional[str]
    ingredients: Optional[List[str]]


@dataclass
class DishRecommendation:
    """菜品推荐"""
    dishes: List[str]
    score: float
    nutrition: NutritionData
    explanation: str
    warnings: List[str]


@dataclass
class Memory:
    """记忆数据"""
    memory_id: str
    user_id: int
    memory_type: str
    content: Dict[str, Any]
    importance_score: float
    created_time: datetime
    expire_time: Optional[datetime]
    status: str  # active, compressed, deleted


@dataclass
class SemanticMemory:
    """语义记忆"""
    memory_id: str
    user_id: int
    category: str
    summary: str
    structured_data: Dict[str, Any]
    confidence: float
    time_range: tuple  # (start_date, end_date)
    source_count: int
