"""Claim records and the handler review queue, backed by Azure Table Storage.

The workspace never decides a claim. It stores the prepared view and the recommendation, and
a named handler records accept / amend / reject against it (CIP-CLM-200 section 5.5).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.data.tables import TableClient
from azure.identity import AzureCliCredential

import config as cfg

ENDPOINT = f"https://{cfg.STORAGE_ACCOUNT}.table.core.windows.net"

PREPARED = "prepared"          # waiting for a handler
AWAITING_VERIFICATION = "awaiting_verification"
ACCEPTED = "accepted"
REQUEST_INFORMATION = "request_information"
REJECTED = "rejected"
ARCHIVED = "archived"
DUPLICATE = "duplicate"
DUPLICATE_PENDING = "duplicate_pending"
LEGACY_AMENDED = "amended"
DECISIONS = (ACCEPTED, REQUEST_INFORMATION, REJECTED, DUPLICATE)
ALL_DECISION_PARTITIONS = (*DECISIONS, LEGACY_AMENDED, ARCHIVED, DUPLICATE, DUPLICATE_PENDING)

# Table Storage entities cap each property at 64 KB, so large blocks are chunked.
_CHUNK = 30_000


def _client(table_name: str) -> TableClient:
    client = TableClient(endpoint=ENDPOINT, table_name=table_name, credential=AzureCliCredential())
    try:
        client.create_table()
    except ResourceExistsError:
        pass
    return client


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _pack(entity: dict[str, Any], key: str, value: Any) -> None:
    text = json.dumps(value, default=str)
    for index in range(0, max(len(text), 1), _CHUNK):
        entity[f"{key}_{index // _CHUNK}"] = text[index:index + _CHUNK]


def _unpack(entity: dict[str, Any], key: str) -> Any:
    parts = [entity[k] for k in sorted((k for k in entity if k.startswith(f"{key}_")),
                                       key=lambda k: int(k.rsplit("_", 1)[1]))]
    if not parts:
        return None
    try:
        return json.loads("".join(parts))
    except json.JSONDecodeError:
        return None


def _extracted_value(extracted: dict[str, Any], document: str, field: str) -> str:
    value = ((extracted.get(document) or {}).get(field) or {}).get("value")
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def duplicate_identity(extracted: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return the minimum strong identity used to detect a repeated claim."""
    identity = (
        _extracted_value(extracted, "claim_form", "policy_number"),
        _extracted_value(extracted, "claim_form", "vin"),
        _extracted_value(extracted, "claim_form", "date_of_loss"),
    )
    return identity if all(identity) else None


def find_duplicate(result: dict[str, Any]) -> str | None:
    """Find an existing different claim with the same strong identity."""
    identity = duplicate_identity(result.get("extracted", {}))
    if identity is None:
        return None
    with _client(cfg.CLAIM_TABLE) as table:
        for entity in table.list_entities():
            if entity.get("RowKey") == result.get("claim_id"):
                continue
            if duplicate_identity(_unpack(entity, "extracted") or {}) == identity:
                return entity["RowKey"]
    return None


def save_claim(result: dict[str, Any]) -> str:
    """Store a prepared claim, replacing any previous preparation of the same claim."""
    claim_id = result["claim_id"]
    review = result.get("review") or {}
    entity: dict[str, Any] = {
        "PartitionKey": DUPLICATE_PENDING if result.get("duplicate_of") else PREPARED,
        "RowKey": claim_id,
        "status": (DUPLICATE_PENDING if result.get("duplicate_of") else
                AWAITING_VERIFICATION if result.get("verification_items") else PREPARED),
        "prepared_at": _now(),
        "processed_at": _now(),
        "documents_present": ",".join(result.get("documents_present", [])),
        "finding_count": len(result.get("findings", [])),
        "critical_count": sum(1 for f in result.get("findings", []) if f["severity"] == "critical"),
        "rule_recommendation": result.get("rule_recommendation", ""),
        "agent_recommendation": review.get("recommendation", ""),
        "summary": (review.get("summary") or "")[:_CHUNK],
        "handler": "",
        "handler_note": "",
        "decided_at": "",
        "elapsed_seconds": result.get("elapsed_seconds"),
        "verification_status": result.get("verification_status", "ready"),
        "duplicate_of": result.get("duplicate_of", ""),
    }
    _pack(entity, "findings", result.get("findings", []))
    _pack(entity, "extracted", result.get("extracted", {}))
    _pack(entity, "photos", result.get("photo_assessments", []))
    _pack(entity, "review", review)
    _pack(entity, "verification_items", result.get("verification_items", []))

    with _client(cfg.CLAIM_TABLE) as table:
        for partition in (PREPARED, AWAITING_VERIFICATION, *ALL_DECISION_PARTITIONS):
            try:
                table.delete_entity(partition, claim_id)
            except ResourceNotFoundError:
                pass
        table.create_entity(entity)
    return claim_id


