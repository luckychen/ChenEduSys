"""Generate synthetic test images for the question segmenter.

Creates documents with various question layouts:
  - Simple numbered questions
  - Questions with section headers
  - Mixed text + figure regions
  - Dense questions with small gaps

Usage:
    python tests/fixtures/generate_segmenter_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

FIXTURE_DIR = Path(__file__).parent / "segmenter"
PAGE_W = 800
PAGE_H = 1100
MARGIN = 40


def _white_page() -> np.ndarray:
    return np.ones((PAGE_H, PAGE_W, 3), dtype=np.uint8) * 255


def _add_text(
    img: np.ndarray, text: str, x: int, y: int,
    scale: float = 0.6, thick: int = 2, color: tuple = (0, 0, 0),
) -> int:
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)
    return y


def _draw_rect(img: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), 2)
    # Fill with light gray
    overlay = img[y:y + h, x:x + w].copy()
    overlay[:] = (230, 230, 230)
    cv2.addWeighted(overlay, 0.5, img[y:y + h, x:x + w], 0.5, 0, img[y:y + h, x:x + w])


def generate_simple_numbered() -> tuple[np.ndarray, list[dict]]:
    """5 numbered questions with clear gaps between them."""
    img = _white_page()
    questions = []
    y = MARGIN + 40

    for i in range(1, 6):
        top = y
        y = _add_text(img, f"{i}. Solve for x in the equation x^2 + {i * 2}x + {i * 3} = 0",
                       MARGIN + 10, y)
        y += 10
        _add_text(img, f"   Show all your work and simplify your answer.",
                   MARGIN + 10, y, scale=0.5, thick=1)
        y += 15
        _add_text(img, f"   Hint: try factoring the quadratic.",
                   MARGIN + 10, y, scale=0.45, thick=1, color=(120, 120, 120))
        y += 40  # gap
        questions.append({"index": i - 1, "top": top, "bottom": y - 40, "text": f"Q{i}"})

    return img, questions


def generate_section_headers() -> tuple[np.ndarray, list[dict]]:
    """Section headers followed by questions with no blank line."""
    img = _white_page()
    questions = []
    y = MARGIN + 40

    # Section 1
    y = _add_text(img, "Section A: Algebra", MARGIN + 10, y, scale=0.8, thick=2)
    y += 15
    top = y
    y = _add_text(img, "1. Factor the expression: 6x^2 + 11x - 10", MARGIN + 10, y)
    y += 10
    _add_text(img, "   Write your answer as a product of two binomials.", MARGIN + 10, y, scale=0.5, thick=1)
    y += 50
    questions.append({"index": 0, "top": top, "bottom": y - 50, "text": "Q1"})

    top = y
    y = _add_text(img, "2. Simplify: (3x - 2)^2", MARGIN + 10, y)
    y += 50
    questions.append({"index": 1, "top": top, "bottom": y - 50, "text": "Q2"})

    # Section 2
    y = _add_text(img, "Section B: Geometry", MARGIN + 10, y, scale=0.8, thick=2)
    y += 15
    top = y
    y = _add_text(img, "3. Find the area of a triangle with base 8 and height 5.", MARGIN + 10, y)
    y += 50
    questions.append({"index": 2, "top": top, "bottom": y - 50, "text": "Q3"})

    top = y
    y = _add_text(img, "4. A circle has radius 7. Find its circumference.", MARGIN + 10, y)
    y += 50
    questions.append({"index": 3, "top": top, "bottom": y - 50, "text": "Q4"})

    return img, questions


def generate_with_figure() -> tuple[np.ndarray, list[dict]]:
    """Questions with embedded figures (geometry)."""
    img = _white_page()
    questions = []
    y = MARGIN + 40

    # Q1 with triangle figure
    top = y
    y = _add_text(img, "1. In the triangle below, find angle A.", MARGIN + 10, y)
    y += 10
    pts = np.array([[500, y], [600, y + 120], [400, y + 120]], np.int32)
    cv2.polylines(img, [pts], True, (0, 0, 0), 2)
    cv2.putText(img, "A", (510, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, "B", (395, y + 130), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, "C", (605, y + 130), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    y += 140
    y += 40
    questions.append({"index": 0, "top": top, "bottom": y - 40, "text": "Q1", "has_figure": True})

    # Q2 with rectangle
    top = y
    y = _add_text(img, "2. The rectangle below has area 48. Find the perimeter.", MARGIN + 10, y)
    y += 10
    _draw_rect(img, 400, y, 150, 80)
    cv2.putText(img, "?", (470, y + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.putText(img, "8", (380, y + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    y += 100
    y += 40
    questions.append({"index": 1, "top": top, "bottom": y - 40, "text": "Q2", "has_figure": True})

    # Q3 plain text
    top = y
    y = _add_text(img, "3. Compute: 7! / (4! * 3!)", MARGIN + 10, y)
    y += 40
    questions.append({"index": 2, "top": top, "bottom": y - 40, "text": "Q3"})

    return img, questions


def generate_dense_questions() -> tuple[np.ndarray, list[dict]]:
    """Many short questions with small gaps."""
    img = _white_page()
    questions = []
    y = MARGIN + 40

    for i in range(1, 11):
        top = y
        y = _add_text(img, f"{i}. What is {i * 3} + {i * 7}?", MARGIN + 10, y, scale=0.55)
        y += 25  # small gap
        questions.append({"index": i - 1, "top": top, "bottom": y - 25, "text": f"Q{i}"})

    return img, questions


def generate_single_question() -> tuple[np.ndarray, list[dict]]:
    """Only one question — no splitting needed."""
    img = _white_page()
    y = MARGIN + 60
    top = y
    y = _add_text(img, "1. Prove that the sum of angles in any triangle is 180 degrees.",
                   MARGIN + 10, y, scale=0.7)
    y += 20
    _add_text(img, "   Use the parallel postulate in your proof.", MARGIN + 10, y, scale=0.5, thick=1)

    return img, [{"index": 0, "top": top, "bottom": y, "text": "Q1"}]


def generate_sub_numbering() -> tuple[np.ndarray, list[dict]]:
    """Questions with sub-parts: (a), (b), (c)."""
    img = _white_page()
    questions = []
    y = MARGIN + 40

    top = y
    y = _add_text(img, "1. Consider the function f(x) = 2x^2 - 3x + 1.", MARGIN + 10, y)
    y += 8
    _add_text(img, "   (a) Find f(0).", MARGIN + 10, y, scale=0.55)
    y += 20
    _add_text(img, "   (b) Find f(-1).", MARGIN + 10, y, scale=0.55)
    y += 20
    _add_text(img, "   (c) Find the vertex of the parabola.", MARGIN + 10, y, scale=0.55)
    y += 40
    questions.append({"index": 0, "top": top, "bottom": y - 40, "text": "Q1", "has_subparts": True})

    top = y
    y = _add_text(img, "2. A bag contains 5 red and 3 blue marbles.", MARGIN + 10, y)
    y += 8
    _add_text(img, "   (a) What is P(red)?", MARGIN + 10, y, scale=0.55)
    y += 20
    _add_text(img, "   (b) What is P(red or blue)?", MARGIN + 10, y, scale=0.55)
    y += 40
    questions.append({"index": 1, "top": top, "bottom": y - 40, "text": "Q2", "has_subparts": True})

    return img, questions


def generate_two_column() -> tuple[np.ndarray, list[dict]]:
    """Two-column layout with questions on both sides."""
    img = _white_page()
    questions = []
    y = MARGIN + 40
    col_w = (PAGE_W - 3 * MARGIN) // 2

    # Left column
    for i in range(1, 4):
        top = y
        _add_text(img, f"{i}. Compute {i * 5} * {i * 3}", MARGIN + 10, y, scale=0.5)
        y += 40
        questions.append({"index": i - 1, "top": top, "bottom": y - 40, "text": f"Q{i}", "column": "left"})

    # Right column
    y = MARGIN + 40
    for i in range(4, 7):
        top = y
        _add_text(img, f"{i}. Solve x + {i} = {i * 2}",
                   MARGIN + col_w + MARGIN + 10, y, scale=0.5)
        y += 40
        questions.append({"index": i - 1, "top": top, "bottom": y - 40, "text": f"Q{i}", "column": "right"})

    # Draw column separator
    cv2.line(img, (MARGIN + col_w + MARGIN // 2, MARGIN),
             (MARGIN + col_w + MARGIN // 2, PAGE_H - MARGIN), (200, 200, 200), 1)

    return img, questions


def generate_all() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    generators = {
        "simple_numbered": generate_simple_numbered,
        "section_headers": generate_section_headers,
        "with_figure": generate_with_figure,
        "dense_questions": generate_dense_questions,
        "single_question": generate_single_question,
        "sub_numbering": generate_sub_numbering,
        "two_column": generate_two_column,
    }

    meta = {}
    for name, gen in generators.items():
        img, questions = gen()
        path = FIXTURE_DIR / f"{name}.png"
        cv2.imwrite(str(path), img)
        meta[name] = {
            "file": path.name,
            "question_count": len(questions),
            "questions": questions,
        }

    meta_path = FIXTURE_DIR / "fixtures_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Generated {len(generators)} fixtures in {FIXTURE_DIR}/")
    total = sum(f.stat().st_size for f in FIXTURE_DIR.glob("*.png"))
    print(f"Total size: {total / 1024:.0f} KB")


if __name__ == "__main__":
    generate_all()
