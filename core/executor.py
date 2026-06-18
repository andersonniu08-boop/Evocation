"""Execution engine — autonomously works through a Goal's Tasks."""

import json
from dataclasses import dataclass, field
from typing import Any

MAX_ITERATIONS = 5  # Max tool calls per task before halting

DESTRUCTIVE_TOOLS = {"bash", "write", "edit"}  # Tools requiring user approval

EXECUTOR_SYSTEM_PROMPT = """You are an autonomous coding agent executing a task plan. You are working through one task at a time from a larger goal.

## Current Context
Goal: {goal_title}
Objective: {goal_objective}

## Task Plan (remaining)
{tasks_remaining}

## Current Task
Task: {current_task}

## Previous Findings
{previous_findings}

## Instructions
1. Choose ONE tool call to advance the current task. Pick the most appropriate tool.
2. After the tool result, evaluate if the task is COMPLETE or needs MORE work.
3. If COMPLETE: describe what was accomplished in 1-2 sentences (these become findings).
4. If MORE: briefly note what still needs to be done.

## Response Format
Return ONLY valid JSON — no markdown, no prose:

If you need to execute a tool:
```json
{{"action": "tool", "tool": "read|write|edit|bash|glob|grep", "params": {{"key": "value"}}, "reasoning": "brief explanation"}}
```

If the task is complete:
```json
{{"action": "complete", "findings": "What was accomplished"}}
```

If the task failed:
```json
{{"action": "failed", "reason": "Why it failed"}}
```"""


@dataclass
class TaskContext:
    task: dict
    iterations: int = 0
    findings: list[str] = field(default_factory=list)
    status: str = "pending"


async def execute_goal(
    goal: dict,
    tasks: list[dict],
    provider,
    on_status=None,
    on_approval=None,
    max_iterations: int = MAX_ITERATIONS,
) -> dict:
    """Execute all pending tasks for a goal.

    Args:
        goal: Goal dict with title, objective, id
        tasks: List of task dicts (description, order, status)
        provider: BaseProvider instance
        on_status: Callback for status updates
        on_approval: Async callback for destructive tool approval (returns True/False)
        max_iterations: Max tool calls per task

    Returns:
        Dict with results: {completed, failed, findings_summary}
    """
    from core.provider import Message

    pending = [t for t in tasks if t.get("status") not in ("completed", "failed")]
    completed = 0
    failed = 0
    all_findings = []

    for task in pending:
        if on_status:
            on_status(f"Executing task: {task.get('description', '')[:80]}")

        ctx = TaskContext(task=task)

        for iteration in range(max_iterations):
            ctx.iterations = iteration + 1

            # Build the prompt
            tasks_remaining = "\n".join(
                f"- {t.get('description', '')}" for t in pending[pending.index(task) :]
            )
            previous_findings = "\n".join(ctx.findings[-3:]) if ctx.findings else "(none)"

            prompt = EXECUTOR_SYSTEM_PROMPT.format(
                goal_title=goal.get("title", "Untitled"),
                goal_objective=goal.get("objective", ""),
                tasks_remaining=tasks_remaining,
                current_task=task.get("description", ""),
                previous_findings=previous_findings,
            )

            messages = [Message(role="system", content=prompt)]
            response = await provider.chat_async(messages, tools=None)

            # Parse the LLM's decision
            decision = _parse_executor_response(response.content)
            if not decision:
                ctx.findings.append("LLM returned unparseable response")
                break

            action = decision.get("action", "")

            if action == "complete":
                ctx.findings.append(decision.get("findings", "Task completed"))
                ctx.status = "completed"
                completed += 1
                break

            elif action == "failed":
                ctx.findings.append(decision.get("reason", "Task failed"))
                ctx.status = "failed"
                failed += 1
                break

            elif action == "tool":
                tool_name = decision.get("tool", "")
                params = decision.get("params", {})

                if not tool_name:
                    ctx.findings.append("No tool specified")
                    break

                # Yield for approval on destructive tools
                if tool_name in DESTRUCTIVE_TOOLS and on_approval:
                    approved = await on_approval(tool_name, params, decision.get("reasoning", ""))
                    if not approved:
                        ctx.findings.append(f"User denied {tool_name} execution")
                        ctx.status = "paused"
                        break
                    if on_status:
                        on_status(f"Approved: {tool_name}")

                # Execute the tool
                if on_status:
                    on_status(f"Running: {tool_name}")

                result = await _execute_tool(tool_name, params)

                # Evaluate result
                if result.get("success"):
                    ctx.findings.append(
                        f"{tool_name}: {_summarize_result(result)}"
                    )
                else:
                    ctx.findings.append(
                        f"{tool_name} failed: {result.get('error', 'unknown error')}"
                    )

        # End of task iterations
        all_findings.extend(ctx.findings)
        task["findings"] = "\n".join(ctx.findings)
        task["status"] = ctx.status

    return {
        "completed": completed,
        "failed": failed,
        "findings_summary": "\n".join(all_findings[-20:]),
    }


def _parse_executor_response(content: str) -> dict | None:
    """Parse the LLM's JSON response, handling markdown fences."""
    import re

    if not content or not content.strip():
        return None

    raw = content.strip()

    # Strip markdown fences
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()

    # Extract JSON object
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _execute_tool(tool_name: str, params: dict) -> dict:
    """Execute a tool and return its result."""
    from core.tools import execute_tool

    import asyncio

    result = await asyncio.to_thread(execute_tool, tool_name, params)
    return result


def _summarize_result(result: dict) -> str:
    """Extract a brief summary from a tool result."""
    content = result.get("content", "")
    stdout = result.get("stdout", "")
    matches = result.get("matches", [])
    if isinstance(matches, list) and matches:
        return f"Found {len(matches)} matches"
    if content:
        return content[:120]
    if stdout:
        return stdout[:120]
    return str(result)[:120]
