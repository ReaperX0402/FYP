from __future__ import annotations
import re
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import ImportSession, Jobs, Media, Decisions, Exports, LocalArchives
from src.utils.hashing import sha256_file, sha256_bytes
from src.utils.embed import embed_ipds_metadata
from src.utils.watermark import burn_watermark

_VERSION_RE = re.compile(r"^(?P<stem>.+?)(?:_v(?P<v>\d+))?$")
MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")

def _utc_now_iso() -> str:
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
    return f"{safe_uut}_{safe_op}_{export_ts}_{seq:03d}{ext}"

# Query to retrieve accepted image
def _get_accepted_media(db: Session, import_session_id: int) -> list[tuple[Media, Decisions]]:
    stmt = (
        select(Media, Decisions)
        .join(Decisions, Decisions.media_id == Media.media_id)
        .where(Media.import_session_id == import_session_id)
        .where(Decisions.status == "accepted")
        .order_by(
            Media.captured_at.asc().nulls_last(),
            Media.media_id.asc(),
        )
    )
    return list(db.execute(stmt).all())

def _get_all_media(db: Session, import_session_id: int) -> list[tuple[Media, Decisions]]:
    stmt = (
        select(Media, Decisions)
        .join(Decisions, Decisions.media_id == Media.media_id)
        .where(Media.import_session_id == import_session_id)
        .order_by(
            Media.captured_at.asc().nulls_last(),
            Media.media_id.asc(),
        )
    )
    return list(db.execute(stmt).all())

def _next_versioned_path(export_root: Path, base_name: str) -> tuple[str, Path]:
    """
    base_name like: ABC123_7.zip
    returns (zip_name, zip_path) possibly versioned: ABC123_7_v2.zip
    """
    base_path = export_root / base_name
    if not base_path.exists():
        return base_name, base_path

    stem = Path(base_name).stem         # ABC123_7
    ext  = Path(base_name).suffix       # .zip

    # find max version among: stem.zip, stem_v2.zip, stem_v3.zip...
    max_v = 1
    for p in export_root.glob(f"{stem}*{ext}"):
        m = _VERSION_RE.match(p.stem)
        if not m:
            continue
        if m.group("stem") != stem:
            continue
        v = m.group("v")
        if v:
            max_v = max(max_v, int(v))
    next_v = max_v + 1
    zip_name = f"{stem}_v{next_v}{ext}"
    return zip_name, export_root / zip_name

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
    
    #Prepare PATH
    export_root.mkdir(parents=True, exist_ok=True)
    archive_root.mkdir(parents=True, exist_ok=True)

    base_zip_name = f"{uut_serial}_{import_session_id}.zip" 
    zip_name, zip_path = _next_versioned_path(export_root, base_zip_name)
    
    staging_dir = export_root / f".staging_{uut_serial}_{import_session_id}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    export_ts = _ts_for_filename()  # one timestamp for the whole export batch

    files_manifest: list[dict[str, Any]] = []

    seq = 1
    for media, decision in accepted:
        src = Path(media.local_path)
        if not src.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise RuntimeError(f"Missing source file on disk: {src}")
        
        export_name = build_export_photo_name(
            uut_serial=uut_serial,
            operator_id=operator_id,
            export_ts=export_ts,
            seq=seq,
            original_name=(media.filename or src.name),
        )

        dst = staging_dir / export_name
        shutil.copy2(src, dst)

        embed_ipds_metadata(
            str(dst),
            uut_serial=uut_serial,
            import_session_id=import_session_id,
            captured_at=media.captured_at,
        )

        dt = datetime.now(timezone.utc)

        # If DB gave you a naive datetime, assume it is UTC (or fix ingestion properly below)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        dt_text = dt.astimezone(MY_TZ).strftime("%Y-%m-%d %H:%M:%S")

        burn_watermark(
            str(dst),
            uut_serial=uut_serial,
            dt_text=dt_text
        )

        size = dst.stat().st_size
        sha = sha256_file(dst)

        files_manifest.append(
            {
                "seq": seq,
                "export_name": export_name,
                "source_vendor_id": media.vendor_id,
                "source_local_path": str(src),
                "size_bytes": size,
                "sha256": sha,
                "captured_at": media.captured_at.isoformat() if media.captured_at else None,
                "decision": {
                    "status": decision.status,
                    "reason": decision.reason,
                    "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
                    "notes": decision.notes
                },
            }
        )
        seq += 1

    # Building of manifest.json 
    manifest = {
        "schema": "ipds_manifest_v1",
        "exported_at": _utc_now_iso(),
        "job_id": job_id,
        "import_session_id": import_session_id,
        "uut_serial": uut_serial,
        "operator_id": operator_id,
        "file_count": len(files_manifest),
        "files": files_manifest
    }

    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    manifest_hash = sha256_bytes(manifest_bytes)

    sidecar_manifest_path = export_root / f"{zip_name}.manifest.json"
    sidecar_manifest_path.write_bytes(manifest_bytes)

    # Create ZIP with deterministic internal layout
    # ZIP layout:
    #   manifest.json
    #   photos/<renamed files>

    tmp_zip = zip_path.with_suffix(zip_path.suffix + ".part")
    if tmp_zip.exists():
        tmp_zip.unlink()

    with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", manifest_bytes)
        for f in sorted(staging_dir.iterdir()):
            z.write(f, arcname=f"photos/{f.name}")

    tmp_zip.replace(zip_path) 

    export_row = Exports(
    import_session_id=import_session_id,
    export_path=str(zip_path),
    manifest_path=str(sidecar_manifest_path),
    manifest_hash=manifest_hash,
    status="created",
)

    db.add(export_row)
    db.flush()
    db.refresh(export_row)

    archive_dir = archive_root / f"{uut_serial}_{import_session_id}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    all_media = _get_all_media(db, import_session_id)
    archived_count = 0

    for media, _decision in all_media:
        src = Path(media.local_path)
        if not src.exists():
            continue

        dst = archive_dir / src.name

        if not dst.exists():
            shutil.copy2(src, dst)
            archived_count += 1

    # Save the same manifest used in export
    archive_manifest = archive_dir / "manifest.json"
    archive_manifest.write_bytes(manifest_bytes)

    ok = archive_manifest.exists() and archive_dir.exists()

    archive_row = LocalArchives(
    export_id=export_row.export_id,
    archive_path=str(archive_dir),
    verify_status="verified" if ok else "failed",
    last_error=None if ok else "Archive creation failed",
    )

    db.add(archive_row)

    export_row.status = "archived" if ok else "failed"
    db.commit()

    shutil.rmtree(staging_dir, ignore_errors=True)

    return ZipExportResult(
        export_id=export_row.export_id,
        zip_path=zip_path,
        archive_path=archive_dir,
        manifest_hash=manifest_hash,
        file_count=len(files_manifest),
    )

