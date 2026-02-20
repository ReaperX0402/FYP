from pathlib import Path

from src.adapter.olympus import OlympusTG7Adapter
from src.db.session import SessionLocal
from src.db.models import ImportSession
from src.db.repo_media import insert_media_idempotent
from src.core.ingest import save_bytes_atomic, already_imported


def run_ingestion_for_session(import_session_id: int) -> dict:
    imported = 0
    skipped = 0
    failed = 0

    with SessionLocal() as db:
        session = db.get(ImportSession, import_session_id)
        if not session:
            raise RuntimeError("ImportSession not found")

        incoming_dir = Path("data/incoming") / f"session_{import_session_id}"
        incoming_dir.mkdir(parents=True, exist_ok=True)

        adapter = OlympusTG7Adapter()
        adapter.connect()

        try:
            media_items = list(adapter.list_media())

            for item in media_items:
                try:
                    # Skip known duplicates BEFORE download
                    if already_imported(db, adapter.name, item.vendor_id):
                        skipped += 1
                        continue

                    # Download
                    data = adapter.download_media(item)

                    # Save safely
                    dest, _ = save_bytes_atomic(
                        incoming_dir / item.filename,
                        data,
                        expected_size=item.size_bytes,
                    )

                    # Insert into DB (idempotent)
                    insert_media_idempotent(
                        db,
                        import_session_id=import_session_id,
                        adapter=adapter.name,
                        vendor_id=item.vendor_id,
                        filename=item.filename,
                        size_bytes=item.size_bytes,
                        captured_at=item.captured_at,
                        local_path=str(dest),
                    )

                    imported += 1

                except Exception:
                    db.rollback()
                    failed += 1
                    continue

            db.commit()

        finally:
            try:
                adapter.disconnect()
            except Exception:
                pass

    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
    }
