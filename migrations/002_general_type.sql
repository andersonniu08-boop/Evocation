-- Migration 002: Add 'general' memory type for non-structural memories
-- Broadens the memory_type enum to support unstructured / fallback memories.

ALTER TABLE memories DROP CONSTRAINT IF EXISTS memories_memory_type_check;
ALTER TABLE memories ADD CONSTRAINT memories_memory_type_check CHECK (memory_type IN (
    'general',
    'conversation', 'design_decision', 'learned_fact',
    'user_preference', 'task_history', 'code_snippet', 'bug',
    'goal_definition', 'plan_architecture', 'task_result', 'past_failure'
));
