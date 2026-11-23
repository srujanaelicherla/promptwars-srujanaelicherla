"""Mutable user profiles. Roles are stored here, never taken from the client."""

from __future__ import annotations

from threading import Lock

from app.models import User


class UserStore:
    def __init__(self, initial: list[User]) -> None:
        self._lock = Lock()
        self._users = {item.id: item for item in initial}

    def get(self, user_id: str) -> User | None:
        with self._lock:
            return self._users.get(user_id)

    def upsert(self, user: User) -> None:
        with self._lock:
            self._users[user.id] = user

    def snapshot(self) -> list[User]:
        with self._lock:
            return list(self._users.values())
