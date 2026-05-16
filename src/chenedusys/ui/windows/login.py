"""Login / Registration window."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chenedusys.core.event_bus import EventBus
from chenedusys.services.auth import AuthService, AuthError


class LoginWindow(QWidget):
    """Login and registration form."""

    login_success = Signal(dict)  # emits user dict

    def __init__(self, bus: EventBus, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bus = bus
        self.auth = auth_service
        self.setWindowTitle("ChenEduSys — Login")
        self.resize(360, 320)

        layout = QVBoxLayout(self)

        title = QLabel("ChenEduSys")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        self._username = QLineEdit()
        self._username.setPlaceholderText("Username")
        layout.addWidget(self._username)

        self._password = QLineEdit()
        self._password.setPlaceholderText("Password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._password)

        self._role = QComboBox()
        self._role.addItems(["student", "teacher"])
        layout.addWidget(QLabel("Role (for registration):"))
        layout.addWidget(self._role)

        self._login_btn = QPushButton("Login")
        self._login_btn.clicked.connect(self._on_login)
        layout.addWidget(self._login_btn)

        self._register_btn = QPushButton("Register")
        self._register_btn.clicked.connect(self._on_register)
        layout.addWidget(self._register_btn)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: red; font-size: 12px;")
        layout.addWidget(self._status)

    def _on_login(self) -> None:
        username = self._username.text().strip()
        password = self._password.text()
        if not username or not password:
            self._status.setText("Enter username and password")
            return
        self._status.setText("Logging in...")
        self._login_btn.setEnabled(False)
        asyncio.get_event_loop().create_task(self._do_login(username, password))

    def _on_register(self) -> None:
        username = self._username.text().strip()
        password = self._password.text()
        role = self._role.currentText()
        if not username or not password:
            self._status.setText("Enter username and password")
            return
        if len(password) < 8:
            self._status.setText("Password must be at least 8 characters")
            return
        self._status.setText("Registering...")
        self._register_btn.setEnabled(False)
        asyncio.get_event_loop().create_task(self._do_register(username, password, role))

    async def _do_login(self, username: str, password: str) -> None:
        try:
            user = await self.auth.login(username, password)
            self._status.setText("")
            self.login_success.emit(user)
        except AuthError as e:
            self._status.setText(str(e))
        finally:
            self._login_btn.setEnabled(True)

    async def _do_register(self, username: str, password: str, role: str) -> None:
        try:
            await self.auth.register(username, password, role)
            self._status.setText("Registered! Now login.")
        except AuthError as e:
            self._status.setText(str(e))
        finally:
            self._register_btn.setEnabled(True)
