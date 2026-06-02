"""Hybrid retrieval ranking formula."""
import math


def score_memory(
    vector_score: float,
    bm25_score: float,
    days_since_access: float,
    importance: float,
    decay_factor: float,
    same_workspace: bool,
    access_count: int,
    mean_access_count: float = 5.0,
) -> float:
    recency = math.exp(-0.01 * days_since_access)
    effective_importance = importance * decay_factor
    workspace_boost = 1.5 if same_workspace else 1.0
    frequency = _sigmoid(access_count / max(mean_access_count, 1.0))

    return (
        0.35 * vector_score
        + 0.20 * bm25_score
        + 0.15 * recency
        + 0.15 * effective_importance
        + 0.10 * workspace_boost
        + 0.05 * frequency
    )


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
