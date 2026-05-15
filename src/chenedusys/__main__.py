"""Entry point for ``python -m chenedusys``."""

from __future__ import annotations

import sys

from chenedusys.app import create_app
from chenedusys.ui.windows.login import LoginWindow


def main() -> int:
    app, bus = create_app()
    window = LoginWindow(bus)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
