from pathlib import Path
from app.services.knowledge import KnowledgeBase


def memory_context(root: Path) -> str:
    return KnowledgeBase(root).prompt_context(max_chars=60000)
