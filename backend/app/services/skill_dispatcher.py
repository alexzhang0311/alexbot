from typing import Dict, List, Optional, Callable, Any
from app.models import User
from app.core.database import AsyncSession


class Skill:
    """
    Base Skill class.
    Each skill has:
    - name: unique identifier
    - description: what it does
    - trigger_keywords: keywords that may trigger this skill
    - execute(): main logic
    """
    name: str = "base_skill"
    description: str = ""
    trigger_keywords: List[str] = []

    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    async def execute(self, query: str, **kwargs) -> str:
        """Execute the skill. Returns result text."""
        raise NotImplementedError

    def should_trigger(self, query: str) -> bool:
        """Check if query matches trigger conditions"""
        query_lower = query.lower()
        return any(kw in query_lower for kw in self.trigger_keywords)


class SkillDispatcher:
    """
    Routes queries to appropriate skills.
    Manages skill lifecycle and result aggregation.
    """
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self._skills: Dict[str, Skill] = {}
        self._register_builtin_skills()

    def _register_builtin_skills(self):
        """Register built-in skills"""
        from app.skills.builtin import (
            WeatherSkill, CalculatorSkill, 
            ReminderSkill, QASkill
        )
        
        self.register(WeatherSkill)
        self.register(CalculatorSkill)
        self.register(ReminderSkill)
        self.register(QASkill)

    def register(self, skill_class: type[Skill]):
        """Register a skill class"""
        skill_instance = skill_class(self.db, self.user)
        self._skills[skill_instance.name] = skill_instance

    def unregister(self, name: str):
        """Unregister a skill"""
        self._skills.pop(name, None)

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, str]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "keywords": s.trigger_keywords,
            }
            for s in self._skills.values()
        ]

    async def check_and_execute(
        self, 
        query: str, 
        skill_names: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Check which skills should be triggered and execute them.
        Returns dict of {skill_name: result}
        """
        results = {}
        
        # Filter skills to check
        skills_to_check = self._skills
        if skill_names:
            skills_to_check = {
                name: s for name, s in self._skills.items() 
                if name in skill_names
            }
        
        for name, skill in skills_to_check.items():
            if skill.should_trigger(query):
                try:
                    result = await skill.execute(query)
                    results[name] = result
                except Exception as e:
                    results[name] = f"Error: {str(e)}"
        
        return results

    async def execute_skill(self, name: str, query: str, **kwargs) -> str:
        """Execute a specific skill by name"""
        skill = self._skills.get(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found")
        return await skill.execute(query, **kwargs)
