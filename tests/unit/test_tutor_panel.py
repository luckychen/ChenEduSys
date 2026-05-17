"""Unit tests for the tutor panel UI widget."""

from __future__ import annotations

import numpy as np
import pytest

from chenedusys.ai.tutor import TutorResponse
from chenedusys.ui.widgets.tutor_panel import TutorPanel


@pytest.fixture
def panel(qtbot):
    p = TutorPanel()
    qtbot.addWidget(p)
    return p


class TestTutorPanel:

    def test_initial_state(self, panel):
        assert not panel._tutor_btn.isEnabled()

    def test_tutor_btn_enabled_with_key_and_image(self, panel):
        panel._key_input.setText("test-api-key")
        panel._on_key_changed()
        panel.set_question_image(np.zeros((100, 100, 3), dtype=np.uint8))
        assert panel._tutor_btn.isEnabled()

    def test_tutor_btn_disabled_without_key(self, panel):
        panel.set_question_image(np.zeros((100, 100, 3), dtype=np.uint8))
        assert not panel._tutor_btn.isEnabled()

    def test_tutor_btn_disabled_without_image(self, panel):
        panel._key_input.setText("test-api-key")
        panel._on_key_changed()
        assert not panel._tutor_btn.isEnabled()

    def test_display_response_with_concepts(self, panel):
        resp = TutorResponse(
            concepts=["algebra", "factoring"],
            difficulty="Medium",
            difficulty_level=3,
            hints=["Try factoring.", "Look for patterns."],
            solution="x = 5",
        )
        panel._display_response(resp)

        html = panel._response_display.toHtml()
        assert "algebra" in html
        assert "factoring" in html
        assert "Medium" in html
        assert "Try factoring" in html

    def test_display_empty_response(self, panel):
        resp = TutorResponse()
        panel._display_response(resp)
        assert "No response" in panel._response_display.toPlainText()

    def test_provider_change(self, panel):
        panel._provider_combo.setCurrentIndex(1)  # OpenAI
        from chenedusys.ai.tutor import LLMProvider
        assert panel.tutor.provider == LLMProvider.OPENAI

    def test_model_input(self, panel):
        panel._model_input.setText("custom-model")
        panel._on_model_changed()
        assert panel.tutor.model == "custom-model"

    def test_display_response_difficulty_colors(self, panel):
        for diff in ["Easy", "Medium", "Hard"]:
            resp = TutorResponse(difficulty=diff, difficulty_level=2, solution="x=1")
            panel._display_response(resp)
            html = panel._response_display.toHtml()
            # Qt renders the difficulty text with a colored span
            assert diff in html
