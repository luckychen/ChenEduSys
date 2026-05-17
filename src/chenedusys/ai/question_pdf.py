"""Generate one-question-per-page PDFs from segmented question regions.

Each page contains:
  - The cropped question image (top portion)
  - Blank answer space (bottom portion)
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from chenedusys.ai.segmenter import SegmentationResult

logger = logging.getLogger(__name__)

# A4 at 150 DPI
_A4_WIDTH_PT = 595
_A4_HEIGHT_PT = 842

# Answer space as fraction of page height
_ANSWER_SPACE_RATIO = 0.35


def questions_to_pdf(
    result: SegmentationResult,
    output_path: str,
    answer_ratio: float = _ANSWER_SPACE_RATIO,
) -> bool:
    """Save segmented questions as a one-question-per-page PDF.

    Args:
        result: Segmentation result with question regions.
        output_path: Where to save the PDF.
        answer_ratio: Fraction of page reserved for blank answer space.

    Returns:
        True if saved successfully.
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF (fitz) required for PDF generation")
        return False

    if not result.questions:
        logger.warning("No questions to export")
        return False

    try:
        doc = fitz.open()

        for q in result.questions:
            page = doc.new_page(width=_A4_WIDTH_PT, height=_A4_HEIGHT_PT)
            _insert_question_image(doc, page, q.image, answer_ratio)

        doc.save(output_path, deflate=True)
        doc.close()
        return True
    except Exception as exc:
        logger.error("Failed to generate PDF: %s", exc)
        return False


def _insert_question_image(
    doc, page, image: np.ndarray, answer_ratio: float,
) -> None:
    """Insert a question image into the top portion of a PDF page."""
    import fitz

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]

    # Encode as PNG for quality
    _, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    img_bytes = buf.tobytes()

    # Calculate image placement
    page_w = page.rect.width
    page_h = page.rect.height

    question_area_h = page_h * (1 - answer_ratio)
    margin = 15

    # Scale image to fit within page width and question area height
    scale_w = (page_w - 2 * margin) / w
    scale_h = (question_area_h - 2 * margin) / h
    scale = min(scale_w, scale_h)

    display_w = w * scale
    display_h = h * scale

    x = (page_w - display_w) / 2
    y = margin

    rect = fitz.Rect(x, y, x + display_w, y + display_h)

    page.insert_image(
        rect,
        stream=img_bytes,
    )

    # Draw a light separator line between question and answer space
    sep_y = question_area_h
    shape = page.new_shape()
    shape.draw_line(
        fitz.Point(margin, sep_y),
        fitz.Point(page_w - margin, sep_y),
    )
    shape.finish(color=(0.7, 0.7, 0.7), width=0.5)
    shape.commit()

    # Add "Answer:" label
    text_point = fitz.Point(margin + 5, sep_y + 15)
    page.insert_text(
        text_point, "Answer:",
        fontsize=11, color=(0.5, 0.5, 0.5),
    )
