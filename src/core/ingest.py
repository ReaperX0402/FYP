from __future__ import annotations

import hashlib
from pathlib import Path

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
    sha = hashlib.sha256(data).hexdigest
    tmp.replace(dest)
    return dest, sha

