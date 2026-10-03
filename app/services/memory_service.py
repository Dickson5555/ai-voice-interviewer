import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List


class SessionMemory:
    """Thread-safe, bounded, per-session message store."""

    def __init__(self, max_turns: int = 40):
        # max_turns = total messages kept per session (user + AI)
        self._max_turns = max_turns
        self._memory: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self._max_turns))
        self._lock = threading.Lock()
        self._created: Dict[str, datetime] = {}

    def get_history(self, session_id: str) -> List[str]:
        with self._lock:
            return list(self._memory.get(session_id, []))

    def add_message(self, session_id: str, role: str, message: str) -> None:
        with self._lock:
            if session_id not in self._created:
                self._created[session_id] = datetime.utcnow()
            self._memory[session_id].append(f"{role}: {message}")

    def clear_session(self, session_id: str) -> None:
        """Remove all memory for a session. Call on disconnect / end."""
        with self._lock:
            self._memory.pop(session_id, None)
            self._created.pop(session_id, None)

    def active_sessions(self) -> int:
        with self._lock:
            return len(self._memory)


# Module-level singleton (same as before, so imports don't change).
memory_store = SessionMemory()