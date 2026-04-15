from PIL import Image
from datetime import datetime
from pathlib import Path

def embed_ipds_metadata(file_path: str,* , uut_serial: str, import_session_id: int | None = None, captured_at: datetime | None = None,) -> None:
    try:
        path = Path(file_path)
        img = Image.open(path)

        captured_str = (
            captured_at.isoformat()
            if captured_at
            else "unknown"
        )

        session_part = f" | Session={import_session_id}" if import_session_id else ""

        metadata_text = (
            f"IPDS | SN={uut_serial}{session_part} | Captured={captured_str}"
        )

        # Pillow EXIF embedding (JPEG mainly)
        exif = img.getexif()
        exif[0x9286] = metadata_text  # UserComment
        exif[0x010E] = metadata_text  # ImageDescription

        img.save(path, exif=exif)

    except Exception:
        # Metadata should never break export
        pass