from fastapi import APIRouter, Depends
from app.models import User
from app.services.auth_service import get_current_user
from app.services.skill_dispatcher import SkillDispatcher

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/")
async def list_skills(
    user: User = Depends(get_current_user)
):
    # Note: SkillDispatcher needs db session - simplified here
    return [
        {"name": "weather", "description": "天气预报", "keywords": ["天气", "weather"]},
        {"name": "calculator", "description": "数学计算", "keywords": ["计算", "calculate"]},
        {"name": "reminder", "description": "设置提醒", "keywords": ["提醒", "remind"]},
        {"name": "qa", "description": "常见问答", "keywords": ["怎么", "如何", "什么是"]},
    ]


@router.get("/{skill_name}/execute")
async def execute_skill(
    skill_name: str,
    query: str = "",
    user: User = Depends(get_current_user)
):
    # Direct skill execution without db (for demo)
    from app.skills.builtin import WeatherSkill, CalculatorSkill, ReminderSkill, QASkill
    
    skills_map = {
        "weather": WeatherSkill(None, user),
        "calculator": CalculatorSkill(None, user),
        "reminder": ReminderSkill(None, user),
        "qa": QASkill(None, user),
    }
    
    skill = skills_map.get(skill_name)
    if not skill:
        return {"error": f"Skill '{skill_name}' not found"}
    
    result = await skill.execute(query)
    return {"skill": skill_name, "result": result}
