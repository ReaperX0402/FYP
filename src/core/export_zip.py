from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ImportSession, Jobs, Media, Decisions, Exports, LocalArchives
from src.utils.hashing import sha256_file, sha256_bytes

# Helpers (naming & timestamping)
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _ts_for_filename(dt: datetime|None = None) -> str:
    if dt is None:
         dt = datetime.now(timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y%m%dT%H%M%S")

def _sanitize_token(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in ("-", "_"))

def build_export_photo_name(*, uut_serial: str, operator_id: str, export_ts: str, seq: int, original_name: str,) -> str:
    ext = Path(original_name).suffix.lower()
    safe_uut = _sanitize_token(uut_serial)
    safe_op = _sanitize_token(operator_id)
    return f"UUT_{safe_uut}_OP{safe_op}_{export_ts}_{seq:03d}{ext}"

# Query to retrieve accepted image
def _get_accepted_media(db: Session, import_session_id: int) -> list[tuple[Media, Decisions]]:
    stmt= (select(Media, Decisions).
          join(Decisions, Decisions.media_id == Media.media_id).
          where(Media.import_session_id == import_session_id).
          where(Decisions.status == "accepted").
          order_by(Media.import_session_id == import_session_id)
          )
    return list(db.execute(stmt).all())
    
@dataclass
class ZipExportResult:
    export_id: int
    zip_path: Path
    archive_path: Path
    manifest_hash: str
    file_count: int

def export_session_to_zip(*, db: Session, import_session_id: int, export_root: Path, archive_root: Path,) -> ZipExportResult:
    """
    Export accepted images for a session into a ZIP:
      - ZIP filename: <UUT_SN>_<IMPORT_SESSION_ID>.zip
      - Photos renamed per proposal and stored in ZIP under photos/
      - manifest.json stored at ZIP root, includes per-file sha256 + size
      - DB records: exports + local_archives (mandatory)
    """
    sess = db.get(ImportSession, import_session_id)
    if not sess:
        raise RuntimeError(f"ImportSession not found: {import_session_id}")
    job = db.get(Jobs, sess.job_id)
    if not job:
        raise RuntimeError(f"Job not found for session job_id={sess.job_id}")
    accepted = _get_accepted_media(db, import_session_id)
    if not accepted:
        raise RuntimeError("No accepted media found. Nothing to export.")
    
    uut_serial = sess.uut_serial
    operator_id = sess.operator_id
    job_id = job.job_id
    