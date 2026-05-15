"""Screen overlay paint demo — draw over anything on screen.

Run with:  python demo_paint.py

The canvas is a transparent full-screen window. You can see your desktop
and any app behind it. Strokes float above everything.

Controls:
  - Hold Ctrl + move touchpad/mouse  = draw
  - Hold Shift + move touchpad/mouse = erase
  - 2-finger touchpad                = pan canvas
  - Click "Clear"                    = wipe strokes
  - ESC                              = quit
"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chenedusys.core.event_bus import EventBus
from chenedusys.services.paint_engine import PaintEngine
from chenedusys.ui.widgets.paint_canvas import PaintCanvas


def main():
    app = QApplication(sys.argv)
    bus = EventBus()
    engine = PaintEngine(bus)

    window_flags = (
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    window = QWidget(None, window_flags)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    window.setWindowTitle("ChenEduSys Paint Overlay")

    # Auto-detect screen size
    screen = app.primaryScreen()
    if screen:
        geo = screen.geometry()
        window.setGeometry(geo)

    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 60)
    layout.setSpacing(0)

    # --- Transparent paint canvas fills entire screen ---
    canvas = PaintCanvas(engine, bus)
    layout.addWidget(canvas, stretch=1)

    # --- Compact toolbar at the bottom ---
    toolbar = QWidget()
    toolbar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    toolbar.setFixedHeight(36)
    toolbar.setStyleSheet("background-color: rgba(30, 30, 30, 220);")
    toolbar_layout = QHBoxLayout(toolbar)
    toolbar_layout.setContentsMargins(8, 2, 8, 2)
    toolbar_layout.setSpacing(8)

    btn_style = (
        "QPushButton { background: #555; color: #ddd; border: none;"
        "padding: 4px 12px; border-radius: 3px; font-size: 12px; }"
        "QPushButton:hover { background: #777; }"
    )

    def do_clear():
        engine.clear()
        canvas.update()

    def do_stop():
        engine.stop()
        canvas.update()

    def do_quit():
        app.quit()

    clear_btn = QPushButton("Clear")
    clear_btn.setStyleSheet(btn_style)
    clear_btn.clicked.connect(do_clear)
    toolbar_layout.addWidget(clear_btn)

    stop_btn = QPushButton("Stop")
    stop_style = btn_style.replace("#555", "#c0392b").replace("#777", "#e74c3c")
    stop_btn.setStyleSheet(stop_style)
    stop_btn.clicked.connect(do_stop)
    toolbar_layout.addWidget(stop_btn)

    quit_btn = QPushButton("Quit (ESC)")
    quit_btn.setStyleSheet(btn_style)
    quit_btn.clicked.connect(do_quit)
    toolbar_layout.addWidget(quit_btn)

    toolbar_layout.addStretch()

    layout.addWidget(toolbar)

    # ESC shortcut to quit — override window keyPressEvent since
    # QShortcut doesn't work reliably with Tool window type
    original_key_press = window.keyPressEvent

    def _on_key_press(event):
        if event.key() == Qt.Key.Key_Escape:
            do_quit()
        else:
            original_key_press(event)

    window.keyPressEvent = _on_key_press  # type: ignore[assignment]

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
