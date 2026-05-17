"""Unit tests for the question segmenter and PDF generator."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from chenedusys.ai.segmenter import QuestionSegmenter, SegmentationResult
from chenedusys.ai.question_pdf import questions_to_pdf

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "segmenter"


def _load_fixture(name: str) -> np.ndarray:
    path = FIXTURE_DIR / name
    img = cv2.imread(str(path))
    assert img is not None, f"Fixture not found: {path}"
    return img


def _fixture_meta() -> dict:
    path = FIXTURE_DIR / "fixtures_meta.json"
    if not path.exists():
        pytest.skip("Run tests/fixtures/generate_segmenter_fixtures.py first")
    return json.loads(path.read_text())


@pytest.fixture
def segmenter():
    return QuestionSegmenter(use_ocr=False)


@pytest.fixture
def segmenter_with_ocr():
    return QuestionSegmenter(use_ocr=True)


class TestSegmenter:

    def test_simple_numbered_finds_questions(self, segmenter):
        img = _load_fixture("simple_numbered.png")
        result = segmenter.segment(img)
        assert result.page_count >= 3
        assert all(q.image is not None for q in result.questions)
        assert all(q.image.shape[0] > 0 for q in result.questions)

    def test_section_headers_finds_questions(self, segmenter):
        img = _load_fixture("section_headers.png")
        result = segmenter.segment(img)
        assert result.page_count >= 3

    def test_with_figure_preserves_regions(self, segmenter):
        img = _load_fixture("with_figure.png")
        result = segmenter.segment(img)
        assert result.page_count >= 2
        # At least one question should be taller (contains a figure)
        heights = [q.image.shape[0] for q in result.questions]
        assert max(heights) > min(heights)

    def test_dense_questions(self, segmenter):
        img = _load_fixture("dense_questions.png")
        result = segmenter.segment(img)
        # Dense questions with very small gaps may merge — at least 1 question
        assert result.page_count >= 1
        # But the full content should be captured
        total_h = sum(q.bbox[3] for q in result.questions)
        assert total_h > 100

    def test_single_question(self, segmenter):
        img = _load_fixture("single_question.png")
        result = segmenter.segment(img)
        assert result.page_count >= 1
        assert result.questions[0].image.shape[0] > 20

    def test_sub_numbering(self, segmenter):
        img = _load_fixture("sub_numbering.png")
        result = segmenter.segment(img)
        assert result.page_count >= 1

    def test_two_column(self, segmenter):
        img = _load_fixture("two_column.png")
        result = segmenter.segment(img)
        assert result.page_count >= 1

    def test_empty_image_returns_empty(self, segmenter):
        result = segmenter.segment(np.array([]))
        assert result.page_count == 0

    def test_none_image_returns_empty(self, segmenter):
        result = segmenter.segment(None)
        assert result.page_count == 0

    def test_white_image_returns_single(self, segmenter):
        img = np.ones((500, 400, 3), dtype=np.uint8) * 255
        result = segmenter.segment(img)
        # All white — no content blocks → single fallback
        assert result.page_count == 1

    def test_question_bboxes_valid(self, segmenter):
        img = _load_fixture("simple_numbered.png")
        result = segmenter.segment(img)
        h, w = img.shape[:2]
        for q in result.questions:
            x, y, qw, qh = q.bbox
            assert x >= 0
            assert y >= 0
            assert qw > 0
            assert qh > 0
            assert y + qh <= h

    def test_question_images_match_bbox(self, segmenter):
        img = _load_fixture("simple_numbered.png")
        result = segmenter.segment(img)
        for q in result.questions:
            _, _, bw, bh = q.bbox
            assert q.image.shape[0] == bh
            assert q.image.shape[1] == bw


class TestSegmenterOCR:

    def test_ocr_flag_respected(self):
        seg = QuestionSegmenter(use_ocr=False)
        assert not seg._ocr_available

    def test_simple_with_ocr(self, segmenter_with_ocr):
        img = _load_fixture("simple_numbered.png")
        result = segmenter_with_ocr.segment(img)
        assert result.page_count >= 3


class TestQuestionPDF:

    def test_generate_pdf(self, segmenter, tmp_path):
        img = _load_fixture("simple_numbered.png")
        result = segmenter.segment(img)

        out_path = str(tmp_path / "questions.pdf")
        success = questions_to_pdf(result, out_path)
        assert success
        assert Path(out_path).exists()
        assert Path(out_path).stat().st_size > 0

    def test_pdf_has_correct_page_count(self, segmenter, tmp_path):
        import fitz

        img = _load_fixture("simple_numbered.png")
        result = segmenter.segment(img)

        out_path = str(tmp_path / "questions.pdf")
        questions_to_pdf(result, out_path)

        doc = fitz.open(out_path)
        assert len(doc) == result.page_count
        doc.close()

    def test_empty_result_returns_false(self, tmp_path):
        result = SegmentationResult()
        out_path = str(tmp_path / "empty.pdf")
        assert not questions_to_pdf(result, out_path)

    def test_pdf_with_figure_question(self, segmenter, tmp_path):
        import fitz

        img = _load_fixture("with_figure.png")
        result = segmenter.segment(img)

        out_path = str(tmp_path / "figures.pdf")
        questions_to_pdf(result, out_path)

        doc = fitz.open(out_path)
        assert len(doc) >= 2
        # First page should have an image inserted
        page = doc[0]
        imgs = page.get_images()
        assert len(imgs) >= 1
        doc.close()

    def test_custom_answer_ratio(self, segmenter, tmp_path):
        import fitz

        img = _load_fixture("single_question.png")
        result = segmenter.segment(img)

        out_path = str(tmp_path / "custom.pdf")
        questions_to_pdf(result, out_path, answer_ratio=0.5)

        assert Path(out_path).exists()
        doc = fitz.open(out_path)
        assert len(doc) >= 1
        doc.close()

    def test_all_fixtures_generate_pdf(self, segmenter, tmp_path):
        meta = _fixture_meta()
        for name in meta:
            img = _load_fixture(f"{name}.png")
            result = segmenter.segment(img)
            out_path = str(tmp_path / f"{name}.pdf")
            assert questions_to_pdf(result, out_path), f"Failed for {name}"
