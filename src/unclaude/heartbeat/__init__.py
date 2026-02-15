"""Heartbeat system for proactive agent behavior.

Exports:
    HeartbeatManager - Main heartbeat coordinator
    HeartbeatTask - A scheduled proactive task
    HeartbeatWake - Request-merge layer
"""

from .manager import HeartbeatManager, HeartbeatTask
from .wake import HeartbeatWake

__all__ = [
    "HeartbeatManager",
    "HeartbeatTask",
    "HeartbeatWake",
]
