from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeBase:
    """Read-only knowledge base loaded from JSON files inside the project."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self) -> dict[str, Any]:
        bundle: dict[str, Any] = {"rules": [], "scenarios": [], "metadata": {}}
        if not self.root.exists():
            return bundle

        for path in sorted(self.root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            relative = str(path.relative_to(self.root))
            if isinstance(payload, dict):
                if isinstance(payload.get("rules"), list):
                    bundle["rules"].extend(payload["rules"])
                if isinstance(payload.get("scenarios"), list):
                    bundle["scenarios"].extend(payload["scenarios"])
                bundle["metadata"][relative] = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"rules", "scenarios"}
                }
        return bundle

    def prompt_context(self, max_chars: int = 12000) -> str:
        compact = json.dumps(self.load(), ensure_ascii=False, separators=(",", ":"))
        return compact[:max_chars]
