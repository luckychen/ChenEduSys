"""Tutor panel — displays LLM tutoring feedback for a math question."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chenedusys.ai.tutor import LLMTutor, LLMProvider, TutorResponse

logger = logging.getLogger(__name__)


class TutorPanel(QWidget):
    """Side panel for LLM tutoring of a selected question."""

    tutor_response_ready = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tutor = LLMTutor()
        self._current_response: TutorResponse | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # API configuration
        config_label = QLabel("API Configuration")
        config_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(config_label)

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["Anthropic (Claude)", "OpenAI (GPT)"])
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_row.addWidget(self._provider_combo)
        provider_row.addStretch()
        layout.addLayout(provider_row)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API Key:"))
        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("Enter API key...")
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.editingFinished.connect(self._on_key_changed)
        key_row.addWidget(self._key_input)
        layout.addLayout(key_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("Auto")
        self._model_input.editingFinished.connect(self._on_model_changed)
        model_row.addWidget(self._model_input)
        layout.addLayout(model_row)

        # Tutor button
        self._tutor_btn = QPushButton("Get Tutoring")
        self._tutor_btn.setEnabled(False)
        self._tutor_btn.setStyleSheet("padding: 8px; font-weight: bold;")
        self._tutor_btn.clicked.connect(self._on_tutor_clicked)
        layout.addWidget(self._tutor_btn)

        # Response display
        layout.addWidget(self._make_label("Response"))

        self._response_display = QTextEdit()
        self._response_display.setReadOnly(True)
        self._response_display.setPlaceholderText("Load a question and click Get Tutoring")
        layout.addWidget(self._response_display, stretch=1)

        # Status
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(self._status_label)

    @staticmethod
    def _make_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        return label

    @property
    def tutor(self) -> LLMTutor:
        return self._tutor

    def set_question_image(self, image) -> None:
        """Set the current question image for tutoring."""
        self._question_image = image
        self._tutor_btn.setEnabled(self._tutor.is_configured and image is not None)

    def _on_provider_changed(self, index: int) -> None:
        provider = LLMProvider.ANTHROPIC if index == 0 else LLMProvider.OPENAI
        self._tutor.configure(provider=provider)
        self._model_input.setPlaceholderText(f"Default: {self._tutor.model}")
        self._update_tutor_btn()

    def _on_key_changed(self) -> None:
        self._tutor.configure(api_key=self._key_input.text().strip())
        self._update_tutor_btn()

    def _on_model_changed(self) -> None:
        text = self._model_input.text().strip()
        if text:
            self._tutor.configure(model=text)

    def _update_tutor_btn(self) -> None:
        has_image = hasattr(self, "_question_image") and self._question_image is not None
        self._tutor_btn.setEnabled(self._tutor.is_configured and has_image)

    def _on_tutor_clicked(self) -> None:
        if not hasattr(self, "_question_image") or self._question_image is None:
            return
        self._status_label.setText("Calling LLM...")
        self._status_label.setStyleSheet("font-size: 11px; color: orange;")

        import asyncio

        async def _run():
            try:
                resp = await self._tutor.tutor_image(self._question_image)
                self._current_response = resp
                self._display_response(resp)
                self.tutor_response_ready.emit(resp)
            except Exception as exc:
                self._status_label.setText(f"Error: {exc}")
                self._status_label.setStyleSheet("font-size: 11px; color: red;")
                logger.error("Tutor error: %s", exc)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_run())
            else:
                loop.run_until_complete(_run())
        except RuntimeError:
            asyncio.run(_run())

    def _display_response(self, resp: TutorResponse) -> None:
        if resp.is_empty:
            self._response_display.setPlainText("No response received.")
            self._status_label.setText("No response")
            self._status_label.setStyleSheet("font-size: 11px; color: red;")
            return

        html_parts = []

        if resp.concepts:
            html_parts.append("<b>Concepts:</b>")
            html_parts.append("<ul>")
            for c in resp.concepts:
                html_parts.append(f"<li>{c}</li>")
            html_parts.append("</ul>")

        if resp.difficulty:
            color = {"Easy": "green", "Medium": "orange", "Hard": "red"}.get(
                resp.difficulty, "gray"
            )
            html_parts.append(
                f"<b>Difficulty:</b> <span style='color:{color}'>{resp.difficulty}"
                f"</span> ({resp.difficulty_level}/5)"
            )

        if resp.hints:
            html_parts.append("<b>Hints:</b>")
            html_parts.append("<ol>")
            for h in resp.hints:
                html_parts.append(f"<li>{h}</li>")
            html_parts.append("</ol>")

        if resp.solution:
            html_parts.append("<b>Solution:</b>")
            html_parts.append(f"<p>{resp.solution.replace(chr(10), '<br>')}</p>")

        self._response_display.setHtml("".join(html_parts))
        self._status_label.setText("Response received")
        self._status_label.setStyleSheet("font-size: 11px; color: green;")
