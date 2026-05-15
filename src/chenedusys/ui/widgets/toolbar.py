"""Drawing toolbar: pen, eraser, clear, stop buttons."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QWidget,
)


class Toolbar(QWidget):
    """Horizontal toolbar for paint controls."""

    pen_clicked = Signal()
    eraser_clicked = Signal()
    clear_clicked = Signal()
    stop_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._pen_btn = QPushButton("Pen")
        self._pen_btn.setCheckable(True)
        self._pen_btn.setChecked(True)
        self._pen_btn.clicked.connect(self._on_pen)
        layout.addWidget(self._pen_btn)

        self._eraser_btn = QPushButton("Eraser")
        self._eraser_btn.setCheckable(True)
        self._eraser_btn.clicked.connect(self._on_eraser)
        layout.addWidget(self._eraser_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self.clear_clicked.emit)
        layout.addWidget(self._clear_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self._stop_btn)

        self._stopped = False

    @property
    def stopped(self) -> bool:
        return self._stopped

    def set_mode_pen(self) -> None:
        self._pen_btn.setChecked(True)
        self._eraser_btn.setChecked(False)

    def set_mode_eraser(self) -> None:
        self._pen_btn.setChecked(False)
        self._eraser_btn.setChecked(True)

    def _on_pen(self) -> None:
        self.set_mode_pen()
        self.pen_clicked.emit()

    def _on_eraser(self) -> None:
        self.set_mode_eraser()
        self.eraser_clicked.emit()

    def _on_stop(self) -> None:
        self._stopped = True
        self._pen_btn.setEnabled(False)
        self._eraser_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self.stop_clicked.emit()
