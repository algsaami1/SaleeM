from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_STORE_LOCK = threading.Lock()
_ALLOWED_RESULTS = {"win", "loss", "open", "no_trade"}


@dataclass(frozen=True)
class FeedbackStoreConfig:
    path: Path

    @classmethod
    def from_env(cls) -> "FeedbackStoreConfig":
        path = Path(
            os.getenv(
                "SALEEM_FEEDBACK_STORE_PATH",
                "/tmp/saleem_feedback_store.json",
            ).strip()
        )
        return cls(path=path)


class FeedbackStore:
    def __init__(self, config: FeedbackStoreConfig | None = None) -> None:
        self.config = config or FeedbackStoreConfig.from_env()

    def _empty_payload(self) -> dict[str, Any]:
        return {
            "feedback_submissions": [],
            "note_messages": [],
        }

    def _read(self) -> dict[str, Any]:
        path = self.config.path
        if not path.exists():
            return self._empty_payload()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_payload()
        if not isinstance(payload, dict):
            return self._empty_payload()
        payload.setdefault("feedback_submissions", [])
        payload.setdefault("note_messages", [])
        if not isinstance(payload["feedback_submissions"], list):
            payload["feedback_submissions"] = []
        if not isinstance(payload["note_messages"], list):
            payload["note_messages"] = []
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        path = self.config.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_feedback(
        self,
        *,
        trade_result: str,
        rating: int,
        notes: str | None = None,
    ) -> dict[str, Any]:
        trade_result = str(trade_result or "").strip().lower()
        if trade_result not in _ALLOWED_RESULTS:
            raise ValueError("trade_result must be one of win/loss/open/no_trade")
        rating = int(rating)
        if not 1 <= rating <= 5:
            raise ValueError("rating must be between 1 and 5")

        entry = {
            "id": uuid.uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_result": trade_result,
            "rating": rating,
            "notes": (notes or "").strip(),
        }

        with _STORE_LOCK:
            payload = self._read()
            payload["feedback_submissions"].append(entry)
            self._write(payload)
            return self._build_summary(payload)

    def record_note(self, *, message: str) -> dict[str, Any]:
        cleaned = str(message or "").strip()
        if not cleaned:
            raise ValueError("message is required")
        entry = {
            "id": uuid.uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": cleaned,
        }
        with _STORE_LOCK:
            payload = self._read()
            payload["note_messages"].append(entry)
            self._write(payload)
            return entry

    def summary(self) -> dict[str, Any]:
        with _STORE_LOCK:
            return self._build_summary(self._read())

    def _build_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        feedback_submissions = [
            item for item in payload.get("feedback_submissions", []) if isinstance(item, dict)
        ]
        ratings = [
            int(item["rating"])
            for item in feedback_submissions
            if isinstance(item.get("rating"), int) or str(item.get("rating", "")).isdigit()
        ]
        wins = sum(1 for item in feedback_submissions if item.get("trade_result") == "win")
        losses = sum(1 for item in feedback_submissions if item.get("trade_result") == "loss")
        opens = sum(1 for item in feedback_submissions if item.get("trade_result") == "open")
        no_trade = sum(1 for item in feedback_submissions if item.get("trade_result") == "no_trade")
        closed_trades = wins + losses
        total_trades = wins + losses + opens
        success_rate = round((wins / closed_trades) * 100) if closed_trades else 0
        failure_rate = 100 - success_rate if closed_trades else 0
        average_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

        return {
            "average_rating": average_rating,
            "rating_count": len(ratings),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "open_trades": opens,
            "no_trade": no_trade,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "participant_submissions": len(feedback_submissions),
            "note_count": len(payload.get("note_messages", [])),
        }
