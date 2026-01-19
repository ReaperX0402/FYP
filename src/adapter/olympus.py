from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from adapter.base import CameraMedia, CameraAdapter

def parse_dt(s: str) -> Optional[datetime]:
    """
    Parse camera tiemstamp string into datetime
    As different camera has different format of datetime
    If parsing fails, return None instead of crashing the system. 
    """
    if not s :
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try: 
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None    

@dataclass 
class OlympusTG7Adapter(CameraAdapter):
    """
    This adapter utilizes the "olympuswifi" library 
    Key assumption:
      - PC is already connected to the camera's Wi-Fi network.
      - The camera is awake and in Wi-Fi connection/standby mode.
    Goals to achieve:
      - connect() should fail if camera fail to connect or anything goes wrong
      - list_media() proves camera API is reachable.
      - download_media() can actually transfer bytes end-to-end.
    """
    def __post_init__(self) -> None:
        # _cam will hold the underlying OlympusCamera object (from olympuswifi)
        self._cam = None

        #Internal connection state for health reporting 
        self._connected = False
        self._detail = "Not Connected"

    @property
    def name(self) -> str:
        return "olympus_tg7"
    
    def connect(self) -> None:
        #Create the OlympusCamera instance and validate connection by listing images.
        from olympuswifi.camera import OlympusCamera
        #Create a camera session object
        self._cam = OlympusCamera()
        
        #Validate connectivity with an API call 
        try:
            _ = list(self._cam.list_images("/DCIM"))
        except Exception as e:
            self._cam = None
            self._connected = False
            self._detail = f"Connect failed: {e}"

            raise RuntimeError(
                "Cannot talk to the TG-7 over Wi-Fi.\n"
                "Common causes:\n"
                "- PC not connected to TG-7 Wi-Fi SSID\n"
                "- Camera sleeping / not in Wi-Fi mode\n"
                "- IP/subnet mismatch\n"
                f"Underlying error: {e}"
            ) from e

        self._connected = True
        self._detail = "Connected"


    def disconnect(self) -> None :
        #Reset adapter state and drop the underlying camera object.
        self._cam = None
        self._connected = False
        self._detail = "Disconnected"

    def health(self) -> dict:
        #Health or status to be display on main during debugging
        return{
            "adapter": self.name,
            "connected": bool(self._connected and self._cam is not None),
            "detail": self._detail,
        }
    
    def list_media(self) -> Iterable[CameraMedia]:
        """
        Request the camera for a list of iamges and convert them into CameraMedia object
        Filter to JPG/JPEG only for the debugging stage.
        """
        if not self._cam or not self._connected:
            raise RuntimeError("Adapter not connected")
        
        files = self._cam.list_images("/DCIM")

        items: list[CameraMedia] = []
        for f in files:
            path = getattr(f, "file_name", "")
            size = getattr(f, "file_size", "")
            dt = getattr(f, "date_time", "")

            if not path or size is None:
                continue

            if not path.lower().endswith((".jpg", ".jpeg")):
                continue

            items.append(
                CameraMedia(
                    vendor_id= path,
                    filename= path.split("/")[-1],
                    size_bytes= int(size),
                    captured_at= parse_dt(dt)
                )
            )

        return items
    
    def download_media(self, media: CameraMedia) -> bytes:
        #Download bytes for the given media item
        if not self._cam or not self._connected:
            raise RuntimeError("Adapter not connected")
        
        try:
            return self._cam.download_image(media.vendor_id)
        except Exception as e:
            raise RuntimeError(f"Download failed for {media.vendor_id}: {e}") from e
    

        
