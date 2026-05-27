from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List


DEFAULT_AGENT_SKILLS = [
    {
        "name": "calculator",
        "description": "数学计算器。当用户需要计算、求值、数学运算时使用。支持基本四则运算。",
        "summary": "当用户需要计算时，使用 Bash 工具执行 Python 计算：",
    },
    {
        "name": "qa",
        "description": "常见问题解答。当用户询问\"怎么改密码\"、\"怎么联系客服\"、\"怎么升级会员\"等 FAQ 问题时使用。",
        "summary": "| 问题 | 答案 |",
    },
    {
        "name": "reminder",
        "description": "设置提醒。当用户说\"提醒我\"、\"记得\"、\"X分钟后提醒\"时使用。",
        "summary": "当用户设置提醒时：",
    },
    {
        "name": "weather",
        "description": "查询天气预报。当用户询问天气、气温、天气预报时使用。支持城市：北京、上海、深圳、杭州、广州等。",
        "summary": "调用 `/api/skills/weather/execute` 接口查询天气。",
    },
]


def get_skills_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".claude" / "skills"


def _parse_skill_file(skill_file: Path) -> Dict[str, str]:
    content = skill_file.read_text(encoding="utf-8")
    name = skill_file.parent.name
    description = ""

    frontmatter = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if frontmatter:
        for line in frontmatter.group(1).splitlines():
            key, _, value = line.partition(":")
            if not _:
                continue
            if key.strip() == "name":
                name = value.strip()
            elif key.strip() == "description":
                description = value.strip()

    body = re.sub(r"^---\s*\n.*?\n---\s*\n*", "", content, flags=re.DOTALL)
    summary = ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            summary = stripped[:120]
            break

    return {
        "name": name,
        "description": description,
        "summary": summary,
    }


def get_agent_skills() -> List[Dict[str, str]]:
    skills_dir = get_skills_dir()
    discovered: List[Dict[str, str]] = []

    if skills_dir.is_dir():
        for entry in sorted(skills_dir.iterdir()):
            skill_file = entry / "SKILL.md"
            if not skill_file.is_file():
                continue
            try:
                discovered.append(_parse_skill_file(skill_file))
            except Exception:
                continue

    if discovered:
        return discovered

    return [dict(skill) for skill in DEFAULT_AGENT_SKILLS]


def get_agent_skill_names() -> List[str]:
    return [skill["name"] for skill in get_agent_skills()]


def build_skills_prompt() -> str:
    lines: List[str] = []
    for skill in get_agent_skills():
        skill_line = f"### /{skill['name']} - {skill['description']}" if skill.get("description") else f"### /{skill['name']}"
        lines.append(skill_line)
        if skill.get("summary"):
            lines.append(f"  {skill['summary']}")
    return "\n".join(lines)