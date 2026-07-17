from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeBase:
    """Read-only knowledge library loaded from JSON files inside the project."""

    LIST_KEYS = (
        "rules", "scenarios", "items", "drawing_rules", "weights", "categories"
    )

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self) -> dict[str, Any]:
        bundle: dict[str, Any] = {
            "rules": [],
            "scenarios": [],
            "categories": {},
            "documents": [],
            "metadata": {},
        }
        if not self.root.exists():
            return bundle

        for path in sorted(self.root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue

            relative = str(path.relative_to(self.root))
            category = str(payload.get("category") or path.parent.name)
            bundle["metadata"][relative] = {
                key: value
                for key, value in payload.items()
                if key not in self.LIST_KEYS
            }

            if isinstance(payload.get("rules"), list):
                bundle["rules"].extend(payload["rules"])
            if isinstance(payload.get("scenarios"), list):
                bundle["scenarios"].extend(payload["scenarios"])

            category_items: list[Any] = []
            for key in ("items", "drawing_rules", "weights"):
                if isinstance(payload.get(key), list):
                    category_items.extend(payload[key])
            if category_items:
                bundle["categories"].setdefault(category, []).extend(category_items)

            bundle["documents"].append({
                "path": relative,
                "category": category,
                "payload": payload,
            })
        return bundle

    def prompt_context(self, max_chars: int = 60000) -> str:
        loaded = self.load()
        prompt_bundle = {
            "rules": loaded["rules"],
            "scenarios": loaded["scenarios"],
            "categories": loaded["categories"],
        }
        compact = json.dumps(
            prompt_bundle, ensure_ascii=False, separators=(",", ":")
        )
        if len(compact) <= max_chars:
            return compact
        # Drop lower-priority category tails before truncating raw JSON.
        reduced = dict(prompt_bundle)
        reduced["categories"] = {
            key: value[:8] for key, value in loaded["categories"].items()
        }
        compact = json.dumps(reduced, ensure_ascii=False, separators=(",", ":"))
        return compact[:max_chars]
