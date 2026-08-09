import json
from pathlib import Path

_LIBRARY = (
    Path(__file__).resolve().parents[1]
    / "knowledge"
    / "saleem_reference_patterns_v1.json"
)

_cache = None


def load_reference_rules():
    global _cache

    if _cache is not None:
        return _cache

    try:
        data = json.loads(_LIBRARY.read_text(encoding="utf-8"))
        refs = data.get("references") or []
    except Exception:
        refs = []

    _cache = refs
    return refs


def reference_rule_by_id(reference_id):
    target = str(reference_id or "").strip().lower()

    for item in load_reference_rules():
        if str(item.get("id") or "").strip().lower() == target:
            return item

    return None


def reference_rule_count():
    return len(load_reference_rules())
