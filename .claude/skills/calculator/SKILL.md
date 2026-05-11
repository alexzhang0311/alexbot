---
name: calculator
description: 数学计算器。当用户需要计算、求值、数学运算时使用。支持基本四则运算。
---

# 数学计算器

## 使用方式

当用户需要计算时，使用 Bash 工具执行 Python 计算：

```bash
python3 -c "print(表达式)"
```

例如用户说"计算 123 + 456"：

```bash
python3 -c "print(123 + 456)"
```

⚠️ 安全注意：只计算纯数学表达式，不执行任意 Python 代码。使用 `ast.literal_eval` 或简单算术。
