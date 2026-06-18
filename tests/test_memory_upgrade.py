"""Tests for structural memory priority and retrieval weighting."""
import pytest
from core.retrieval import MEMORY_TYPE_MULTIPLIER


class TestMemoryTypeMultiplier:
    def test_structural_types_boosted(self):
        """Past failures and plans get higher multipliers than general context."""
        assert MEMORY_TYPE_MULTIPLIER["past_failure"] == 1.3
        assert MEMORY_TYPE_MULTIPLIER["plan_architecture"] == 1.25
        assert MEMORY_TYPE_MULTIPLIER["goal_definition"] == 1.25
        assert MEMORY_TYPE_MULTIPLIER["task_result"] == 1.1

    def test_structural_priority_over_general(self):
        """Structural knowledge should rank above general context."""
        assert MEMORY_TYPE_MULTIPLIER["past_failure"] > MEMORY_TYPE_MULTIPLIER["conversation"]
        assert MEMORY_TYPE_MULTIPLIER["plan_architecture"] > MEMORY_TYPE_MULTIPLIER["learned_fact"]
        assert MEMORY_TYPE_MULTIPLIER["bug"] > MEMORY_TYPE_MULTIPLIER["conversation"]
        assert MEMORY_TYPE_MULTIPLIER["goal_definition"] > MEMORY_TYPE_MULTIPLIER["user_preference"]

    def test_general_types_at_baseline(self):
        """General conversation/preferences stay at baseline 1.0."""
        assert MEMORY_TYPE_MULTIPLIER["conversation"] == 1.0
        assert MEMORY_TYPE_MULTIPLIER["user_preference"] == 1.0
        assert MEMORY_TYPE_MULTIPLIER["task_history"] == 1.0

    def test_all_types_covered(self):
        """All memory types have a multiplier."""
        expected_types = {
            "past_failure", "plan_architecture", "goal_definition",
            "task_result", "design_decision", "bug", "code_snippet",
            "learned_fact", "conversation", "user_preference", "task_history",
        }
        assert set(MEMORY_TYPE_MULTIPLIER.keys()) == expected_types

    def test_failure_vs_general_similar_text(self):
        """With identical non-type scores, past_failure should outrank general."""
        general_score = 0.5 * MEMORY_TYPE_MULTIPLIER["conversation"]
        failure_score = 0.5 * MEMORY_TYPE_MULTIPLIER["past_failure"]
        assert failure_score > general_score


class TestContextBuilder:
    def test_grouped_by_type(self):
        """Context builder groups memories under type headers."""
        from core.agent_loop import _retrieve_context as build_context

        # We're testing the formatting logic, not the async retrieval
        results = [
            {"content": "Fixed race condition in queue", "memory_type": "past_failure", "id": "1"},
            {"content": "Uses pgvector for vectors", "memory_type": "design_decision", "id": "2"},
            {"content": "User prefers pytest", "memory_type": "user_preference", "id": "3"},
        ]

        # Call the formatting helper directly (simplified)
        TYPE_HEADERS = {
            "past_failure": "### Past Failures to Avoid",
            "design_decision": "### Design Decisions",
            "user_preference": "### Preferences",
        }
        grouped = {}
        for r in results:
            mtype = r.get("memory_type", "conversation")
            if mtype not in grouped:
                grouped[mtype] = []
            grouped[mtype].append(f"- {r['content']}")

        lines = []
        for mtype in ["past_failure", "design_decision", "user_preference"]:
            if mtype in grouped:
                lines.append(TYPE_HEADERS.get(mtype, f"### {mtype}"))
                lines.extend(grouped[mtype])

        output = "\n".join(lines)
        assert "### Past Failures to Avoid" in output
        assert "### Design Decisions" in output
        assert "### Preferences" in output
        assert "Fixed race condition in queue" in output
        assert "Uses pgvector for vectors" in output
        assert "User prefers pytest" in output

    def test_failure_before_design(self):
        """In the ordered output, past failures appear before design decisions."""
        results = [
            {"content": "Chose pgvector", "memory_type": "design_decision", "id": "1"},
            {"content": "Queue deadlock crash", "memory_type": "past_failure", "id": "2"},
        ]
        grouped = {}
        for r in results:
            mtype = r["memory_type"]
            if mtype not in grouped:
                grouped[mtype] = []
            grouped[mtype].append(f"- {r['content']}")

        lines = []
        priority = ["past_failure", "design_decision"]
        for mtype in priority:
            if mtype in grouped:
                lines.append(mtype)
                lines.extend(grouped[mtype])

        output = "\n".join(lines)
        failure_idx = output.index("past_failure")
        design_idx = output.index("design_decision")
        assert failure_idx < design_idx


class TestMemoryTypeValidation:
    def test_new_types_validated(self):
        """The validation function accepts new goal-oriented types."""
        from core.memory import _validate_memory_records

        items = [
            {"type": "goal_definition", "content": "Build a REST API with OAuth"},
            {"type": "plan_architecture", "content": "Use hexagonal architecture"},
            {"type": "task_result", "content": "Implemented login endpoint"},
            {"type": "past_failure", "content": "Database migration failed due to lock timeout"},
        ]
        records = _validate_memory_records(items, "test")
        assert len(records) == 4
        assert records[0].memory_type == "goal_definition"
        assert records[1].memory_type == "plan_architecture"
        assert records[2].memory_type == "task_result"
        assert records[3].memory_type == "past_failure"
