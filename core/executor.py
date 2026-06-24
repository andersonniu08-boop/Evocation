"""Execution engine — autonomous state-machine loop through Goal Tasks.

State flow:
  IDLE → EXECUTING → WAITING_APPROVAL → EXECUTING → (COMPLETE or FAILED or PAUSED)
                                           ↓ deny
                                         PAUSED
"""

import json
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.logger import (
    log_error,
    log_info,
    log_llm_request,
    log_state_transition,
    log_tool_call,
)
from core.tools import tool_requires_approval

MAX_ITERATIONS = 10  # Max tool calls per task before halting
MAX_ALTERNATIVES = 2  # Max alternative strategies after a tool rejection


class ExecutorState(StrEnum):
    IDLE = "idle"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


EXECUTOR_SYSTEM_PROMPT = """You are an autonomous coding agent executing a task plan. Work through one task at a time from a larger goal.

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
{{"action": "tool", "tool": "read|write|edit|bash|glob|grep", "params": {{"key": "value"}}, "reasoning": "brief explanation of why this tool"}}
```

If the task is complete:
```json
{{"action": "complete", "findings": "What was accomplished — concrete details"}}
```

If the task failed (cannot proceed):
```json
{{"action": "failed", "reason": "Why it failed — be specific"}}
```"""


EVALUATION_PROMPT = """Evaluate whether the tool output below completes the current task.

## Current Task
{current_task}

## Goal Context
{goal_context}

## Tool Executed
Tool: {tool_name}
Result: {tool_result}

## Instructions
Determine if this task is now COMPLETE or needs MORE work.
Return ONLY valid JSON:

If complete:
```json
{{"decision": "complete", "findings": "Concise summary of what was achieved"}}
```

If more work needed:
```json
{{"decision": "more", "next_action": "What to do next"}}
```

If the tool failed or can't proceed:
```json
{{"decision": "failed", "reason": "Why we cannot continue"}}
```"""


@dataclass
class TaskContext:
    task: dict
    iterations: int = 0
    findings: list[str] = field(default_factory=list)
    status: str = "pending"


@dataclass
class ExecutorContext:
    goal: dict
    tasks: list[dict]
    current_state: ExecutorState = ExecutorState.IDLE
    completed: int = 0
    failed: int = 0
    paused_task: TaskContext | None = None
    pending_approval: dict | None = None  # {tool, params, reasoning, task_ctx}

    @property
    def total_done(self) -> int:
        return self.completed + self.failed

    @property
    def remaining(self) -> int:
        return len([t for t in self.tasks if t.get("status") not in ("completed", "failed")])


async def execute_goal(
    goal: dict,
    tasks: list[dict],
    provider,
    on_status=None,
    on_approval=None,
    max_iterations: int = MAX_ITERATIONS,
) -> dict:
    """Execute all pending tasks for a goal with state-machine flow.

    Args:
        goal: Goal dict with title, objective, id
        tasks: List of task dicts (description, order, status) — mutated in place
        provider: BaseProvider instance
        on_status: Callback(status_message: str) for status updates
        on_approval: Async callback(tool_name, params, reasoning) → bool
        max_iterations: Max tool calls per task before halting

    Returns:
        Dict with {completed, failed, findings_summary, final_state}
    """
    from core.provider import Message

    ctx = ExecutorContext(goal=goal, tasks=tasks)
    ctx.current_state = ExecutorState.EXECUTING

    log_state_transition("Executor", ExecutorState.IDLE.value, ExecutorState.EXECUTING.value,
                        {"goal_id": goal.get("id", ""), "task_count": len(tasks),
                         "pending": len([t for t in tasks if t.get("status") not in ("completed", "failed")])})

    pending = [t for t in tasks if t.get("status") not in ("completed", "failed")]

    for task_idx, task in enumerate(pending):
        # Check if executor was paused (approval denied)
        if ctx.current_state == ExecutorState.PAUSED:
            break

        tctx = TaskContext(task=task)
        status_msg = f"Task {ctx.total_done + 1}/{len(tasks)}: {task.get('description', '')[:80]}"
        if on_status:
            on_status(status_msg)

        await _execute_single_task(ctx, tctx, task_idx, pending, goal, provider, on_status, on_approval, max_iterations)

        # Persist findings and status back to task dict
        task["findings"] = "\n".join(tctx.findings)
        task["status"] = tctx.status

        if tctx.status == "completed":
            ctx.completed += 1
        elif tctx.status == "failed":
            ctx.failed += 1
        elif tctx.status == "paused":
            ctx.current_state = ExecutorState.PAUSED
            break

    if ctx.current_state != ExecutorState.PAUSED:
        ctx.current_state = ExecutorState.COMPLETED if ctx.failed == 0 else ExecutorState.COMPLETED

    log_state_transition("Executor", ExecutorState.EXECUTING.value, ctx.current_state.value,
                        {"completed": ctx.completed, "failed": ctx.failed, "remaining": ctx.remaining})

    all_findings = []
    for t in tasks:
        f = t.get("findings", "")
        if f:
            all_findings.append(f)

    return {
        "completed": ctx.completed,
        "failed": ctx.failed,
        "findings_summary": "\n---\n".join(all_findings[-20:]),
        "final_state": ctx.current_state.value,
    }


