from typing import List
from app.services.skill_dispatcher import Skill


class WeatherSkill(Skill):
    """Weather query skill - triggers on weather-related queries"""
    name = "weather"
    description = "查询天气预报"
    trigger_keywords = ["天气", "weather", "气温", "temperature"]

    async def execute(self, query: str, **kwargs) -> str:
        # Extract location from query (simplified)
        location = "北京"
        for word in ["北京", "上海", "深圳", "杭州", "广州"]:
            if word in query:
                location = word
                break
        
        # Placeholder - integrate with weather API
        return f"【{location}天气预报】\n今天: 晴，18-26°C\n明天: 多云，17-24°C\n后天: 小雨，15-22°C"


class CalculatorSkill(Skill):
    """Math calculator skill"""
    name = "calculator"
    description = "数学计算"
    trigger_keywords = ["计算", "calculate", "等于", "加起来", "相加"]

    async def execute(self, query: str, **kwargs) -> str:
        import re
        # Simple math expression extraction
        expr = query
        for keyword in ["计算", "calculate", "等于"]:
            expr = expr.replace(keyword, "")
        expr = expr.strip()
        
        try:
            # WARNING: eval in production should use safe math parser
            result = eval(expr, {"__builtins__": {}}, {})
            return f"计算结果: {expr} = {result}"
        except Exception as e:
            return f"无法计算: {expr}"


class ReminderSkill(Skill):
    """Quick reminder / timer skill"""
    name = "reminder"
    description = "设置提醒"
    trigger_keywords = ["提醒", "提醒我", "remind", "记得", "待会"]

    async def execute(self, query: str, **kwargs) -> str:
        # Extract time and content (simplified)
        import re
        time_pattern = r"(\d+)(分钟|小时|小时后|小时后)"
        match = re.search(time_pattern, query)
        
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            
            if "分钟" in unit:
                minutes = amount
            elif "小时" in unit:
                minutes = amount * 60
            else:
                minutes = amount
            
            # Extract reminder content
            content = query.replace(match.group(0), "").strip()
            return f"✅ 已设置 {minutes} 分钟后的提醒: {content or '无内容'}"
        
        return "请说 '提醒我 X 分钟后...'"


class QASkill(Skill):
    """General Q&A knowledge base skill"""
    name = "qa"
    description = "常见问答"
    trigger_keywords = ["什么是", "怎么", "如何", "why", "how", "what", "who"]

    async def execute(self, query: str, **kwargs) -> str:
        # Simple FAQ - in production, use vector search or knowledge graph
        faq = {
            "怎么改密码": "在设置页面点击'账户安全'->'修改密码'",
            "怎么联系客服": "可以发邮件到 support@company.com 或拨打 400-xxx-xxxx",
            "怎么升级会员": "进入'会员中心'选择套餐进行升级",
        }
        
        for question, answer in faq.items():
            if question in query:
                return f"【{question}】\n{answer}"
        
        return ""  # No match, let LLM handle it
