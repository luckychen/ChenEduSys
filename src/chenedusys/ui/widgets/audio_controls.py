"""Audio controls — mute/unmute button and volume slider."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)


class AudioControls(QWidget):
    """Compact audio control bar with mute button and volume slider."""

    mute_toggled = Signal(bool)
    volume_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._muted = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._mute_btn = QPushButton("Mic On")
        self._mute_btn.setFixedWidth(80)
        self._mute_btn.setStyleSheet("padding: 4px;")
        self._mute_btn.clicked.connect(self._toggle_mute)
        layout.addWidget(self._mute_btn)

        self._vol_label = QLabel("Vol:")
        self._vol_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._vol_label)

        self._vol_slider = QSlider()
        self._vol_slider.setOrientation(Qt.Horizontal if False else Qt.Horizontal)
        from PySide6.QtCore import Qt
        self._vol_slider.setOrientation(Qt.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(100)
        self._vol_slider.setFixedWidth(100)
        self._vol_slider.valueChanged.connect(self._on_volume_change)
        layout.addWidget(self._vol_slider)

        self._vol_pct = QLabel("100%")
        self._vol_pct.setFixedWidth(35)
        self._vol_pct.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._vol_pct)

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        if self._muted:
            self._mute_btn.setText("Muted")
            self._mute_btn.setStyleSheet("padding: 4px; background-color: #e74c3c; color: white;")
        else:
            self._mute_btn.setText("Mic On")
            self._mute_btn.setStyleSheet("padding: 4px; background-color: #2ecc71; color: white;")
        self.mute_toggled.emit(self._muted)

    def _on_volume_change(self, value: int) -> None:
        self._vol_pct.setText(f"{value}%")
        self.volume_changed.emit(value / 100.0)

    def set_mute(self, muted: bool) -> None:
        if muted != self._muted:
            self._toggle_mute()

    def set_volume(self, volume: float) -> None:
        self._vol_slider.setValue(int(volume * 100))