def list_claims(status: str | None = None) -> list[dict[str, Any]]:
    with _client(cfg.CLAIM_TABLE) as table:
        query = f"PartitionKey eq '{status}'" if status else None
        entities = list(table.query_entities(query) if query else table.list_entities())
    claims = []
    for entity in entities:
        claims.append({
            "claim_id": entity["RowKey"],
            "status": entity.get("status"),
            "prepared_at": entity.get("prepared_at"),
            "documents_present": (entity.get("documents_present") or "").split(","),
            "finding_count": entity.get("finding_count"),
            "critical_count": entity.get("critical_count"),
            "rule_recommendation": entity.get("rule_recommendation"),
            "agent_recommendation": entity.get("agent_recommendation"),
            "summary": entity.get("summary"),
            "handler": entity.get("handler"),
            "handler_note": entity.get("handler_note"),
            "decided_at": entity.get("decided_at"),
            "verification_status": entity.get("verification_status", "ready"),
            "elapsed_seconds": entity.get("elapsed_seconds"),
            "processed_at": entity.get("processed_at", entity.get("prepared_at")),
            "duplicate_of": entity.get("duplicate_of", ""),
        })
    return sorted(claims, key=lambda c: c["claim_id"])


def get_claim(claim_id: str) -> dict[str, Any] | None:
    with _client(cfg.CLAIM_TABLE) as table:
        for entity in table.query_entities(f"RowKey eq '{claim_id}'"):
            return {
                "claim_id": entity["RowKey"],
                "status": entity.get("status"),
                "prepared_at": entity.get("prepared_at"),
                "documents_present": (entity.get("documents_present") or "").split(","),
                "rule_recommendation": entity.get("rule_recommendation"),
                "agent_recommendation": entity.get("agent_recommendation"),
                "findings": _unpack(entity, "findings") or [],
                "extracted": _unpack(entity, "extracted") or {},
                "photo_assessments": _unpack(entity, "photos") or [],
                "review": _unpack(entity, "review") or {},
                "verification_items": _unpack(entity, "verification_items") or [],
                "verification_confirmations": _unpack(entity, "verification_confirmations") or [],
                "handler": entity.get("handler"),
                "handler_note": entity.get("handler_note"),
                "decided_at": entity.get("decided_at"),
                "duplicate_of": entity.get("duplicate_of", ""),
                "decision_history": _unpack(entity, "decision_history") or [],
                "duplicate_of": entity.get("duplicate_of", ""),
                "processed_at": entity.get("processed_at", entity.get("prepared_at")),
            }
    return None


