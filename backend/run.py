#!/usr/bin/env python3
"""Windows 兼容入口 — 必须在 uvicorn 之前设置 SelectorEventLoopPolicy"""

import sys

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
