import csv
import io
from datetime import date, datetime, timezone
from calendar import monthrange
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.database import expenses_collection
from app.models import (
    CategoryTotal,
    MonthlyReport,
    MonthTotal,
    SummaryReport,
    TopExpense,
    paise_to_rupees,
)
from app.security import get_current_user
from app.routers.expenses import _date_to_datetime

router = APIRouter(tags=["reports"])


def _current_month_range() -> tuple[date, date]:
    today = date.today()
    last_day = monthrange(today.year, today.month)[1]
    return date(today.year, today.month, 1), date(today.year, today.month, last_day)


@router.get("/reports/summary", response_model=SummaryReport)
async def summary_report(
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
    current_user: dict = Depends(get_current_user),
):
    month_start, month_end = _current_month_range()
    if date_from is None:
        date_from = month_start
    if date_to is None:
        date_to = month_end

    is_current_month = (date_from == month_start and date_to == month_end)

    match_stage = {
        "user_id": current_user["_id"],
        "date": {"$gte": _date_to_datetime(date_from), "$lte": _date_to_datetime(date_to)},
    }

    pipeline = [
        {"$match": match_stage},
        {
            "$facet": {
                "by_category": [
                    {
                        "$group": {
                            "_id": "$category",
                            "total_paise": {"$sum": "$amount_paise"},
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"total_paise": -1}},
                ],
                "overall": [
                    {
                        "$group": {
                            "_id": None,
                            "total_paise": {"$sum": "$amount_paise"},
                            "count": {"$sum": 1},
                        }
                    }
                ],
            }
        },
    ]

    result = await expenses_collection.aggregate(pipeline).to_list(length=1)
    facet = result[0] if result else {"by_category": [], "overall": []}

    overall_list = facet.get("overall", [])
    overall_total_paise = overall_list[0]["total_paise"] if overall_list else 0

    categories: list[CategoryTotal] = []
    for row in facet.get("by_category", []):
        pct = (row["total_paise"] / overall_total_paise * 100) if overall_total_paise else 0.0
        categories.append(
            CategoryTotal(
                category=row["_id"],
                total=paise_to_rupees(row["total_paise"]),
                percentage=round(pct, 2),
                count=row["count"],
            )
        )

    budget = None
    remaining = None
    over_budget = None
    if is_current_month and current_user.get("monthly_budget") is not None:
        budget = current_user["monthly_budget"]
        spent = paise_to_rupees(overall_total_paise)
        remaining = round(budget - spent, 2)
        over_budget = remaining < 0

    return SummaryReport(
        from_date=date_from,
        to_date=date_to,
        total_spent=paise_to_rupees(overall_total_paise),
        categories=categories,
        budget=budget,
        remaining=remaining,
        over_budget=over_budget,
    )


@router.get("/reports/monthly", response_model=MonthlyReport)
async def monthly_report(
    year: int = Query(..., ge=1970, le=2100),
    current_user: dict = Depends(get_current_user),
):
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year, 12, 31, tzinfo=timezone.utc)

    pipeline = [
        {"$match": {"user_id": current_user["_id"], "date": {"$gte": start, "$lte": end}}},
        {
            "$group": {
                "_id": {"year": {"$year": "$date"}, "month": {"$month": "$date"}},
                "total_paise": {"$sum": "$amount_paise"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.month": 1}},
    ]

    months = []
    async for row in expenses_collection.aggregate(pipeline):
        months.append(
            MonthTotal(
                year=row["_id"]["year"],
                month=row["_id"]["month"],
                total=paise_to_rupees(row["total_paise"]),
                count=row["count"],
            )
        )

    return MonthlyReport(year=year, months=months)


@router.get("/reports/top-expenses", response_model=list[TopExpense])
async def top_expenses_this_month(
    limit: int = Query(default=5, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    month_start, month_end = _current_month_range()
    cursor = (
        expenses_collection.find(
            {
                "user_id": current_user["_id"],
                "date": {
                    "$gte": _date_to_datetime(month_start),
                    "$lte": _date_to_datetime(month_end),
                },
            }
        )
        .sort("amount_paise", -1)
        .limit(limit)
    )

    return [
        TopExpense(
            id=str(doc["_id"]),
            amount=paise_to_rupees(doc["amount_paise"]),
            category=doc["category"],
            date=doc["date"].date(),
            note=doc.get("note"),
        )
        async for doc in cursor
    ]


@router.get("/reports/export")
async def export_csv(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    current_user: dict = Depends(get_current_user),
):
    query = {
        "user_id": current_user["_id"],
        "date": {"$gte": _date_to_datetime(date_from), "$lte": _date_to_datetime(date_to)},
    }

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "category", "amount", "note"])

    async for doc in expenses_collection.find(query).sort("date", 1):
        writer.writerow(
            [
                doc["date"].date().isoformat(),
                doc["category"],
                paise_to_rupees(doc["amount_paise"]),
                doc.get("note") or "",
            ]
        )

    buffer.seek(0)
    filename = f"expenses_{date_from.isoformat()}_{date_to.isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
