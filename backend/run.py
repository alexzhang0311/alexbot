#!/usr/bin/env python3
"""Windows 兼容入口 — 必须在任何 asyncio 使用之前设置 ProactorEventLoopPolicy"""

import sys

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # Verify it took effect
    loop = asyncio.new_event_loop()
    print(f"[run.py] Loop type: {type(loop).__name__}")
    loop.close()

if __name__ == "__main__":
    import uvicorn
    print("[run.py] Starting uvicorn...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
