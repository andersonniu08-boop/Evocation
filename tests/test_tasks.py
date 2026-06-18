"""Tests for Task CRUD and goal progress calculation."""
import pytest
from core.bridge import (
    _task_row,
    _calc_goal_progress,
    handle_create_tasks,
    handle_update_task,
    handle_get_tasks,
    handle_get_goal_progress,
)


class TestTaskRow:
    def test_maps_all_fields(self):
        row = {
            "id": "abc-123",
            "goal_id": "goal-1",
            "description": "Add login endpoint",
            "status": "pending",
            "order": 2,
            "findings": "",
            "notes": "",
            "started_at": None,
            "completed_at": None,
            "created_at": "2026-01-01",
        }
        result = _task_row(row)
        assert result["id"] == "abc-123"
        assert result["goal_id"] == "goal-1"
        assert result["description"] == "Add login endpoint"
        assert result["status"] == "pending"
        assert result["order"] == 2
        assert result["findings"] == ""
        assert result["notes"] == ""
        assert result["started_at"] is None
        assert result["completed_at"] is None

    def test_null_handling(self):
        row = {
            "id": "x", "goal_id": "g", "description": "test",
            "status": "pending", "order": 0,
            "findings": None, "notes": None,
            "started_at": None, "completed_at": None,
            "created_at": "2026-01-01",
        }
        result = _task_row(row)
        assert result["findings"] == ""
        assert result["notes"] == ""


class TestTaskCRUD:
    @pytest.mark.asyncio
    async def test_create_tasks_validates_goal(self):
        result = await handle_create_tasks({"goal_id": "", "tasks": []})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_create_tasks_requires_tasks(self):
        result = await handle_create_tasks({"goal_id": "abc", "tasks": []})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_update_task_requires_id(self):
        result = await handle_update_task({"task_id": ""})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_tasks_requires_goal_id(self):
        result = await handle_get_tasks({"goal_id": ""})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_goal_progress_requires_goal_id(self):
        result = await handle_get_goal_progress({"goal_id": ""})
        assert "error" in result


class TestGoalProgress:
    @pytest.mark.asyncio
    async def test_progress_structure(self):
        """Verify progress calculation returns correct structure."""
        class MockConn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def fetchrow(self, *a, **kw):
                return {
                    "total": 7,
                    "completed": 2,
                    "failed": 1,
                    "in_progress": 1,
                }

        class MockPool:
            def acquire(self):
                return MockConn()

        result = await _calc_goal_progress("goal-1", MockPool())
        assert result["total"] == 7
        assert result["completed"] == 2
        assert result["failed"] == 1
        assert result["in_progress"] == 1
        assert result["percentage"] == 29  # 2/7 ≈ 29%
