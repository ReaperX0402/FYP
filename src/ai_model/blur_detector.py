"""
Blur Detection Utility

Purpose:
--------
This module provides a lightweight blur detection method for the IPDS review flow.

Method:
-------
Variance of Laplacian

Interpretation:
---------------
- Higher variance  -> sharper image
- Lower variance   -> blurrier image

Threshold Use:
--------------
A configurable threshold is used to determine whether an image should be
flagged as potentially blurry.

IMPORTANT:
----------
This is a soft warning only. Operators remain the final authority.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import cv2


class BlurDetector:
    """
    Lightweight blur detector based on Variance of Laplacian.
    """

    def __init__(self, threshold: float = 100.0) -> None:
        """
        Args:
            threshold:
                Blur warning threshold.
                Images with blur score below this value are flagged.
        """
        self.threshold = float(threshold)

    def detect(self, image_path: str | Path) -> Dict[str, Any]:
        """
        Analyze an image and return blur score + warning flag.

        Args:
            image_path:
                Path to image file.

        Returns:
            Dict containing:
            - blur_score: numeric sharpness estimate
            - blur_warning: True if below threshold
        """
        image_path = str(image_path)

        image = cv2.imread(image_path)
        if image is None:
            raise RuntimeError(f"Failed to load image for blur detection: {image_path}")
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        return {
            "blur_score": round(blur_score, 6),
            "blur_warning": blur_score < self.threshold,
        }