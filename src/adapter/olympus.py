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
        self._connected = None
        self._detail = "Not Connected"

    @property
    def name(self) -> str:
        return self._name
    
    def connect(self) -> None:
        #Create the OlympusCamera instance and validate connection by listing images.
        from olympus import OlympusCamera
        
