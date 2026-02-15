"""Usage tracking API routes for the web dashboard."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class BudgetRequest(BaseModel):
    """Request to set a usage budget."""
    limit_usd: float
    period: str = "daily"  # daily, weekly, monthly, total
    action: str = "warn"   # warn, downgrade, block
    soft_limit_pct: float = 0.8


@router.get("/usage/summary")
async def usage_summary(period: str = Query("today", description="today|yesterday|week|month|all")):
    """Get aggregated usage summary for a time period."""
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    summary = tracker.get_summary(period=period)
    return summary.to_dict()


@router.get("/usage/daily")
async def usage_daily(days: int = Query(7, ge=1, le=90)):
    """Get day-by-day usage breakdown."""
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    return {"days": tracker.get_daily_breakdown(days=days)}


@router.get("/usage/models")
async def usage_by_model(period: str = Query("all", description="today|week|month|all")):
    """Get per-model usage breakdown."""
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    return {"models": tracker.get_model_breakdown(period=period)}


@router.get("/usage/recent")
async def usage_recent(limit: int = Query(20, ge=1, le=200)):
    """Get recent usage records."""
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    return {"records": tracker.get_recent(limit=limit)}


@router.get("/usage/budget")
async def get_budget():
    """Get current budget status."""
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    return tracker.check_budget()


@router.post("/usage/budget")
async def set_budget(req: BudgetRequest):
    """Set a usage budget."""
    from unclaude.usage import get_usage_tracker, BudgetPeriod, BudgetAction

    try:
        period = BudgetPeriod(req.period)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid period: {req.period}")

    try:
        action = BudgetAction(req.action)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid action: {req.action}")

    tracker = get_usage_tracker()
    tracker.set_budget(
        limit_usd=req.limit_usd,
        period=period,
        action=action,
        soft_limit_pct=req.soft_limit_pct,
    )
    return {"status": "ok", "budget": tracker.check_budget()}


@router.delete("/usage/budget")
async def clear_budget():
    """Remove usage budget."""
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    tracker.clear_budget()
    return {"status": "ok"}


@router.get("/usage/export")
async def export_usage():
    """Export all usage data as CSV."""
    from fastapi.responses import FileResponse
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    filepath = tracker.export_csv()
    return FileResponse(
        filepath,
        media_type="text/csv",
        filename="unclaude_usage.csv",
    )
