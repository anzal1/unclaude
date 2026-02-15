"""Token usage tracking and budget management.

This module provides persistent token usage tracking, cost estimation,
and budget enforcement. Users screamed for this feature across every
platform — it's the #1 pain point after multi-agent setup.

Features:
- Per-request token logging with model/provider/cost
- Session and daily/weekly/monthly aggregation
- Budget limits with soft/hard thresholds
- Cost estimation using LiteLLM's pricing data
- CLI and web API access to usage data
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class BudgetPeriod(str, Enum):
    """Budget period for cost limits."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TOTAL = "total"


class BudgetAction(str, Enum):
    """What to do when budget is exceeded."""
    WARN = "warn"           # Print warning, continue
    DOWNGRADE = "downgrade"  # Switch to cheaper model
    BLOCK = "block"         # Refuse to make the call


@dataclass
class UsageRecord:
    """A single LLM call usage record."""
    timestamp: float
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    session_id: str | None = None
    task_id: str | None = None
    request_type: str = "chat"  # chat, stream, daemon

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "request_type": self.request_type,
        }


@dataclass
class UsageSummary:
    """Aggregated usage summary."""
    period: str
    start_time: float
    end_time: float
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    models_used: dict[str, int] = field(default_factory=dict)
    providers_used: dict[str, int] = field(default_factory=dict)
    avg_tokens_per_request: float = 0.0
    avg_cost_per_request: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_date": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_date": datetime.fromtimestamp(self.end_time).isoformat(),
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "models_used": self.models_used,
            "providers_used": self.providers_used,
            "avg_tokens_per_request": round(self.avg_tokens_per_request, 1),
            "avg_cost_per_request": round(self.avg_cost_per_request, 6),
        }


@dataclass
class BudgetConfig:
    """Budget configuration."""
    period: BudgetPeriod = BudgetPeriod.DAILY
    limit_usd: float = 5.0
    soft_limit_pct: float = 0.8  # Warn at 80%
    action: BudgetAction = BudgetAction.WARN


# Known model pricing (cost per 1K tokens)
# Updated as of early 2026
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Gemini
    "gemini/gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    "gemini/gemini-2.5-flash": {"input": 0.00015, "output": 0.00035},
    "gemini/gemini-2.5-pro": {"input": 0.00125, "output": 0.005},
    # OpenAI
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "o3": {"input": 0.01, "output": 0.04},
    "o3-mini": {"input": 0.0011, "output": 0.0044},
    # Anthropic
    "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
    # DeepSeek
    "deepseek/deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek/deepseek-reasoner": {"input": 0.00055, "output": 0.00219},
    # Local/free
    "ollama/llama3.1": {"input": 0.0, "output": 0.0},
    "ollama/codellama": {"input": 0.0, "output": 0.0},
    "ollama/deepseek-coder-v2": {"input": 0.0, "output": 0.0},
}


