"""Dashboard window — list meetings, create, join."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chenedusys.core.event_bus import EventBus
from chenedusys.services.auth import AuthService


class DashboardWindow(QWidget):
    """Shows active meetings and lets teacher create / student join."""

    logout_clicked = Signal()
    meeting_joined = Signal(str)  # emits meeting_id

    def __init__(
        self,
        bus: EventBus,
        auth: AuthService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.bus = bus
        self.auth = auth
        self.setWindowTitle("ChenEduSys — Dashboard")
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        self._user_label = QLabel()
        self._user_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self._user_label)
        header.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)

        logout_btn = QPushButton("Logout")
        logout_btn.clicked.connect(self.logout_clicked.emit)
        header.addWidget(logout_btn)
        layout.addLayout(header)

        # Create meeting (teacher only)
        self._create_bar = QHBoxLayout()
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("Meeting title")
        self._create_bar.addWidget(self._title_input)
        self._create_btn = QPushButton("Create Meeting")
        self._create_btn.clicked.connect(self._on_create)
        self._create_bar.addWidget(self._create_btn)
        layout.addLayout(self._create_bar)

        # Meeting list
        self._list = QListWidget()
        layout.addWidget(self._list)

        self._join_btn = QPushButton("Join Selected Meeting")
        self._join_btn.clicked.connect(self._on_join)
        layout.addWidget(self._join_btn)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self._status)

        self._meetings: list[dict] = []

    def set_user(self, user: dict) -> None:
        self._user_label.setText(f"{user['username']} ({user['role']})")
        is_teacher = user.get("role") == "teacher"
        self._create_bar.setVisible(is_teacher)
        self._refresh()

    def _refresh(self) -> None:
        asyncio.get_event_loop().create_task(self._do_list())

    async def _do_list(self) -> None:
        import aiohttp
        token = self.auth.token
        if not token:
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.auth._hub_url}/meetings",
                    headers={"Authorization": f"Bearer {token}"},
                ) as resp:
                    if resp.status == 200:
                        self._meetings = await resp.json()
                        self._update_list()
        except Exception as e:
            self._status.setText(f"Error: {e}")

    def _update_list(self) -> None:
        self._list.clear()
        for m in self._meetings:
            title = m.get("title") or m["id"]
            text = f"{title}  —  teacher: {m['teacher_id'][:8]}  status: {m['status']}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, m["id"])
            self._list.addItem(item)

    def _on_create(self) -> None:
        asyncio.get_event_loop().create_task(self._do_create())

    async def _do_create(self) -> None:
        import aiohttp
        token = self.auth.token
        if not token:
            return
        title = self._title_input.text().strip()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.auth._hub_url}/meetings",
                    json={"title": title},
                    headers={"Authorization": f"Bearer {token}"},
                ) as resp:
                    if resp.status == 201:
                        self._title_input.clear()
                        await self._do_list()
                    else:
                        body = await resp.json()
                        self._status.setText(body.get("reason", "Create failed"))
        except Exception as e:
            self._status.setText(f"Error: {e}")

    def _on_join(self) -> None:
        item = self._list.currentItem()
        if item is None:
            self._status.setText("Select a meeting first")
            return
        meeting_id = item.data(Qt.ItemDataRole.UserRole)
        asyncio.get_event_loop().create_task(self._do_join(meeting_id))

    async def _do_join(self, meeting_id: str) -> None:
        import aiohttp
        token = self.auth.token
        if not token:
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.auth._hub_url}/meetings/{meeting_id}/join",
                    headers={"Authorization": f"Bearer {token}"},
                ) as resp:
                    if resp.status == 200:
                        self.meeting_joined.emit(meeting_id)
                    else:
                        body = await resp.json()
                        self._status.setText(body.get("reason", "Join failed"))
        except Exception as e:
            self._status.setText(f"Error: {e}")
