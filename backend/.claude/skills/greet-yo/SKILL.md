---
name: greet-yo
description: A casual greeting skill that responds with "Hi xxx" when user says "Yo". Triggers when user greets with "Yo" or any casual greeting containing "Yo" (case-insensitive).
---

# Greet Yo

Responds to casual "Yo" greetings with a friendly "Hi {name}" response.

## Trigger

When user says "Yo", "yo", "Yo!", "yo!", or any casual greeting containing "Yo".

## Response Format

```text
Hi {greeting_name}, how can I help you?
```

## Example

- User: "Yo"
- Response: "Hi A神, how can I help you?" (uses the user's configured name)

## Notes

- Extract the user's name from context or system configuration
- Keep the response casual and friendly
- Respond directly without asking follow-up questions