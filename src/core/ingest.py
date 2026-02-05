from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.db.models import Media
from src.db.repo_media import insert_media_idempotent
from src.utils.hashing import sha256_file

def save_bytes_atomic(dest: Path, data: bytes, expected_size: int) -> tuple[Path, str]:
    """
    Write to .part first, check size, then rename to final file
    Prevent half download file treated as complete and corrupt file being in the pipeline
    """
    dest.parent.mkdir(parents= True, exist_ok= True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    #Write bytes to disk, then check file size.
    tmp.write_bytes(data)
    actual = tmp.stat().st_size

    #Detect if the file is corrupted or not by comparing the file size
    if actual != expected_size:
        tmp.unlink(missing_ok= True)
        raise IOError(f"Size mismatch: Expected{expected_size}, got {actual}")
        
    #Hashing helps detect silent curruption and allows tracebility
    sha = sha256_file(tmp)
    tmp.replace(dest)
    return dest, sha

def already_imported(db: Session, adapter_name: str, vendor_id: str) -> bool:
    q = select(Media.media_id).where(Media.adapter == adapter_name, Media.vendor_id == vendor_id)
    return db.execute(q).scalar_one_or_none() is not None

@dataclass
class IngestSummary:
    listed: int = 0
    skipped_known: int = 0
    downloaded: int = 0
    inserted: int = 0
    failed: int = 0

def run_ingestion(db: Session, adapter, import_session_id: int, incoming_dir: Path) -> IngestSummary:
    summary = IngestSummary()

    adapter.connect()
    try:
        session_dir = incoming_dir / f"session_{import_session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)

        items = list(adapter.list_media())
        summary.listed = len(items)

        for item in items:
            try:
                # skip download if already imported
                if already_imported(db, adapter.name, item.vendor_id):
                    summary.skipped_known += 1
                    continue

                data = adapter.download_media(item)
                dest, _sha = save_bytes_atomic(session_dir / item.filename, data, item.size_bytes)
                summary.downloaded += 1

                _, inserted = insert_media_idempotent(
                    db,
                    import_session_id=import_session_id,
                    adapter=adapter.name,
                    vendor_id=item.vendor_id,
                    filename=item.filename,
                    size_bytes=item.size_bytes,
                    captured_at=item.captured_at,
                    local_path=str(dest),
                )
                summary.inserted += 1 if inserted else 0

            except Exception:
                db.rollback()
                summary.failed += 1
                # keep going; do not crash whole ingestion

        return summary

    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass