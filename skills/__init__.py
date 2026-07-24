"""
Skill基类和注册表
定义Skill接口和动态路由机制
"""

from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """
    Skill基类

    所有Skill必须继承此类并实现execute方法
    """

    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Skill

        Args:
            context: 执行上下文，包含输入数据和之前Skill的结果

        Returns:
            执行结果，会被merge到context中供后续Skill使用
        """
        pass

    def validate_input(self, context: Dict[str, Any]) -> bool:
        """验证输入参数"""
        return True


class SkillRegistry:
    """
    Skill注册表

    管理所有可用的Skill，支持动态注册和查询
    """

    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}
        self.categories: Dict[str, list] = {
            "vision": [],
            "database": [],
            "api": [],
            "calculation": []
        }

    def register(self, skill: BaseSkill):
        """注册新Skill"""
        self.skills[skill.name] = skill
        if skill.category in self.categories:
            self.categories[skill.category].append(skill.name)
        logger.info(f"Registered skill: {skill.name} ({skill.category})")

    def get(self, name: str) -> Optional[BaseSkill]:
        """获取Skill"""
        return self.skills.get(name)

    def get_by_category(self, category: str) -> list:
        """按分类获取Skill列表"""
        return self.categories.get(category, [])

    async def execute_pipeline(
        self,
        skill_names: list,
        initial_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行Skill流水线

        Args:
            skill_names: 要执行的Skill名称列表
            initial_context: 初始上下文

        Returns:
            最终context，包含所有Skill的执行结果
        """
        context = initial_context.copy()

        for skill_name in skill_names:
            skill = self.get(skill_name)
            if not skill:
                logger.warning(f"Skill not found: {skill_name}")
                continue

            try:
                result = await skill.execute(context)
                context.update(result)
                logger.debug(f"Skill {skill_name} executed successfully")
            except Exception as e:
                logger.error(f"Skill {skill_name} failed: {e}", exc_info=True)
                context[f"{skill_name}_error"] = str(e)

        return context


# 全局Skill注册表实例
skill_registry = SkillRegistry()