def record_decision(claim_id: str, *, decision: str, handler: str, note: str = "",
                    verification_confirmations: list[str] | None = None) -> None:
    """A named handler accepts, amends or rejects the prepared claim."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    if not handler.strip():
        raise ValueError("a handler name is required - decisions are never anonymous")

    with _client(cfg.CLAIM_TABLE) as table:
        entity = next(iter(table.query_entities(f"RowKey eq '{claim_id}'")), None)
        if entity is None:
            raise KeyError(claim_id)
        required = _unpack(entity, "verification_items") or []
        confirmed = sorted(set(verification_confirmations or []))
        required_ids = sorted(item.get("id") for item in required)
        if required_ids and confirmed != required_ids:
            raise ValueError("confirm every verification item before recording a decision")
        old_partition = entity["PartitionKey"]
        history = _unpack(entity, "decision_history") or []
        history.append({"decision": decision, "handler": handler.strip(), "note": note,
                "recorded_at": _now()})
        entity.update({
            "PartitionKey": decision,
            "status": decision,
            "handler": handler.strip(),
            "handler_note": note,
            "decided_at": _now(),
        })
        _pack(entity, "verification_confirmations", confirmed)
        _pack(entity, "decision_history", history)
        table.create_entity(entity)
        table.delete_entity(old_partition, claim_id)


def archive_claim(claim_id: str) -> None:
    """Move a completed handler decision to the archive without deleting its record."""
    with _client(cfg.CLAIM_TABLE) as table:
        entity = next(iter(table.query_entities(f"RowKey eq '{claim_id}'")), None)
        if entity is None:
            raise KeyError(claim_id)
        if entity["PartitionKey"] not in (
            ACCEPTED, REQUEST_INFORMATION, REJECTED, DUPLICATE, LEGACY_AMENDED,
        ):
            raise ValueError("only completed decisions can be archived")
        old_partition = entity["PartitionKey"]
        entity.update({"PartitionKey": ARCHIVED, "status": ARCHIVED, "archived_at": _now()})
        table.create_entity(entity)
        table.delete_entity(old_partition, claim_id)


def counts() -> dict[str, int]:
    result = {}
    with _client(cfg.CLAIM_TABLE) as table:
        for status in (PREPARED, AWAITING_VERIFICATION, *ALL_DECISION_PARTITIONS):
            result[status] = sum(1 for _ in table.query_entities(
                f"PartitionKey eq '{status}'", select=["RowKey"]))
    return result


def metrics() -> dict[str, Any]:
    """Aggregate persisted claims and retain the claim ids behind every metric."""
    with _client(cfg.CLAIM_TABLE) as table:
        entities = list(table.list_entities())

    claims: list[dict[str, Any]] = []
    for entity in entities:
        findings = _unpack(entity, "findings") or []
        extracted = _unpack(entity, "extracted") or {}
        review = _unpack(entity, "review") or {}
        claim_id = entity["RowKey"]
        claims.append({
            "claim_id": claim_id,
            "status": entity.get("status"),
            "recommendation": entity.get("agent_recommendation") or entity.get("rule_recommendation"),
            "finding_codes": sorted({f.get("code") for f in findings if f.get("code")}),
            "findings": findings,
            "extracted": extracted,
            "elapsed_seconds": entity.get("elapsed_seconds"),
            "review": review,
        })

    def grouped(key: str) -> dict[str, dict[str, Any]]:
        values: dict[str, list[str]] = {}
        for claim in claims:
            value = claim.get(key)
            if value:
                values.setdefault(str(value), []).append(claim["claim_id"])
        return {value: {"count": len(ids), "claim_ids": sorted(ids)}
                for value, ids in sorted(values.items())}

    finding_codes: dict[str, list[str]] = {}
    missing_documents: dict[str, list[str]] = {}
    estimates: list[dict[str, Any]] = []
    elapsed: list[Decimal] = []
    for claim in claims:
        for code in claim["finding_codes"]:
            finding_codes.setdefault(code, []).append(claim["claim_id"])
        for finding in claim["findings"]:
            if finding.get("code") == "MISSING_DOCUMENT" and finding.get("document"):
                missing_documents.setdefault(finding["document"], []).append(claim["claim_id"])
        raw_total = ((claim["extracted"].get("repair_estimate") or {}).get("total_amount") or {}).get("value")
        try:
            if raw_total is not None:
                estimates.append({"claim_id": claim["claim_id"],
                                  "amount": float(Decimal(str(raw_total).replace("$", "").replace(",", "")))})
        except (InvalidOperation, ValueError):
            pass
        try:
            if claim["elapsed_seconds"] is not None:
                elapsed.append(Decimal(str(claim["elapsed_seconds"])))
        except (InvalidOperation, ValueError):
            pass

    def trace(values: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
        return {key: {"count": len(set(ids)), "claim_ids": sorted(set(ids))}
                for key, ids in sorted(values.items())}

    cleared = [c["claim_id"] for c in claims if not any(
        f.get("severity") in {"critical", "warning"} for f in c["findings"])]
    return {
        "processed_claims": len(claims),
        "claim_ids": sorted(c["claim_id"] for c in claims),
        "recommendation_mix": grouped("recommendation"),
        "finding_codes": trace(finding_codes),
        "missing_documents": trace(missing_documents),
        "estimate_values": estimates,
        "average_prepare_seconds": float(sum(elapsed) / len(elapsed)) if elapsed else None,
        "waiting_on_policyholder": {"count": len(grouped("recommendation").get("request_information", {}).get("claim_ids", [])),
                                     "claim_ids": grouped("recommendation").get("request_information", {}).get("claim_ids", [])},
        "needs_senior_adjuster": {"count": len(grouped("recommendation").get("refer", {}).get("claim_ids", [])),
                                   "claim_ids": grouped("recommendation").get("refer", {}).get("claim_ids", [])},
        "cleared_without_finding": {"count": len(cleared), "claim_ids": sorted(cleared)},
    }
