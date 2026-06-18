"""Planner module — generates structured task plans from goal objectives."""

import json
import re

PLANNER_SYSTEM_PROMPT = """You are a senior software architect breaking down a coding objective into discrete, sequential, executable tasks.

Given a goal objective, produce a JSON array of tasks. Each task must be a specific, actionable coding step — not high-level advice.

Rules:
- Each task should be independently executable (one file, one change, one test).
- Tasks must be ordered sequentially — each builds on the previous.
- Return ONLY a JSON array of objects. No markdown, no prose.
- Each object must have: "description" (string), "order" (integer starting at 1).

Example input: "Add authentication to the Flask app"

Example output:
```json
[
  {"description": "Create User model with password hashing", "order": 1},
  {"description": "Add login endpoint POST /auth/login", "order": 2},
  {"description": "Add JWT token generation and validation", "order": 3},
  {"description": "Add register endpoint POST /auth/register", "order": 4},
  {"description": "Write auth integration tests", "order": 5}
]
```

Now produce a plan for the following objective. Return ONLY valid JSON — no other text.

Objective: {objective}"""


async def generate_plan(objective: str, provider) -> list[dict]:
    """Generate a task plan from an objective using the LLM provider.

    Args:
        objective: The goal objective to plan for.
        provider: A BaseProvider instance (LiteLLMProvider or OllamaProvider).

    Returns:
        A list of task dicts with 'description' and 'order' keys.

    Raises:
        ValueError: If the LLM fails to produce valid JSON after retries.
    """
    from core.provider import Message

    prompt = PLANNER_SYSTEM_PROMPT.format(objective=objective)
    messages = [Message(role="system", content=prompt)]

    max_retries = 3
    last_error = None
    raw = ""

    for attempt in range(max_retries):
        try:
            response = await provider.chat_async(messages, tools=None)
            raw = response.content.strip() if response.content else ""

            if not raw:
                last_error = "Empty response from LLM"
                continue

            tasks = _parse_plan_json(raw)
            if tasks and len(tasks) > 0:
                return tasks

            last_error = "Failed to extract valid task list from response"
        except Exception as e:
            last_error = str(e)

    raise ValueError(f"Planner failed after {max_retries} attempts: {last_error}\nRaw response: {raw[:300]}")


def _parse_plan_json(raw: str) -> list[dict] | None:
    """Parse LLM output into a validated task list."""
    # Strip markdown fences
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    text = m.group(1).strip() if m else raw

    # Extract JSON array
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        text = m.group(0)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, list):
        data = [data]

    tasks = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description", "")).strip()
        if not desc:
            continue
        order = int(item.get("order", i + 1))
        tasks.append({"description": desc, "order": order})

    return sorted(tasks, key=lambda t: t["order"])
