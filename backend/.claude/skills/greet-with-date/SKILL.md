---
name: greet-with-date
description: A friendly greeting skill that responds with "Hi, 我的A神，今天是xxxx年x月x日x点x分". Triggers when user says "HELLO" or any greeting words.
---

# Greet With Date

## Overview

When user says "HELLO" (case-insensitive), respond with a friendly greeting including the current date and time.

## Response Format

When triggered, reply in this exact format:

```
Hi, 我的A神，今天是{year}年{month}月{day}日{hour}点{minute}分
```

Replace placeholders with actual current date/time.

## Examples

- User: "HELLO" → Reply: "Hi, 我的A神，今天是2026年5月12日15点30分"
- User: "Hello there!" → Reply: "Hi, 我的A神，今天是2026年5月12日15点30分"
