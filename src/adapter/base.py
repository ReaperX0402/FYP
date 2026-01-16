from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Protocol, runtime_checkable

@dataclass(frozen= False, slots = True)
class CameraMedia: 
    vendor_id: str
    filename: str
    size_bytes: int
    captured_at: Optional[datetime] = None

@runtime_checkable
class CameraAdapter(Protocol):
    #Ensures that all adapter follow this contract
    @property
    def name(self) -> str: 
        #Unique adapter name
        ...
    def connect(self) -> None:
        #Esthablish connection with the camera. Catch exception if fail to connect
        ...
    def disconnect(self) -> None:
        #Close session / release resources. Must be safe to call repeatedly.
        ...
    def health(self) -> dict:
        """Return a small status dict for UI/Logging. 
           Can include:
           - connected: boolean 
           - adapter: str
           - details: str
        """
        ...
    def list_media(self) -> Iterable[CameraMedia]:
        #Return CameraMedia object that can be passed into download_media
        ...
    def download_media(self, media: CameraMedia) -> bytes:
        #Download the media bytes for the given CameraMedia. Raise exception if downloas fail       
        ...