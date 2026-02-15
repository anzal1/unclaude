"""Request-merge layer for heartbeat.

HeartbeatWake collects incoming heartbeat requests, deduplicates
them within a merge window, and batches them for the runner.

Inspired by OpenClaw's HeartbeatWake which:
- Merges duplicate requests arriving within 250ms
- Prioritizes by urgency
- Handles rate limiting per source
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class HeartbeatRequest:
    """A request to wake the heartbeat."""
    source: str          # Who requested the wake (tool, timer, event)
    task_type: str       # Type of task to run
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 0    # Higher = more urgent
    timestamp: float = field(default_factory=time.time)
    dedupe_key: str = ""  # Requests with same key get merged

    def __post_init__(self):
        if not self.dedupe_key:
            self.dedupe_key = f"{self.source}:{self.task_type}"


class HeartbeatWake:
    """Request-merge layer for heartbeat system.

    Collects heartbeat requests, deduplicates within a merge window,
    and dispatches to the runner.

    Usage:
        wake = HeartbeatWake(merge_window_ms=250)
        wake.request(HeartbeatRequest(source="timer", task_type="check_status"))
        # Requests are batched and merged before dispatch
    """

    def __init__(
        self,
        merge_window_ms: int = 250,
        max_queue_size: int = 100,
        rate_limit_per_source: int = 10,
        rate_limit_window_s: float = 60.0,
    ):
        self.merge_window_ms = merge_window_ms
        self.max_queue_size = max_queue_size
        self.rate_limit_per_source = rate_limit_per_source
        self.rate_limit_window_s = rate_limit_window_s

        self._pending: dict[str, HeartbeatRequest] = {}
        self._dispatch_callback: Callable | None = None
        self._merge_task: asyncio.Task | None = None
        self._running = False

        # Rate limiting: source → list of timestamps
        self._rate_tracker: dict[str, list[float]] = {}

    def set_dispatch_callback(self, callback: Callable) -> None:
        """Set the callback for dispatching merged requests."""
        self._dispatch_callback = callback

    async def start(self) -> None:
        """Start the merge loop."""
        self._running = True
        self._merge_task = asyncio.create_task(self._merge_loop())

    async def stop(self) -> None:
        """Stop the merge loop."""
        self._running = False
        if self._merge_task and not self._merge_task.done():
            self._merge_task.cancel()
            try:
                await self._merge_task
            except asyncio.CancelledError:
                pass

    def request(self, req: HeartbeatRequest) -> bool:
        """Submit a heartbeat request.

        Returns True if accepted, False if rate-limited or queue full.
        """
        # Check rate limit
        if not self._check_rate_limit(req.source):
            return False

        # Check queue size
        if len(self._pending) >= self.max_queue_size:
            return False

        # Merge: keep highest priority version
        existing = self._pending.get(req.dedupe_key)
        if existing is None or req.priority > existing.priority:
            self._pending[req.dedupe_key] = req

        return True

    def _check_rate_limit(self, source: str) -> bool:
        """Check if a source is within its rate limit."""
        now = time.time()
        if source not in self._rate_tracker:
            self._rate_tracker[source] = []

        # Clean old entries
        cutoff = now - self.rate_limit_window_s
        self._rate_tracker[source] = [
            t for t in self._rate_tracker[source] if t > cutoff
        ]

        # Check limit
        if len(self._rate_tracker[source]) >= self.rate_limit_per_source:
            return False

        self._rate_tracker[source].append(now)
        return True

    async def _merge_loop(self) -> None:
        """Main merge loop - flushes pending requests after merge window."""
        while self._running:
            await asyncio.sleep(self.merge_window_ms / 1000.0)

            if not self._pending:
                continue

            # Snapshot and clear
            batch = dict(self._pending)
            self._pending.clear()

            # Sort by priority (descending)
            sorted_requests = sorted(
                batch.values(),
                key=lambda r: r.priority,
                reverse=True,
            )

            # Dispatch
            if self._dispatch_callback:
                try:
                    await self._dispatch_callback(sorted_requests)
                except Exception:
                    pass  # Don't let dispatch errors crash the loop

    @property
    def pending_count(self) -> int:
        """Number of pending requests."""
        return len(self._pending)
