"""Memory storage, extraction, and retrieval."""
import uuid
from dataclasses import dataclass, field

from core.db import get_pool
from core.provider import BaseProvider, Message

MEMORY_EXTRACTION_PROMPT = """\
Extract factual memories from this conversation turn. Output JSON array only.

Rules:
- Include design decisions, bugs found/fixed, user preferences, project facts
- Skip small talk, greetings, transient debugging state
- Each entry: {"type": "...", "content": "...", "summary": "...",
  "importance": 0.X, "tags": [...]}
- Types: conversation, design_decision, learned_fact, user_preference,
  task_history, code_snippet, bug
- Importance: 0.0-1.0. Design decisions/bugs > 0.6. Preferences > 0.5.
- summary: one short sentence
- Only return JSON array, no other text.

Conversation:
{conversation}

JSON:"""


@dataclass
class MemoryRecord:
    id: str = ""
    content: str = ""
    summary: str = ""
    memory_type: str = "conversation"
    workspace_name: str = ""
    importance: float = 0.5
    access_count: int = 0
    tags: list[str] = field(default_factory=list)


async def store_memory(
    content: str,
    summary: str,
    memory_type: str,
    workspace_name: str,
    importance: float = 0.5,
    tags: list[str] | None = None,
    embedding: list[float] | None = None,
) -> str:
    """Store a memory with its embedding vector. Returns memory id."""
    pool = await get_pool()
    memory_id = str(uuid.uuid4())

    tag_array = "{" + ",".join(f'"{t}"' for t in (tags or [])) + "}"

    if embedding:
        emb_str = "[" + ",".join(str(e) for e in embedding) + "]"
        await pool.execute(
            """
            INSERT INTO memories (id, content, summary, memory_type, workspace_name,
                                  importance, tags, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector)
            """,
            memory_id,
            content,
            summary,
            memory_type,
            workspace_name,
            importance,
            tag_array,
            emb_str,
        )
    else:
        await pool.execute(
            """
            INSERT INTO memories (id, content, summary, memory_type, workspace_name,
                                  importance, tags)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            memory_id, content, summary, memory_type, workspace_name, importance, tag_array,
        )

    return memory_id


async def check_duplicate(content: str, threshold: float = 0.95) -> bool:
    """Check if a similar memory already exists using embedding similarity."""
    embedding = await generate_embedding(content)
    if not embedding:
        return False

    pool = await get_pool()
    emb_str = "[" + ",".join(str(e) for e in embedding) + "]"
    row = await pool.fetchrow(
        """
        SELECT 1 FROM memories
        WHERE 1 - (embedding <=> $1::vector) > $2
        LIMIT 1
        """,
        emb_str,
        threshold,
    )
    return row is not None


async def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding for text via OpenAI API."""
    try:
        from openai import OpenAI

        from core.config import load_config

        config = load_config()
        client = OpenAI(
            api_key=config.embedding.api_key,
            base_url=config.provider.api_base or None,
        )
        response = client.embeddings.create(
            model=config.embedding.model.replace("openai/", ""),
            input=text,
        )
        return response.data[0].embedding
    except Exception:
        return None


async def extract_memories(
    provider: BaseProvider,
    user_message: str,
    assistant_response: str,
    workspace_name: str,
) -> list[MemoryRecord]:
    """Extract memories from a conversation turn using LLM."""
    conversation = f"User: {user_message}\nAssistant: {assistant_response}"
    prompt = MEMORY_EXTRACTION_PROMPT.format(conversation=conversation)

    messages = [Message(role="user", content=prompt)]
    response = provider.chat(messages, tools=None)

    import json

    try:
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    records = []
    for item in data:
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            content=item.get("content", ""),
            summary=item.get("summary", ""),
            memory_type=item.get("type", "conversation"),
            workspace_name=workspace_name,
            importance=float(item.get("importance", 0.5)),
            tags=item.get("tags", []),
        )
        records.append(record)
    return records


async def store_extracted_memories(
    records: list[MemoryRecord],
    skip_duplicates: bool = True,
) -> int:
    """Store extracted memories with embeddings. Returns count stored."""
    count = 0
    for record in records:
        if record.importance < 0.2:
            continue
        if skip_duplicates and await check_duplicate(record.content):
            continue
        embedding = await generate_embedding(record.content)
        await store_memory(
            content=record.content,
            summary=record.summary,
            memory_type=record.memory_type,
            workspace_name=record.workspace_name,
            importance=record.importance,
            tags=record.tags,
            embedding=embedding,
        )
        count += 1
    return count


async def count_memories(workspace: str) -> int:
    """Count memories for a workspace."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT COUNT(*) FROM memories WHERE workspace_name = $1",
        workspace,
    )
    return row[0] if row else 0


async def count_instinct_activations() -> int:
    """Count total instinct activations."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT COUNT(*) FROM instinct_activations")
    return row[0] if row else 0