class UsageTracker:
    """Persistent token usage tracker backed by SQLite.

    Provides:
    - Per-call logging with full metadata
    - Fast aggregation queries (daily/weekly/monthly/all-time)
    - Budget enforcement with configurable limits
    - Model-level cost breakdowns
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (Path.home() / ".unclaude" / "usage.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._budget: BudgetConfig | None = None

    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0.0,
                    session_id TEXT,
                    task_id TEXT,
                    request_type TEXT DEFAULT 'chat'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_timestamp
                ON usage(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_model
                ON usage(model)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_session
                ON usage(session_id)
            """)
            # Budget config table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budget_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    period TEXT NOT NULL DEFAULT 'daily',
                    limit_usd REAL NOT NULL DEFAULT 5.0,
                    soft_limit_pct REAL NOT NULL DEFAULT 0.8,
                    action TEXT NOT NULL DEFAULT 'warn'
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def record(
        self,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: float | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        request_type: str = "chat",
    ) -> UsageRecord:
        """Record a single LLM call's usage.

        Args:
            model: Model identifier (e.g., "gemini/gemini-2.0-flash")
            provider: Provider name (e.g., "gemini")
            prompt_tokens: Input tokens used
            completion_tokens: Output tokens generated
            total_tokens: Total tokens (input + output)
            cost_usd: Cost in USD. If None, estimated from model pricing.
            session_id: Optional session/conversation ID
            task_id: Optional daemon task ID
            request_type: Type of request (chat/stream/daemon)

        Returns:
            The recorded UsageRecord
        """
        if cost_usd is None:
            cost_usd = self.estimate_cost(
                model, prompt_tokens, completion_tokens)

        record = UsageRecord(
            timestamp=time.time(),
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            session_id=session_id,
            task_id=task_id,
            request_type=request_type,
        )

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """INSERT INTO usage
                   (timestamp, model, provider, prompt_tokens, completion_tokens,
                    total_tokens, cost_usd, session_id, task_id, request_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.timestamp, record.model, record.provider,
                    record.prompt_tokens, record.completion_tokens,
                    record.total_tokens, record.cost_usd,
                    record.session_id, record.task_id, record.request_type,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return record

    @staticmethod
    def estimate_cost(
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Estimate cost for a model call using known pricing."""
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            # Try partial match
            for key, prices in MODEL_PRICING.items():
                if key in model or model in key:
                    pricing = prices
                    break

        if not pricing:
            # Unknown model — estimate conservatively
            # ~$2/1M tokens
            return (prompt_tokens + completion_tokens) * 0.000002

        input_cost = (prompt_tokens / 1000) * pricing["input"]
        output_cost = (completion_tokens / 1000) * pricing["output"]
        return input_cost + output_cost

    def get_summary(
        self,
        period: str = "today",
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> UsageSummary:
        """Get aggregated usage summary for a time period.

        Args:
            period: One of "today", "yesterday", "week", "month", "all",
                    or "custom" (requires start_time/end_time).
        """
        now = time.time()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()

        if period == "today":
            start_time = today_start
            end_time = now
        elif period == "yesterday":
            start_time = today_start - 86400
            end_time = today_start
        elif period == "week":
            start_time = today_start - (7 * 86400)
            end_time = now
        elif period == "month":
            start_time = today_start - (30 * 86400)
            end_time = now
        elif period == "all":
            start_time = 0
            end_time = now
        elif period == "custom":
            if start_time is None or end_time is None:
                raise ValueError(
                    "Custom period requires start_time and end_time")
        else:
            start_time = start_time or 0
            end_time = end_time or now

        conn = sqlite3.connect(str(self.db_path))
        try:
            # Aggregate stats
            row = conn.execute(
                """SELECT
                    COUNT(*) as total_requests,
                    COALESCE(SUM(prompt_tokens), 0) as total_prompt,
                    COALESCE(SUM(completion_tokens), 0) as total_completion,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(cost_usd), 0.0) as total_cost
                FROM usage
                WHERE timestamp >= ? AND timestamp <= ?""",
                (start_time, end_time),
            ).fetchone()

            total_requests = row[0]
            total_prompt = row[1]
            total_completion = row[2]
            total_tokens = row[3]
            total_cost = row[4]

            # Model breakdown
            models = {}
            for mrow in conn.execute(
                """SELECT model, COUNT(*) as cnt
                FROM usage
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY model ORDER BY cnt DESC""",
                (start_time, end_time),
            ).fetchall():
                models[mrow[0]] = mrow[1]

            # Provider breakdown
            providers = {}
            for prow in conn.execute(
                """SELECT provider, COUNT(*) as cnt
                FROM usage
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY provider ORDER BY cnt DESC""",
                (start_time, end_time),
            ).fetchall():
                providers[prow[0]] = prow[1]

        finally:
            conn.close()

        return UsageSummary(
            period=period,
            start_time=start_time,
            end_time=end_time,
            total_requests=total_requests,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            models_used=models,
            providers_used=providers,
            avg_tokens_per_request=(
                total_tokens / total_requests if total_requests > 0 else 0
            ),
            avg_cost_per_request=(
                total_cost / total_requests if total_requests > 0 else 0
            ),
        )

    def get_daily_breakdown(self, days: int = 7) -> list[dict[str, Any]]:
        """Get day-by-day usage breakdown for the last N days."""
        results = []
        now = datetime.now()

        for i in range(days):
            day = now - timedelta(days=i)
            day_start = day.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).timestamp()
            day_end = day_start + 86400

            summary = self.get_summary(
                period="custom",
                start_time=day_start,
                end_time=min(day_end, time.time()),
            )
            results.append({
                "date": day.strftime("%Y-%m-%d"),
                "requests": summary.total_requests,
                "tokens": summary.total_tokens,
                "cost_usd": round(summary.total_cost_usd, 6),
                "models": summary.models_used,
            })

        return results

    def get_model_breakdown(
        self,
        period: str = "all",
    ) -> list[dict[str, Any]]:
        """Get per-model usage breakdown."""
        now = time.time()
        today_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()

        if period == "today":
            start_time = today_start
        elif period == "week":
            start_time = today_start - (7 * 86400)
        elif period == "month":
            start_time = today_start - (30 * 86400)
        else:
            start_time = 0

        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute(
                """SELECT
                    model, provider,
                    COUNT(*) as requests,
                    SUM(prompt_tokens) as prompt,
                    SUM(completion_tokens) as completion,
                    SUM(total_tokens) as tokens,
                    SUM(cost_usd) as cost
                FROM usage
                WHERE timestamp >= ?
                GROUP BY model, provider
                ORDER BY cost DESC""",
                (start_time,),
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "model": row[0],
                "provider": row[1],
                "requests": row[2],
                "prompt_tokens": row[3],
                "completion_tokens": row[4],
                "total_tokens": row[5],
                "cost_usd": round(row[6], 6),
            }
            for row in rows
        ]

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent usage records."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute(
                """SELECT timestamp, model, provider, prompt_tokens,
                       completion_tokens, total_tokens, cost_usd,
                       session_id, task_id, request_type
                FROM usage ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "timestamp": row[0],
                "datetime": datetime.fromtimestamp(row[0]).strftime("%Y-%m-%d %H:%M:%S"),
                "model": row[1],
                "provider": row[2],
                "prompt_tokens": row[3],
                "completion_tokens": row[4],
                "total_tokens": row[5],
                "cost_usd": round(row[6], 6),
                "session_id": row[7],
                "task_id": row[8],
                "request_type": row[9],
            }
            for row in rows
        ]

    # ─── Budget Management ────────────────────────────────────────

    def set_budget(
        self,
        limit_usd: float,
        period: BudgetPeriod = BudgetPeriod.DAILY,
        action: BudgetAction = BudgetAction.WARN,
        soft_limit_pct: float = 0.8,
    ) -> None:
        """Set a usage budget."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """INSERT OR REPLACE INTO budget_config
                   (id, period, limit_usd, soft_limit_pct, action)
                   VALUES (1, ?, ?, ?, ?)""",
                (period.value, limit_usd, soft_limit_pct, action.value),
            )
            conn.commit()
        finally:
            conn.close()

        self._budget = BudgetConfig(
            period=period,
            limit_usd=limit_usd,
            soft_limit_pct=soft_limit_pct,
            action=action,
        )

    def get_budget(self) -> BudgetConfig | None:
        """Get current budget configuration."""
        if self._budget:
            return self._budget

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT period, limit_usd, soft_limit_pct, action FROM budget_config WHERE id = 1"
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return None

        self._budget = BudgetConfig(
            period=BudgetPeriod(row[0]),
            limit_usd=row[1],
            soft_limit_pct=row[2],
            action=BudgetAction(row[3]),
        )
        return self._budget

    def check_budget(self) -> dict[str, Any]:
        """Check current spend against budget.

        Returns:
            Dict with:
            - within_budget: bool
            - soft_warning: bool
            - current_spend: float
            - limit: float
            - remaining: float
            - percentage: float
            - action: str (if over budget)
        """
        budget = self.get_budget()
        if not budget:
            return {
                "within_budget": True,
                "soft_warning": False,
                "budget_set": False,
            }

        # Determine the time window
        if budget.period == BudgetPeriod.DAILY:
            period = "today"
        elif budget.period == BudgetPeriod.WEEKLY:
            period = "week"
        elif budget.period == BudgetPeriod.MONTHLY:
            period = "month"
        else:
            period = "all"

        summary = self.get_summary(period=period)
        current_spend = summary.total_cost_usd
        remaining = max(0, budget.limit_usd - current_spend)
        percentage = (current_spend / budget.limit_usd *
                      100) if budget.limit_usd > 0 else 0

        result = {
            "budget_set": True,
            "within_budget": current_spend < budget.limit_usd,
            "soft_warning": percentage >= (budget.soft_limit_pct * 100),
            "current_spend": round(current_spend, 6),
            "limit": budget.limit_usd,
            "remaining": round(remaining, 6),
            "percentage": round(percentage, 1),
            "period": budget.period.value,
        }

        if not result["within_budget"]:
            result["action"] = budget.action.value

        return result

    def clear_budget(self) -> None:
        """Remove budget configuration."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM budget_config")
            conn.commit()
        finally:
            conn.close()
        self._budget = None

    def export_csv(self, filepath: Path | None = None) -> str:
        """Export usage data to CSV. Returns the file path."""
        if filepath is None:
            filepath = Path.home() / ".unclaude" / "usage_export.csv"

        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute(
                """SELECT timestamp, model, provider, prompt_tokens,
                       completion_tokens, total_tokens, cost_usd,
                       session_id, task_id, request_type
                FROM usage ORDER BY timestamp"""
            ).fetchall()
        finally:
            conn.close()

        headers = [
            "timestamp", "datetime", "model", "provider",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "cost_usd", "session_id", "task_id", "request_type",
        ]

        lines = [",".join(headers)]
        for row in rows:
            dt = datetime.fromtimestamp(row[0]).isoformat()
            values = [str(row[0]), dt] + \
                [str(v) if v is not None else "" for v in row[1:]]
            lines.append(",".join(values))

        filepath.write_text("\n".join(lines))
        return str(filepath)


# ─── Global instance ──────────────────────────────────────────────

_tracker: UsageTracker | None = None


def get_usage_tracker() -> UsageTracker:
    """Get the global usage tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
