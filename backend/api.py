"""FastAPI service behind the claims workspace.

    GET  /api/health
    GET  /api/claims                     list claims with their status
    GET  /api/claims/{id}                the full prepared claim
    GET  /api/claims/{id}/evidence       the files on file for a claim
    GET  /api/claims/{id}/file/{name}    stream one evidence file
    POST /api/claims/{id}/process        run the pipeline for a claim
    POST /api/claims/{id}/decision       a handler records accept / amend / reject

Run it:  uvicorn api:app --reload --port 8000
"""
from __future__ import annotations

import pathlib
import re
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import config as cfg
import pipeline
import store

def _find_repo_dir(name: str) -> pathlib.Path:
    """Locate a top-level folder by walking up: the source tree and the participant
    repository nest this file at different depths."""
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / name
        if candidate.exists():
            return candidate
    return here.parent / name


DATA_DIR = _find_repo_dir("data") / "claims"

app = FastAPI(title="Contoso Claims Workspace", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

_processing: set[str] = set()


class Decision(BaseModel):
    decision: str = Field(min_length=1, max_length=32)
    handler: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=2000)
    verification_confirmations: list[str] = Field(default_factory=list, max_length=100)


def _claim_dir(claim_id: str) -> pathlib.Path:
    # never let a claim id escape the data directory
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", claim_id):
        raise HTTPException(400, "invalid claim id")
    path = DATA_DIR / claim_id
    if not path.is_dir():
        raise HTTPException(404, f"no evidence folder for {claim_id}")
    return path


def _validate_claim_id(claim_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", claim_id):
        raise HTTPException(400, "invalid claim id")


def _schedule_processing(claim_id: str, folder: pathlib.Path, background: BackgroundTasks) -> None:
    if claim_id in _processing:
        return

    def run() -> None:
        _processing.add(claim_id)
        try:
            result = pipeline.process_claim(folder)
            duplicate_of = store.find_duplicate(result)
            if duplicate_of:
                result["duplicate_of"] = duplicate_of
                result["findings"].append({
                    "code": "DUPLICATE_CLAIM",
                    "severity": "critical",
                    "message": f"This claim matches existing claim {duplicate_of} on policy, vehicle and date of loss; handler action is blocked.",
                    "evidence": [
                        {"document": "claim_form", "field": "policy_number",
                         "value": result["extracted"]["claim_form"]["policy_number"]["value"]},
                        {"document": "claim_form", "field": "vin",
                         "value": result["extracted"]["claim_form"]["vin"]["value"]},
                        {"document": "claim_form", "field": "date_of_loss",
                         "value": result["extracted"]["claim_form"]["date_of_loss"]["value"]},
                    ],
                    "duplicate_of": duplicate_of,
                })
                result["rule_recommendation"] = "refer"
                if result.get("review"):
                    result["review"]["recommendation"] = "refer"
            store.save_claim(result)
        finally:
            _processing.discard(claim_id)

    background.add_task(run)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "alias": cfg.ALIAS, "agent": cfg.AGENT_NAME,
            "claim_table": cfg.CLAIM_TABLE}


@app.get("/api/claims")
def list_claims() -> dict[str, Any]:
    if not DATA_DIR.is_dir():
        raise HTTPException(500, f"claim evidence folder not found at {DATA_DIR}")
    stored = {c["claim_id"]: c for c in store.list_claims()}
    claims = []
    for folder in sorted(d for d in DATA_DIR.iterdir() if d.is_dir()):
        claim_id = folder.name
        record = stored.get(claim_id)
        claims.append(record or {
            "claim_id": claim_id, "status": "not_processed",
            "documents_present": [], "finding_count": None,
            "agent_recommendation": None, "summary": None,
        })
    return {"claims": claims, "processing": sorted(_processing)}


@app.get("/api/metrics")
def get_metrics() -> dict[str, Any]:
    return store.metrics()


@app.get("/api/claims/{claim_id}")
def get_claim(claim_id: str) -> dict[str, Any]:
    record = store.get_claim(claim_id)
    if record is None:
        raise HTTPException(404, f"{claim_id} has not been processed yet")
    return record


