"""Client-side authentication service.

Handles registration, login, token storage (OS keyring), and
publishes auth events on the EventBus.
"""

from __future__ import annotations

import logging

import aiohttp
import keyring

from chenedusys.core.event_bus import EventBus
from chenedusys.core.events import LoginFail, LoginSuccess, Logout

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "chenedusys"
_KEYRING_TOKEN_KEY = "auth_token"
_KEYRING_USERNAME_KEY = "username"


class AuthService:
    """Manages authentication against the hub server."""

    def __init__(self, bus: EventBus, hub_url: str = "http://localhost:8443") -> None:
        self._bus = bus
        self._hub_url = hub_url.rstrip("/")
        self._token: str | None = None
        self._user_id: str | None = None
        self._username: str | None = None
        self._role: str | None = None

    @property
    def token(self) -> str | None:
        if self._token is None:
            self._token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
        return self._token

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @property
    def username(self) -> str | None:
        if self._username is None:
            self._username = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME_KEY)
        return self._username

    @property
    def role(self) -> str | None:
        return self._role

    @property
    def is_logged_in(self) -> bool:
        return self._token is not None

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    async def register(self, username: str, password: str, role: str = "student") -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._hub_url}/register",
                json={"username": username, "password": password, "role": role},
            ) as resp:
                body = await resp.json()
                if resp.status != 201:
                    raise AuthError(body.get("reason", f"Registration failed ({resp.status})"))
                return body

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, username: str, password: str) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._hub_url}/login",
                json={"username": username, "password": password},
            ) as resp:
                body = await resp.json()
                if resp.status != 200:
                    self._bus.publish(LoginFail(reason=body.get("reason", "Login failed")))
                    raise AuthError(body.get("reason", f"Login failed ({resp.status})"))

                self._token = body["token"]
                user = body["user"]
                self._user_id = user["id"]
                self._username = user["username"]
                self._role = user["role"]

                # Store in OS keyring
                keyring.set_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY, self._token)
                keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME_KEY, self._username)

                self._bus.publish(LoginSuccess(
                    username=self._username,
                    user_id=self._user_id,
                    token=self._token,
                ))
                return user

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        uid = self._user_id
        self._token = None
        self._user_id = None
        self._username = None
        self._role = None
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME_KEY)
        except keyring.errors.PasswordDeleteError:
            pass
        if uid:
            self._bus.publish(Logout(user_id=uid))

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    async def validate_token(self) -> bool:
        if not self.token:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._hub_url}/me",
                    headers={"Authorization": f"Bearer {self.token}"},
                ) as resp:
                    if resp.status == 200:
                        user = await resp.json()
                        self._user_id = user["id"]
                        self._username = user["username"]
                        self._role = user["role"]
                        return True
                    return False
        except Exception:
            return False


class AuthError(Exception):
    """Raised on authentication failure."""
