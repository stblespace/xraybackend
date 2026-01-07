import asyncio
import logging
from typing import Dict


class ConnectionLimiter:
    """
    Optional connection limiter to help detect or block account sharing.
    """

    def __init__(self, max_connections: int, log_only: bool = False) -> None:
        self.max_connections = max(0, max_connections)
        self.log_only = log_only
        self.enabled = self.max_connections > 0
        self._active: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger(__name__)

    async def start_session(self, uuid: str) -> bool:
        """
        Register a new session. Returns False if the limit is enforced and exceeded.
        """

        if not self.enabled:
            return True

        async with self._lock:
            current = self._active.get(uuid, 0)
            if current >= self.max_connections:
                self._logger.warning(
                    "connection_limit_exceeded", extra={"uuid": uuid, "active": current}
                )
                return self.log_only

            self._active[uuid] = current + 1
            return True

    async def end_session(self, uuid: str) -> None:
        """
        Mark a session as finished to free capacity.
        """

        if not self.enabled:
            return

        async with self._lock:
            current = self._active.get(uuid, 0)
            if current <= 1:
                self._active.pop(uuid, None)
            else:
                self._active[uuid] = current - 1

    async def mark_suspicious(self, uuid: str) -> None:
        """
        Explicitly record suspicious activity without changing counters.
        """

        self._logger.warning("suspicious_activity", extra={"uuid": uuid})

    async def active_connections(self, uuid: str) -> int:
        async with self._lock:
            return self._active.get(uuid, 0)
