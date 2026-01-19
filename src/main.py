from __future__ import annotations

from pathlib import Path

from adapter.olympus import OlympusTG7Adapter
from core.ingest import save_bytes_atomic

def main() -> None:
    """
    What this proves:
      1) connect() works -> camera reachable + API works
      2) list_media() works -> camera can list files
      3) download_media() works -> can transfer actual bytes
      4) ingestion works -> saved file is complete (size verified)
    """

    #Create a folder to store donwloaded file
    incoming_dir = Path("data/incoming")
    incoming_dir.mkdir(parents= True, exist_ok=True)

    #Create adapter
    ad = OlympusTG7Adapter()

    #1) Connect 
    ad.connect()
    print("HEALTH: ", ad.health())

    #2) List Images 
    media = list(ad.list_media())
    print("JPG COUNT: ", len(media))
    if not media:
        print("No JPG found. Take a photo first or ensure camera has images.")
        return
    
    # 3) Pick the newest image
    # Sort by captured_at when available; items with timestamps sort higher.
    media.sort(key=lambda m: (m.captured_at is not None, m.captured_at))
    newest = media[-1]

    print(f"DOWNLOADING: {newest.vendor_id} ({newest.size_bytes} bytes)") 

    # 4) Download bytes
    data = ad.download_media(newest)

    # 5) Save safely 
    dest = incoming_dir / newest.filename
    final_path = save_bytes_atomic(dest, data, expected_size=newest.size_bytes)

    print("SAVED:", final_path)

if __name__ == "__main__":
    main()

