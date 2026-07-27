from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class KnowledgeBase:
    """Read-only knowledge library loaded from project JSON/Markdown assets."""

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
            "markdown_notes": [],
            "reference_images": [],
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

        # Markdown notes contain the human-written model definitions that were
        # previously ignored. Keep bounded excerpts so the prompt remains valid.
        for path in sorted(self.root.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not text:
                continue
            bundle["markdown_notes"].append(
                {
                    "path": str(path.relative_to(self.root)),
                    "text": text[:2400],
                }
            )

        # The model cannot visually inspect local SVG files, but their names are
        # an explicit audit catalogue of the reference examples reviewed.
        for path in sorted(self.root.rglob("*.svg")):
            bundle["reference_images"].append(
                {
                    "path": str(path.relative_to(self.root)),
                    "name": path.stem.replace("_", " "),
                }
            )
        return bundle

    def prompt_context(self, max_chars: int = 60000) -> str:
        """Return compact *valid JSON* without ever cutting it mid-document."""
        loaded = self.load()
        prompt_bundle: dict[str, Any] = {
            "rules": loaded["rules"],
            "scenarios": loaded["scenarios"],
            "categories": loaded["categories"],
            "markdown_notes": loaded["markdown_notes"],
            "reference_images": loaded["reference_images"],
        }

        def encode(value: dict[str, Any]) -> str:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

        compact = encode(prompt_bundle)
        if len(compact) <= max_chars:
            return compact

        # Reduce each section in priority order while preserving syntactically
        # valid JSON. This replaces the former raw string truncation.
        reduced: dict[str, Any] = {
            "rules": loaded["rules"][:80],
            "scenarios": loaded["scenarios"][:50],
            "categories": {
                key: value[:8] for key, value in loaded["categories"].items()
            },
            "markdown_notes": [
                {"path": item["path"], "text": item["text"][:700]}
                for item in loaded["markdown_notes"][:18]
            ],
            "reference_images": loaded["reference_images"][:30],
        }
        compact = encode(reduced)
        if len(compact) <= max_chars:
            return compact

        # Final bounded pass: remove tails one item at a time, never slice JSON.
        for key in ("markdown_notes", "scenarios", "rules", "reference_images"):
            values = reduced.get(key)
            while isinstance(values, list) and values and len(compact) > max_chars:
                values.pop()
                compact = encode(reduced)
        if len(compact) > max_chars:
            reduced["categories"] = {
                key: value[:3] for key, value in reduced["categories"].items()
            }
            compact = encode(reduced)
        return compact