@app.get("/api/claims/{claim_id}/evidence")
def list_evidence(claim_id: str) -> dict[str, Any]:
    import analyzers
    folder = _claim_dir(claim_id)
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            relative = path.relative_to(folder).as_posix()
            files.append({
                "name": relative,
                "type": analyzers.classify_by_filename(path.name),
                "size_kb": round(path.stat().st_size / 1024),
            })
    return {"claim_id": claim_id, "files": files}


@app.get("/api/claims/{claim_id}/file/{name:path}")
def get_file(claim_id: str, name: str) -> FileResponse:
    folder = _claim_dir(claim_id)
    path = (folder / name).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(path)


@app.post("/api/claims/{claim_id}/process")
def process(claim_id: str, background: BackgroundTasks) -> dict[str, Any]:
    folder = _claim_dir(claim_id)
    if claim_id in _processing:
        return {"claim_id": claim_id, "status": "already_processing"}
    _schedule_processing(claim_id, folder, background)
    return {"claim_id": claim_id, "status": "processing"}


@app.post("/api/claims/submit")
async def submit_claim(
    background: BackgroundTasks,
    claim_id: str = Form(..., min_length=2, max_length=40),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Store uploaded evidence and process the new or existing claim."""
    _validate_claim_id(claim_id)
    if not files or len(files) > cfg.MAX_UPLOAD_FILES:
        raise HTTPException(400, f"upload between 1 and {cfg.MAX_UPLOAD_FILES} files")

    existing_record = store.get_claim(claim_id)
    existing_folder = DATA_DIR / claim_id
    if existing_record is not None and existing_record.get("status") not in {
        store.REQUEST_INFORMATION,
        store.LEGACY_AMENDED,
    }:
        raise HTTPException(
            409,
            f"claim ID {claim_id} already exists with status "
            f"{existing_record.get('status')}; use a new claim ID",
        )
    if existing_record is None and existing_folder.exists():
        raise HTTPException(409, f"claim ID {claim_id} already exists; use a new claim ID")

    folder = DATA_DIR / claim_id
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    try:
        for upload in files:
            original_name = pathlib.Path(upload.filename or "").name
            suffix = pathlib.Path(original_name).suffix.lower()
            if not original_name or suffix not in cfg.ALLOWED_UPLOAD_SUFFIXES:
                raise HTTPException(400, f"unsupported file type for {original_name or 'unnamed file'}")
            destination = folder / original_name
            content = await upload.read(cfg.MAX_UPLOAD_BYTES + 1)
            if len(content) > cfg.MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"{original_name} exceeds the upload size limit")
            destination.write_bytes(content)
            saved.append(original_name)
    except HTTPException:
        for name in saved:
            (folder / name).unlink(missing_ok=True)
        raise
    finally:
        for upload in files:
            await upload.close()

    if claim_id in _processing:
        return {"claim_id": claim_id, "status": "already_processing", "files": saved}
    _schedule_processing(claim_id, folder, background)
    return {"claim_id": claim_id, "status": "processing", "files": saved}


@app.post("/api/claims/{claim_id}/decision")
def decide(claim_id: str, body: Decision) -> dict[str, Any]:
    if body.decision not in store.DECISIONS:
        raise HTTPException(400, f"decision must be one of {store.DECISIONS}")
    try:
        store.record_decision(claim_id, decision=body.decision,
                      handler=body.handler, note=body.note,
                      verification_confirmations=body.verification_confirmations)
    except KeyError:
        raise HTTPException(404, f"{claim_id} has not been prepared") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"claim_id": claim_id, "status": body.decision, "handler": body.handler}


@app.post("/api/claims/{claim_id}/archive")
def archive(claim_id: str) -> dict[str, Any]:
    try:
        store.archive_claim(claim_id)
    except KeyError:
        raise HTTPException(404, f"{claim_id} has not been prepared") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"claim_id": claim_id, "status": store.ARCHIVED}
