from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ultralytics import YOLO


class AngleClassifier:
    def __init__(self, model_path: str | Path) -> None:
        self.model_path = str(model_path)
        self.model = YOLO(self.model_path)

    @staticmethod
    def _parse_class_name(class_name: str) -> tuple[str, str]:
        obj, angle = class_name.rsplit("_", 1)
        return obj, angle

    def predict(self, image_path: str | Path) -> Dict[str, Any]:
        results = self.model.predict(source=str(image_path), imgsz=224, verbose=False)

        if not results:
            raise RuntimeError("No prediction results returned.")

        r = results[0]
        if r.probs is None:
            raise RuntimeError("No classification probabilities returned.")

        top1_idx = r.probs.top1
        confidence = float(r.probs.top1conf)
        class_name = self.model.names[top1_idx]
        obj, angle = self._parse_class_name(class_name)

        return {
            "class_name": class_name,
            "object": obj,
            "angle": angle,
            "confidence": confidence,
        }