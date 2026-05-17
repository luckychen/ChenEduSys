"""Unit tests for the document scanner."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from chenedusys.ai.scanner import DocumentScanner, ScanResult

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "scanner"


def _load_fixture(name: str) -> np.ndarray:
    path = FIXTURE_DIR / name
    img = cv2.imread(str(path))
    assert img is not None, f"Fixture not found: {path}"
    return img


def _fixture_meta() -> dict:
    path = FIXTURE_DIR / "fixtures_meta.json"
    if not path.exists():
        pytest.skip("Run tests/fixtures/generate_scanner_fixtures.py first")
    return json.loads(path.read_text())


@pytest.fixture
def scanner():
    return DocumentScanner()


@pytest.fixture
def clean_doc():
    return _load_fixture("clean_doc.png")


class TestDocumentScanner:

    def test_clean_doc_scan(self, scanner, clean_doc):
        result = scanner.scan(clean_doc)
        assert result is not None
        assert isinstance(result, ScanResult)
        assert result.image is not None
        assert result.height > 0
        assert result.width > 0

    def test_output_is_reasonable_size(self, scanner, clean_doc):
        result = scanner.scan(clean_doc)
        # Output should be roughly document-sized, not tiny or huge
        assert result.width >= 100
        assert result.height >= 100

    def test_angled_15deg_scan(self, scanner):
        img = _load_fixture("angled_15deg.png")
        result = scanner.scan(img)
        assert result is not None
        assert result.width >= 100
        assert result.height >= 100

    def test_angled_30deg_scan(self, scanner):
        img = _load_fixture("angled_30deg.png")
        result = scanner.scan(img)
        assert result is not None
        assert result.width >= 100
        assert result.height >= 100

    def test_dark_photo_scan(self, scanner):
        img = _load_fixture("dark_photo.png")
        result = scanner.scan(img)
        assert result is not None
        # After enhancement, the image should be brighter (mostly white background)
        gray = cv2.cvtColor(result.image, cv2.COLOR_BGR2GRAY)
        mean_brightness = gray.mean()
        assert mean_brightness > 200  # enhanced to near-white

    def test_bright_glare_scan(self, scanner):
        img = _load_fixture("bright_glare.png")
        result = scanner.scan(img)
        assert result is not None

    def test_low_res_scan(self, scanner):
        img = _load_fixture("low_res_640x480.png")
        result = scanner.scan(img)
        assert result is not None

    def test_blurry_noisy_scan(self, scanner):
        img = _load_fixture("blurry_noisy.png")
        result = scanner.scan(img)
        assert result is not None

    def test_rotated_45deg_scan(self, scanner):
        img = _load_fixture("rotated_45deg.png")
        result = scanner.scan(img)
        assert result is not None

    def test_no_document_detected_uses_fallback(self, scanner):
        # Pure noise image — no document edges
        noise = np.random.randint(0, 255, (500, 500, 3), dtype=np.uint8)
        result = scanner.scan(noise)
        assert result is not None  # fallback crops full image

    def test_scan_file(self, scanner, tmp_path):
        # Create a simple test image
        img = np.ones((300, 400, 3), dtype=np.uint8) * 255
        cv2.rectangle(img, (20, 20), (380, 280), (0, 0, 0), 2)
        path = str(tmp_path / "test.png")
        cv2.imwrite(path, img)

        result = scanner.scan_file(path)
        assert result is not None

    def test_scan_file_nonexistent(self, scanner):
        result = scanner.scan_file("/nonexistent/image.png")
        assert result is None

    def test_save_result_as_png(self, scanner, clean_doc, tmp_path):
        result = scanner.scan(clean_doc)
        assert result is not None

        out_path = str(tmp_path / "output.png")
        success = scanner.save(result, out_path)
        assert success

        loaded = cv2.imread(out_path)
        assert loaded is not None
        assert loaded.shape[0] == result.height

    def test_corners_detected_on_clean(self, scanner, clean_doc):
        result = scanner.scan(clean_doc)
        # Clean doc should have detectable corners (or fallback)
        assert result.corners is not None
        assert result.corners.shape == (4, 2)

    def test_enhanced_image_is_mostly_white(self, scanner, clean_doc):
        result = scanner.scan(clean_doc)
        gray = cv2.cvtColor(result.image, cv2.COLOR_BGR2GRAY)
        # After adaptive threshold, background should be white (255)
        white_pct = (gray > 200).sum() / gray.size
        assert white_pct > 0.6  # at least 60% white background


class TestCornerOrdering:

    def test_order_corners(self):
        corners = np.array([
            [100, 0],    # top-right
            [0, 0],      # top-left
            [100, 100],  # bottom-right
            [0, 100],    # bottom-left
        ], dtype=np.float32)

        ordered = DocumentScanner._order_corners(corners)
        assert ordered[0][0] < ordered[1][0]  # tl before tr
        assert ordered[0][1] < ordered[3][1]  # tl above bl

    def test_order_corners_unordered(self):
        corners = np.array([
            [300, 50],
            [50, 300],
            [50, 50],
            [300, 300],
        ], dtype=np.float32)

        ordered = DocumentScanner._order_corners(corners)
        # Top-left should have smallest sum
        assert ordered[0][0] + ordered[0][1] < ordered[2][0] + ordered[2][1]
