from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import expenses_collection
from app.models import (
    Category,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    PaginatedExpenses,
    paise_to_rupees,
    rupees_to_paise,
)
from app.security import get_current_user

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _date_to_datetime(d: date) -> datetime:
    """Store dates as midnight UTC datetimes so range comparisons are exact
    and inclusive without off-by-one bugs."""
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _doc_to_expense_out(doc: dict) -> ExpenseOut:
    return ExpenseOut(
        id=str(doc["_id"]),
        amount=paise_to_rupees(doc["amount_paise"]),
        category=doc["category"],
        date=doc["date"].date(),
        note=doc.get("note"),
        created_at=doc["created_at"],
    )


def _get_object_id(expense_id: str) -> ObjectId:
    try:
        return ObjectId(expense_id)
    except InvalidId:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(payload: ExpenseCreate, current_user: dict = Depends(get_current_user)):
    doc = {
        "user_id": current_user["_id"],
        "amount_paise": rupees_to_paise(payload.amount),
        "category": payload.category.value,
        "date": _date_to_datetime(payload.date),
        "note": payload.note,
        "created_at": datetime.now(timezone.utc),
    }
    result = await expenses_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_expense_out(doc)


@router.get("", response_model=PaginatedExpenses)
async def list_expenses(
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
    category: Optional[Category] = None,
    min_amount: Optional[Decimal] = Query(default=None, ge=0),
    max_amount: Optional[Decimal] = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    query: dict = {"user_id": current_user["_id"]}

    if date_from or date_to:
        date_filter = {}
        if date_from:
            date_filter["$gte"] = _date_to_datetime(date_from)
        if date_to:
            date_filter["$lte"] = _date_to_datetime(date_to)  # inclusive of "to" date
        query["date"] = date_filter

    if category:
        query["category"] = category.value

    if min_amount is not None or max_amount is not None:
        amount_filter = {}
        if min_amount is not None:
            amount_filter["$gte"] = rupees_to_paise(min_amount)
        if max_amount is not None:
            amount_filter["$lte"] = rupees_to_paise(max_amount)
        query["amount_paise"] = amount_filter

    total = await expenses_collection.count_documents(query)

    cursor = (
        expenses_collection.find(query)
        .sort("date", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_doc_to_expense_out(doc) async for doc in cursor]

    return PaginatedExpenses(total=total, page=page, page_size=page_size, items=items)


@router.get("/{expense_id}", response_model=ExpenseOut)
async def get_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    oid = _get_object_id(expense_id)
    doc = await expenses_collection.find_one({"_id": oid, "user_id": current_user["_id"]})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return _doc_to_expense_out(doc)


@router.put("/{expense_id}", response_model=ExpenseOut)
async def update_expense(expense_id: str, payload: ExpenseUpdate, current_user: dict = Depends(get_current_user)):
    oid = _get_object_id(expense_id)

    update: dict = {}
    if payload.amount is not None:
        update["amount_paise"] = rupees_to_paise(payload.amount)
    if payload.category is not None:
        update["category"] = payload.category.value
    if payload.date is not None:
        update["date"] = _date_to_datetime(payload.date)
    if payload.note is not None:
        update["note"] = payload.note

    if not update:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    result = await expenses_collection.find_one_and_update(
        {"_id": oid, "user_id": current_user["_id"]},
        {"$set": update},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return _doc_to_expense_out(result)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(expense_id: str, current_user: dict = Depends(get_current_user)):
    oid = _get_object_id(expense_id)
    result = await expenses_collection.delete_one({"_id": oid, "user_id": current_user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
