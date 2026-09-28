"""Human verification items for extracted fields that affect claim handling."""
from __future__ import annotations

from typing import Any

import config as cfg


def build_verification_items(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one stable, deduplicated item for each critical low-confidence field."""
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for doc_type, fields in extracted.items():
        critical = cfg.CRITICAL_VERIFICATION_FIELDS.get(doc_type, set())
        for field_name, field in (fields or {}).items():
            confidence = field.get("confidence")
            key = (doc_type, field_name)
            if key in seen or field_name not in critical or confidence is None:
                continue
            if confidence >= cfg.LOW_CONFIDENCE_THRESHOLD:
                continue
            seen.add(key)
            items.append({
                "id": f"{doc_type}.{field_name}",
                "document": doc_type,
                "field": field_name,
                "value": field.get("value"),
                "confidence": confidence,
                "instruction": "Confirm this value against the source document before deciding.",
            })
    return items