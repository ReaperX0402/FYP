from __future__ import annotations

from typing import Dict, Set, List

REQUIRED_ANGLES = {"front", "back", "left", "right", "top"}


def suggest_next_angles(object_name: str, captured: Dict[str, Set[str]]) -> List[str]:
    done = captured.get(object_name, set())
    return sorted(REQUIRED_ANGLES - done)