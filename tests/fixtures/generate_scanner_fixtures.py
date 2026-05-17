"""Generate synthetic test images for the document scanner.

Creates a clean "document" with text and grid lines, then applies
realistic distortions to simulate phone photos. Each fixture has
a companion JSON file with expected corner coordinates.

Usage:
    python tests/fixtures/generate_scanner_fixtures.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

FIXTURE_DIR = Path(__file__).parent / "scanner"
DOC_WIDTH = 800
DOC_HEIGHT = 1100
MARGIN = 40


def _create_clean_document() -> tuple[np.ndarray, np.ndarray]:
    """Create a white page with text and grid lines. Returns (image, corners)."""
    img = np.ones((DOC_HEIGHT, DOC_WIDTH, 3), dtype=np.uint8) * 255

    # Grid lines
    for x in range(MARGIN, DOC_WIDTH - MARGIN, 40):
        cv2.line(img, (x, MARGIN), (x, DOC_HEIGHT - MARGIN), (200, 200, 200), 1)
    for y in range(MARGIN, DOC_HEIGHT - MARGIN, 40):
        cv2.line(img, (MARGIN, y), (DOC_WIDTH - MARGIN, y), (200, 200, 200), 1)

    # Title text
    cv2.putText(img, "Math Practice", (MARGIN + 20, MARGIN + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)

    # Questions
    questions = [
        "1. Solve x^2 + 3x - 4 = 0",
        "2. Find the area of the triangle.",
        "3. Compute 5! / (3! * 2!)",
        "4. If f(x) = 2x + 1, find f(3).",
        "5. What is the sum of angles in a hexagon?",
    ]
    for i, q in enumerate(questions):
        y = MARGIN + 120 + i * 80
        cv2.putText(img, q, (MARGIN + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    # A triangle figure
    pts = np.array([
        [600, 400], [700, 550], [500, 550]
    ], np.int32)
    cv2.polylines(img, [pts], True, (0, 0, 0), 2)
    cv2.putText(img, "Fig. 1", (570, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

    corners = np.array([
        [0, 0],
        [DOC_WIDTH - 1, 0],
        [DOC_WIDTH - 1, DOC_HEIGHT - 1],
        [0, DOC_HEIGHT - 1],
    ], dtype=np.float32)

    return img, corners


def _apply_perspective(img: np.ndarray, angle_x: float, angle_y: float) -> tuple[np.ndarray, np.ndarray]:
    """Apply perspective warp to simulate angled photo. Returns (warped, new_corners)."""
    h, w = img.shape[:2]
    pad = max(h, w) // 2

    # Canvas larger than image
    canvas = np.ones((h + 2 * pad, w + 2 * pad, 3), dtype=np.uint8) * 220
    canvas[pad:pad + h, pad:pad + w] = img

    ch, cw = canvas.shape[:2]

    # Perspective distortion
    dx = int(cw * 0.15 * math.sin(angle_x))
    dy = int(ch * 0.15 * math.sin(angle_y))

    src = np.array([
        [pad, pad],
        [pad + w, pad],
        [pad + w, pad + h],
        [pad, pad + h],
    ], dtype=np.float32)

    dst = np.array([
        [pad + dx, pad + dy],
        [pad + w - dx, pad + dy + abs(dy) // 2],
        [pad + w + dx // 2, pad + h - dy],
        [pad - dx // 2, pad + h + dy],
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(canvas, matrix, (cw, ch))

    # Crop to content
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(binary)
    if coords is not None:
        x, y, bw, bh = cv2.boundingRect(coords)
        margin = 20
        x = max(0, x - margin)
        y = max(0, y - margin)
        warped = warped[y:y + bh + 2 * margin, x:x + bw + 2 * margin]
        new_corners = dst - np.array([x, y])
    else:
        new_corners = dst - np.array([pad, pad])

    return warped, new_corners


def _darken(img: np.ndarray, factor: float = 0.4) -> np.ndarray:
    return (img.astype(np.float32) * factor).astype(np.uint8)


def _brighten(img: np.ndarray, factor: float = 1.8) -> np.ndarray:
    result = (img.astype(np.float32) * factor).clip(0, 255).astype(np.uint8)
    return result


def _blur(img: np.ndarray, kernel: int = 7) -> np.ndarray:
    return cv2.GaussianBlur(img, (kernel, kernel), 0)


def _add_noise(img: np.ndarray, std: int = 25) -> np.ndarray:
    noise = np.random.normal(0, std, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def generate_all() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    clean, clean_corners = _create_clean_document()

    fixtures = {}

    # 1. Clean document (baseline)
    path = FIXTURE_DIR / "clean_doc.png"
    cv2.imwrite(str(path), clean)
    fixtures["clean_doc"] = {"file": path.name, "corners": clean_corners.tolist()}

    # 2. Angled 15 degrees
    angled15, c15 = _apply_perspective(clean, 0.3, 0.2)
    path = FIXTURE_DIR / "angled_15deg.png"
    cv2.imwrite(str(path), angled15)
    fixtures["angled_15deg"] = {"file": path.name, "corners": c15.tolist()}

    # 3. Angled 30 degrees
    angled30, c30 = _apply_perspective(clean, 0.6, 0.4)
    path = FIXTURE_DIR / "angled_30deg.png"
    cv2.imwrite(str(path), angled30)
    fixtures["angled_30deg"] = {"file": path.name, "corners": c30.tolist()}

    # 4. Rotated 45 degrees
    rotated = _rotate_image(clean, 45)
    path = FIXTURE_DIR / "rotated_45deg.png"
    cv2.imwrite(str(path), rotated)
    fixtures["rotated_45deg"] = {"file": path.name, "corners": None, "note": "rotated, corners not applicable"}

    # 5. Dark photo
    dark = _darken(_apply_perspective(clean, 0.2, 0.1)[0], 0.35)
    path = FIXTURE_DIR / "dark_photo.png"
    cv2.imwrite(str(path), dark)
    fixtures["dark_photo"] = {"file": path.name, "corners": None, "note": "dark, corners from perspective"}

    # 6. Bright glare
    bright_base = _apply_perspective(clean, 0.15, 0.1)[0]
    h, w = bright_base.shape[:2]
    glare_mask = np.zeros((h, w), dtype=np.float32)
    cv2.circle(glare_mask, (w // 2, h // 3), min(h, w) // 6, 0.8, -1)
    glare = cv2.GaussianBlur(glare_mask, (0, 0), 40)
    for c in range(3):
        bright_base[:, :, c] = np.clip(
            bright_base[:, :, c].astype(np.float32) + glare * 200, 0, 255
        ).astype(np.uint8)
    path = FIXTURE_DIR / "bright_glare.png"
    cv2.imwrite(str(path), bright_base)
    fixtures["bright_glare"] = {"file": path.name, "corners": None}

    # 7. Low resolution
    low = cv2.resize(clean, (640, 480))
    low = cv2.resize(low, (DOC_WIDTH, DOC_HEIGHT))
    path = FIXTURE_DIR / "low_res_640x480.png"
    cv2.imwrite(str(path), low)
    fixtures["low_res_640x480"] = {"file": path.name, "corners": None, "note": "upscaled from 640x480"}

    # 8. Blurry + noisy (realistic phone photo)
    blurry = _blur(_add_noise(_darken(_apply_perspective(clean, 0.25, 0.15)[0], 0.7)), 5)
    path = FIXTURE_DIR / "blurry_noisy.png"
    cv2.imwrite(str(path), blurry)
    fixtures["blurry_noisy"] = {"file": path.name, "corners": None}

    # Save metadata
    meta_path = FIXTURE_DIR / "fixtures_meta.json"
    with open(meta_path, "w") as f:
        json.dump(fixtures, f, indent=2)

    print(f"Generated {len(fixtures)} fixtures in {FIXTURE_DIR}/")
    total_size = sum(f.stat().st_size for f in FIXTURE_DIR.glob("*.png"))
    print(f"Total size: {total_size / 1024:.0f} KB")


def _rotate_image(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    diagonal = int(math.sqrt(w**2 + h**2))
    canvas = np.ones((diagonal, diagonal, 3), dtype=np.uint8) * 220
    x_off = (diagonal - w) // 2
    y_off = (diagonal - h) // 2
    canvas[y_off:y_off + h, x_off:x_off + w] = img

    matrix = cv2.getRotationMatrix2D((diagonal // 2, diagonal // 2), angle, 1.0)
    rotated = cv2.warpAffine(canvas, matrix, (diagonal, diagonal))
    return rotated


if __name__ == "__main__":
    generate_all()
