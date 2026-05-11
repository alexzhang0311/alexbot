#!/usr/bin/env python3
"""
Claude Agent SDK 工具调用测试 Demo

用法:
  export ANTHROPIC_API_KEY='sk-your-key'
  export ANTHROPIC_BASE_URL='https://api.anthropic.com'   # Anthropic 官方
  # export ANTHROPIC_BASE_URL='https://api.minimaxi.com/anthropic'  # MiniMax
  # export ANTHROPIC_BASE_URL='https://api.deepseek.com/anthropic'  # DeepSeek
  python demo/test_claude_sdk.py

或直接命令行传参:
  python demo/test_claude_sdk.py "sk-key" "https://api.anthropic.com" "claude-sonnet-4-20250514"
"""

import os
import sys
import asyncio

# ── 配置 ──────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def log(label: str, text: str, color: str = ""):
    print(f"{color}[{label}]{Colors.RESET} {text}")


async def main(api_key: str, base_url: str, model: str):
    if not api_key:
        print(f"{Colors.RED}❌ 请设置 ANTHROPIC_API_KEY！{Colors.RESET}")
        return

    os.environ["ANTHROPIC_API_KEY"] = api_key
    os.environ["ANTHROPIC_BASE_URL"] = base_url

    print(f"\n{Colors.BOLD}{'='*55}{Colors.RESET}")
    print(f"{Colors.BOLD}  Claude Agent SDK 工具调用测试{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*55}{Colors.RESET}")
    print(f"  API:   {base_url}")
    print(f"  Model: {model}")
    print(f"  Tools: Bash, Read, Write, Edit, Glob, Grep")
    print(f"{'='*55}\n")

    from claude_agent_sdk import query, ClaudeAgentOptions

    options = ClaudeAgentOptions(
        model=model,
        allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        max_turns=3,
        cwd=os.getcwd(),
    )

    prompt = "运行 pwd 然后 ls -la 当前目录，告诉我看到了什么"

    print(f"{Colors.CYAN}➤ 用户:{Colors.RESET} {prompt}\n")

    tool_count = 0
    collected_tools = []
    stderr_lines = []

    def _stderr_cb(line: str):
        stderr_lines.append(line.rstrip())

    options.stderr = _stderr_cb

    try:
        async for msg in query(prompt=prompt, options=options):
            if not hasattr(msg, "content"):
                continue

            for block in msg.content:
                block_type = getattr(block, "type", None)

                if block_type == "tool_use":
                    tool_count += 1
                    name = getattr(block, "name", "?")
                    inp = getattr(block, "input", {})
                    collected_tools.append(name)

                    log(f"🔧 TOOL_USE", f"{Colors.YELLOW}{name}{Colors.RESET}",
                        Colors.YELLOW)
                    for k, v in inp.items():
                        log("  ├─", f"{k} = {v}")

                elif block_type == "text":
                    text = getattr(block, "text", "")
                    sys.stdout.write(f"{Colors.GREEN}{text}{Colors.RESET}")
                    sys.stdout.flush()

                elif block_type == "tool_result":
                    # tool_result 出现在后续消息中
                    output = str(getattr(block, "content", ""))[:200]
                    is_err = getattr(block, "is_error", False)
                    if is_err:
                        log("❌ TOOL_ERR", output[:120], Colors.RED)

    except Exception as e:
        log("ERROR", str(e), Colors.RED)
        if stderr_lines:
            print(f"\n{Colors.YELLOW}STDERR:{Colors.RESET}")
            for line in stderr_lines[-10:]:
                print(f"  {line}")
        print(f"\n{Colors.RED}💡 缺少 claude CLI？确认: which claude{Colors.RESET}")
        return

    print()  # 换行

    # ── 结果 ──
    print(f"{Colors.BOLD}{'='*55}{Colors.RESET}")
    if tool_count > 0:
        print(f"{Colors.GREEN}✅ 工具调用成功！{Colors.RESET}")
        print(f"   共 {tool_count} 次: {collected_tools}")
    else:
        print(f"{Colors.RED}❌ 零工具调用{Colors.RESET}")
        print(f"   当前 API ({base_url}) 不支持 Anthropic tool_use")
        print(f"   换 Anthropic 官方 API Key 再试: https://console.anthropic.com")
    print(f"{Colors.BOLD}{'='*55}{Colors.RESET}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
        base_url = sys.argv[2] if len(sys.argv) > 2 else "https://api.anthropic.com"
        model = sys.argv[3] if len(sys.argv) > 3 else "claude-sonnet-4-20250514"
    else:
        api_key = ANTHROPIC_API_KEY
        base_url = ANTHROPIC_BASE_URL
        model = ANTHROPIC_MODEL

    asyncio.run(main(api_key, base_url, model))
