"""Document scanner — photo to clean, perspective-corrected PNG.

Pipeline:
    1. Edge detection (Canny) + contour finding
    2. 4-point perspective transform to flatten the document
    3. Adaptive contrast/brightness normalization
    4. Output as lossless PNG
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ScanResult:
    """Result of a document scan."""

    __slots__ = ("image", "corners", "width", "height")

    def __init__(self, image: np.ndarray, corners: np.ndarray | None = None) -> None:
        self.image = image
        self.corners = corners
        self.height, self.width = image.shape[:2]


class DocumentScanner:
    """Scans a photo of a document into a clean, flat PNG."""

    def __init__(
        self,
        max_dimension: int = 2000,
        blur_kernel: int = 5,
        canny_threshold1: int = 50,
        canny_threshold2: int = 150,
        target_dpi: int = 300,
    ) -> None:
        self._max_dim = max_dimension
        self._blur_kernel = blur_kernel
        self._canny_t1 = canny_threshold1
        self._canny_t2 = canny_threshold2
        self._target_dpi = target_dpi

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, image: np.ndarray) -> ScanResult | None:
        """Full scan pipeline: detect → warp → enhance.

        Returns ScanResult on success, None if no document detected.
        """
        working = self._resize_for_processing(image)

        corners = self._detect_document_corners(working)
        if corners is None:
            logger.warning("No document contour detected — using fallback crop")
            corners = self._fallback_corners(working)

        # Scale corners back to original image dimensions
        scale_x = image.shape[1] / working.shape[1]
        scale_y = image.shape[0] / working.shape[0]
        corners_original = (corners * np.array([[scale_x, scale_y]], dtype=np.float32)).astype(np.float32)

        warped = self._perspective_transform(image, corners_original)
        enhanced = self._enhance(warped)

        return ScanResult(enhanced, corners_original)

    def scan_file(self, path: str) -> ScanResult | None:
        """Load an image file and scan it."""
        image = cv2.imread(path)
        if image is None:
            logger.error("Cannot read image: %s", path)
            return None
        return self.scan(image)

    def save(self, result: ScanResult, path: str) -> bool:
        """Save scan result as PNG."""
        try:
            cv2.imwrite(path, result.image, [cv2.IMWRITE_PNG_COMPRESSION, 6])
            return True
        except Exception as exc:
            logger.error("Failed to save scan: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Step 1: Resize for processing
    # ------------------------------------------------------------------

    def _resize_for_processing(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        if max(h, w) <= self._max_dim:
            return image.copy()
        scale = self._max_dim / max(h, w)
        return cv2.resize(image, (int(w * scale), int(h * scale)))

    # ------------------------------------------------------------------
    # Step 2: Detect document corners
    # ------------------------------------------------------------------

    def _detect_document_corners(self, image: np.ndarray) -> np.ndarray | None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (self._blur_kernel, self._blur_kernel), 0)
        edges = cv2.Canny(blurred, self._canny_t1, self._canny_t2)

        # Dilate edges to close gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # Sort by area, largest first
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours[:5]:
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

            if len(approx) == 4 and cv2.contourArea(approx) > 1000:
                return self._order_corners(approx.reshape(4, 2).astype(np.float32))

        return None

    def _fallback_corners(self, image: np.ndarray) -> np.ndarray:
        """Use full image as document when no contour detected."""
        h, w = image.shape[:2]
        margin = 5
        return np.array([
            [margin, margin],
            [w - margin, margin],
            [w - margin, h - margin],
            [margin, h - margin],
        ], dtype=np.float32)

    @staticmethod
    def _order_corners(corners: np.ndarray) -> np.ndarray:
        """Order corners: top-left, top-right, bottom-right, bottom-left."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = corners.sum(axis=1)
        diff = np.diff(corners, axis=1).flatten()

        rect[0] = corners[np.argmin(s)]      # top-left: smallest sum
        rect[2] = corners[np.argmax(s)]      # bottom-right: largest sum
        rect[1] = corners[np.argmin(diff)]   # top-right: smallest diff
        rect[3] = corners[np.argmax(diff)]   # bottom-left: largest diff
        return rect

    # ------------------------------------------------------------------
    # Step 3: Perspective transform
    # ------------------------------------------------------------------

    def _perspective_transform(self, image: np.ndarray, corners: np.ndarray) -> np.ndarray:
        """Warp the image to a flat, top-down view."""
        # Compute target dimensions
        (tl, tr, br, bl) = corners

        width_top = np.linalg.norm(tr - tl)
        width_bottom = np.linalg.norm(br - bl)
        max_width = int(max(width_top, width_bottom))

        height_left = np.linalg.norm(bl - tl)
        height_right = np.linalg.norm(br - tr)
        max_height = int(max(height_left, height_right))

        # Ensure minimum size
        max_width = max(max_width, 100)
        max_height = max(max_height, 100)

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ], dtype=np.float32)

        matrix = cv2.getPerspectiveTransform(corners, dst)
        warped = cv2.warpPerspective(image, matrix, (max_width, max_height))
        return warped

    # ------------------------------------------------------------------
    # Step 4: Enhancement
    # ------------------------------------------------------------------

    def _enhance(self, image: np.ndarray) -> np.ndarray:
        """Adaptive contrast/brightness normalization."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_gray = clahe.apply(gray)

        # Adaptive threshold for clean text
        binary = cv2.adaptiveThreshold(
            enhanced_gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=15,
            C=10,
        )

        # Convert back to BGR (white background, black text)
        result = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return result