async def _execute_single_task(
    ctx: ExecutorContext,
    tctx: TaskContext,
    task_idx: int,
    pending: list[dict],
    goal: dict,
    provider,
    on_status,
    on_approval,
    max_iterations: int,
):
    """Execute one task through the tool→evaluate→repeat loop."""
    from core.provider import Message

    task = tctx.task

    for iteration in range(max_iterations):
        tctx.iterations = iteration + 1

        # Build prompt with accumulated findings
        tasks_remaining = "\n".join(
            f"{i+1}. {t.get('description', '')}"
            for i, t in enumerate(pending[task_idx:])
        )
        previous_findings = "\n".join(tctx.findings[-5:]) if tctx.findings else "(none)"

        # Format goal context for the current task
        goal_context = f"Goal: {goal.get('title', '')} — {goal.get('objective', '')}"

        # Step 1: Ask LLM what tool to use (or declare completion)
        action_prompt = EXECUTOR_SYSTEM_PROMPT.format(
            goal_title=goal.get("title", "Untitled"),
            goal_objective=goal.get("objective", ""),
            tasks_remaining=tasks_remaining,
            current_task=task.get("description", ""),
            previous_findings=previous_findings,
        )

        messages = [Message(role="system", content=action_prompt)]
        t0 = time.time()
        response = await provider.chat_async(messages, tools=None)
        latency = (time.time() - t0) * 1000
        log_llm_request("Executor", getattr(provider, "model", "unknown"),
                       response.token_count, latency_ms=latency,
                       purpose=f"action_decision",
                       metadata={"task": tctx.task.get("description", "")[:80], "iteration": iteration + 1})
        decision = _parse_executor_response(response.content)

        if not decision:
            tctx.findings.append("[Error] LLM returned unparseable response")
            tctx.status = "failed"
            return

        action = decision.get("action", "")

        # ── Task is complete ──
        if action == "complete":
            findings = decision.get("findings", "Task completed")
            tctx.findings.append(findings)
            tctx.status = "completed"
            if on_status:
                on_status(f"  ✓ Complete: {findings[:100]}")
            return

        # ── Task failed ──
        if action == "failed":
            reason = decision.get("reason", "Task failed")
            tctx.findings.append(f"[Failed] {reason}")
            tctx.status = "failed"
            if on_status:
                on_status(f"  ✗ Failed: {reason[:100]}")
            return

        # ── Execute a tool ──
        if action == "tool":
            tool_name = decision.get("tool", "")
            params = decision.get("params", {})
            reasoning = decision.get("reasoning", "")

            if not tool_name:
                tctx.findings.append("[Error] No tool specified in tool action")
                tctx.status = "failed"
                return

            # ── Approval check using tool definition flag ──
            requires_approval = tool_requires_approval(tool_name)
            log_tool_call(
                "Executor", tool_name, params,
                metadata={"iteration": iteration + 1, "requires_approval": requires_approval},
            )

            if requires_approval and on_approval:
                log_state_transition("Executor", ctx.current_state.value, ExecutorState.WAITING_APPROVAL.value,
                                    {"tool": tool_name, "task": tctx.task.get("description", "")[:80]})
                ctx.current_state = ExecutorState.WAITING_APPROVAL
                ctx.pending_approval = {
                    "tool": tool_name,
                    "params": params,
                    "reasoning": reasoning,
                    "task_ctx": tctx,
                }
                if on_status:
                    on_status(f"  ⚠ Waiting approval for: {tool_name}")

                approved = await on_approval(tool_name, params, reasoning)
                ctx.pending_approval = None

                if not approved:
                    log_state_transition("Executor", ExecutorState.WAITING_APPROVAL.value, ExecutorState.PAUSED.value,
                                        {"tool": tool_name, "reason": "user_denied"})
                    tctx.findings.append(f"[Denied] User denied {tool_name} execution")

                    # ── Ask LLM for alternative strategy ──
                    alt_result = await _request_alternative(
                        tctx, tool_name, reasoning, provider, on_status
                    )
                    if alt_result:
                        tctx.findings.append(f"[Alternative] {alt_result}")
                        ctx.current_state = ExecutorState.EXECUTING
                        continue  # Retry loop with alternative approach

                    tctx.status = "paused"
                    ctx.current_state = ExecutorState.PAUSED
                    return

                log_state_transition("Executor", ExecutorState.WAITING_APPROVAL.value, ExecutorState.EXECUTING.value,
                                    {"tool": tool_name})
                ctx.current_state = ExecutorState.EXECUTING
                if on_status:
                    on_status(f"  ✓ Approved: {tool_name}")

            # ── Execute the tool ──
            if on_status:
                on_status(f"  ⚡ Running: {tool_name}")

            result = await _execute_tool(tool_name, params)
            result_summary = _summarize_result(result)
            log_tool_call("Executor", tool_name, params,
                         result_summary=result_summary,
                         metadata={"iteration": iteration + 1, "success": result.get("success", False)})

            # ── Step 2: Evaluate if tool output completes the task ──
            eval_prompt = EVALUATION_PROMPT.format(
                current_task=task.get("description", ""),
                goal_context=goal_context,
                tool_name=tool_name,
                tool_result=result_summary,
            )

            eval_messages = [Message(role="system", content=eval_prompt)]
            t0 = time.time()
            eval_response = await provider.chat_async(eval_messages, tools=None)
            latency = (time.time() - t0) * 1000
            log_llm_request("Executor", getattr(provider, "model", "unknown"),
                           eval_response.token_count, latency_ms=latency,
                           purpose="evaluate_task",
                           metadata={"tool": tool_name, "iteration": iteration + 1})
            eval_decision = _parse_executor_response(eval_response.content)

            if eval_decision and eval_decision.get("decision") == "complete":
                findings = eval_decision.get("findings", f"{tool_name}: {result_summary}")
                tctx.findings.append(findings)
                tctx.status = "completed"
                if on_status:
                    on_status(f"  ✓ Done: {findings[:100]}")
                return

            elif eval_decision and eval_decision.get("decision") == "failed":
                reason = eval_decision.get("reason", "Tool failed to make progress")
                tctx.findings.append(f"[Failed] {reason}")
                tctx.status = "failed"
                if on_status:
                    on_status(f"  ✗ Failed: {reason[:100]}")
                return

            else:
                # More work needed — record finding and continue loop
                finding = f"[{tool_name}] {result_summary}"
                tctx.findings.append(finding)
                if eval_decision:
                    next_action = eval_decision.get("next_action", "Continue")
                    tctx.findings.append(f"  → Next: {next_action}")
                if on_status:
                    on_status(f"  ↻ More work needed (iteration {iteration + 1}/{max_iterations})")

    # Exhausted max iterations
    tctx.findings.append(f"[Halted] Reached max iterations ({max_iterations}) without completing")
    tctx.status = "failed"


