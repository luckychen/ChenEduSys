"""Question segmenter — split a scanned document into individual questions.

Pipeline:
    1. Preprocess: binarize and find text regions
    2. Detect horizontal gaps between content blocks
    3. (Optional) Use pytesseract to detect numbering patterns
    4. Merge gaps and numbering to identify question boundaries
    5. Return list of question regions as cropped images
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Numbering patterns that indicate a new question
_NUMBERING_RE = re.compile(
    r"^\s*("
    r"\d+[\.\)]\s"          # "1. " or "1) "
    r"|\d+\.\d+[\.\)]\s"   # "1.1. " or "1.1) "
    r"|\([a-z]\)\s"         # "(a) "
    r"|[A-Z]\.\s"           # "A. "
    r"|Question\s+\d"       # "Question 1"
    r"|Problem\s+\d"        # "Problem 1"
    r"|Q\d+[\.\)]\s"        # "Q1. "
    r")"
)


@dataclass
class QuestionRegion:
    """A detected question region in the document."""

    index: int
    bbox: tuple[int, int, int, int]  # x, y, w, h
    image: np.ndarray
    text_preview: str = ""


@dataclass
class SegmentationResult:
    """Result of segmenting a document into questions."""

    questions: list[QuestionRegion] = field(default_factory=list)
    page_count: int = 0


class QuestionSegmenter:
    """Segments a scanned document image into individual question regions."""

    def __init__(
        self,
        min_gap_height: int = 20,
        min_content_height: int = 30,
        numbering_confidence: float = 0.5,
        use_ocr: bool = True,
    ) -> None:
        self._min_gap = min_gap_height
        self._min_content = min_content_height
        self._numbering_conf = numbering_confidence
        self._use_ocr = use_ocr
        self._ocr_available = self._check_ocr()

    def _check_ocr(self) -> bool:
        if not self._use_ocr:
            return False
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            logger.info("pytesseract/Tesseract not available — using visual gap analysis only")
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def segment(self, image: np.ndarray) -> SegmentationResult:
        """Segment a scanned document into question regions.

        Returns a SegmentationResult with detected questions.
        """
        if image is None or image.size == 0:
            return SegmentationResult()

        gray = self._to_gray(image)
        binary = self._binarize(gray)

        # Horizontal projection to find content/gap rows
        row_projection = self._row_projection(binary)
        content_blocks = self._find_content_blocks(row_projection)

        if not content_blocks:
            # Single question — whole image
            return SegmentationResult(
                questions=[QuestionRegion(
                    index=0,
                    bbox=(0, 0, image.shape[1], image.shape[0]),
                    image=image,
                )],
                page_count=1,
            )

        # If OCR available, get line-level text for numbering detection
        numbered_lines: dict[int, str] = {}
        if self._ocr_available:
            numbered_lines = self._detect_numbering(binary, image)

        # Merge content blocks into question regions
        questions = self._merge_into_questions(
            content_blocks, image, numbered_lines,
        )

        return SegmentationResult(
            questions=questions,
            page_count=len(questions),
        )

    # ------------------------------------------------------------------
    # Step 1: Preprocessing
    # ------------------------------------------------------------------

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 2:
            return image
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def _binarize(gray: np.ndarray) -> np.ndarray:
        # Simple Otsu threshold for clean scanned input
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return binary

    # ------------------------------------------------------------------
    # Step 2: Horizontal projection → content blocks
    # ------------------------------------------------------------------

    @staticmethod
    def _row_projection(binary: np.ndarray) -> np.ndarray:
        """Sum of white pixels per row. High = text/content, low = gap."""
        return binary.sum(axis=1).astype(np.float64)

    def _find_content_blocks(self, projection: np.ndarray) -> list[tuple[int, int]]:
        """Find contiguous ranges of content rows, then merge nearby lines."""
        h = len(projection)
        if h == 0 or projection.max() == 0:
            return []

        # Threshold: any row with non-trial content
        threshold = projection.max() * 0.02 if projection.max() > 0 else 1
        is_content = projection > threshold

        # Find individual text-line blocks
        raw_blocks: list[tuple[int, int]] = []
        start = None
        for i, val in enumerate(is_content):
            if val and start is None:
                start = i
            elif not val and start is not None:
                raw_blocks.append((start, i))
                start = None
        if start is not None:
            raw_blocks.append((start, h))

        if not raw_blocks:
            return []

        # Merge blocks separated by small gaps (within a question)
        # but keep splits where gaps exceed min_gap (between questions)
        merged: list[tuple[int, int]] = [raw_blocks[0]]
        for start, end in raw_blocks[1:]:
            prev_end = merged[-1][1]
            gap = start - prev_end
            if gap < self._min_gap:
                # Small gap — merge with previous block
                merged[-1] = (merged[-1][0], end)
            else:
                # Significant gap — new block
                merged.append((start, end))

        return merged

    # ------------------------------------------------------------------
    # Step 3: OCR-based numbering detection
    # ------------------------------------------------------------------

    def _detect_numbering(
        self, binary: np.ndarray, original: np.ndarray
    ) -> dict[int, str]:
        """Use OCR to find lines that start with numbering patterns.

        Returns {y_center: matched_text} for numbered lines.
        """
        try:
            import pytesseract
        except ImportError:
            return {}

        # Use original image for OCR (better quality than binary)
        gray = self._to_gray(original)
        data = pytesseract.image_to_data(
            gray, output_type=pytesseract.Output.DICT,
        )

        numbered = {}
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            conf = int(data["conf"][i])
            if conf < 30:
                continue

            if _NUMBERING_RE.match(text):
                y = data["top"][i] + data["height"][i] // 2
                line_text = text
                # Collect rest of words on same line
                for j in range(i + 1, n):
                    if abs(data["top"][j] - data["top"][i]) > data["height"][i]:
                        break
                    if data["text"][j].strip():
                        line_text += " " + data["text"][j].strip()
                numbered[y] = line_text

        return numbered

    # ------------------------------------------------------------------
    # Step 4: Merge blocks into question regions
    # ------------------------------------------------------------------

    def _merge_into_questions(
        self,
        blocks: list[tuple[int, int]],
        image: np.ndarray,
        numbered_lines: dict[int, str],
    ) -> list[QuestionRegion]:
        """Convert content blocks into question regions.

        Since _find_content_blocks already merged nearby text lines,
        each block represents a distinct content region. We treat
        each block as a potential question unless OCR numbering
        suggests merging adjacent blocks.
        """
        if not blocks:
            return []

        h, w = image.shape[:2]

        # Each block is a question by default
        questions: list[QuestionRegion] = []
        for q_idx, (y_start, y_end) in enumerate(blocks):
            # Add padding
            y_start_padded = max(0, y_start - 5)
            y_end_padded = min(h, y_end + 5)

            region_img = image[y_start_padded:y_end_padded, 0:w]

            # Find text preview from numbered lines
            preview = ""
            for y, text in numbered_lines.items():
                if y_start_padded <= y <= y_end_padded:
                    preview = text
                    break

            questions.append(QuestionRegion(
                index=q_idx,
                bbox=(0, y_start_padded, w, y_end_padded - y_start_padded),
                image=region_img,
                text_preview=preview,
            ))

        return questions