async def _request_alternative(
    tctx: "TaskContext",
    denied_tool: str,
    reasoning: str,
    provider,
    on_status=None,
) -> str | None:
    """Ask LLM for alternative approach after a tool was denied.

    Returns a new strategy string, or None if no alternatives remain.
    """
    from core.provider import Message

    alt_count = sum(1 for f in tctx.findings if "[Alternative]" in f)
    if alt_count >= MAX_ALTERNATIVES:
        return None

    prompt = f"""The tool `{denied_tool}` was denied by the user. Reason: {reasoning}

Current task: {tctx.task.get("description", "")}

Propose ONE alternative approach that does NOT use `{denied_tool}`.
Return ONLY valid JSON:
```json
{{"strategy": "Describe the alternative approach in one sentence"}}
```
If no alternative is viable, return:
```json
{{"strategy": null}}
```"""

    messages = [Message(role="system", content=prompt)]
    response = await provider.chat_async(messages, tools=None)

    decision = _parse_executor_response(response.content)
    if decision and decision.get("strategy"):
        strategy = str(decision["strategy"])
        log_info("Executor", f"Alternative strategy: {strategy[:100]}",
                {"denied_tool": denied_tool, "alt_count": alt_count + 1})
        return strategy
    return None


def _parse_executor_response(content: str) -> dict | None:
    """Parse LLM JSON response, handling markdown fences and malformed output."""
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
    """Execute a tool via the registry and return its result."""
    from core.tools import execute_tool

    import asyncio

    result = await asyncio.to_thread(execute_tool, tool_name, params)
    return result


def _summarize_result(result: dict) -> str:
    """Extract a concise summary from a tool result for the evaluator."""
    if not result.get("success", True):
        return result.get("error", "Unknown error")

    content = result.get("content", "")
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    matches = result.get("matches", [])

    if isinstance(matches, list) and matches:
        return f"Found {len(matches)} matches: {', '.join(str(m)[:60] for m in matches[:3])}"

    if content:
        return content[:200]

    if stdout:
        return stdout[:200]

    if stderr:
        return f"stderr: {stderr[:200]}"

    return str(result)[:200]
