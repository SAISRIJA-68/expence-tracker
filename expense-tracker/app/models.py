from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class Category(str, Enum):
    food = "food"
    transport = "transport"
    rent = "rent"
    utilities = "utilities"
    entertainment = "entertainment"
    health = "health"
    shopping = "shopping"
    other = "other"


# ---------------------------------------------------------------------------
# Money helpers
#
# Money is NEVER stored or summed as a float. Amounts are accepted/returned
# as decimal rupees in the API (e.g. 149.50) but persisted in MongoDB as an
# integer number of paise (149.50 -> 14950). All aggregation ($sum, $avg)
# therefore operates on integers, which is exact. We only convert back to a
# decimal rupee value when shaping the API response.
# ---------------------------------------------------------------------------

def rupees_to_paise(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees(paise: int) -> float:
    return float((Decimal(paise) / 100).quantize(Decimal("0.01")))


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    monthly_budget: Optional[Decimal] = Field(default=None, ge=0)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    monthly_budget: Optional[float] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BudgetUpdate(BaseModel):
    monthly_budget: Decimal = Field(ge=0)


# ---------------------------------------------------------------------------
# Expense schemas
# ---------------------------------------------------------------------------

class ExpenseCreate(BaseModel):
    amount: Decimal = Field(gt=0, description="Amount in rupees, must be positive")
    category: Category
    date: date
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("amount")
    @classmethod
    def validate_amount_precision(cls, v: Decimal) -> Decimal:
        # Reject more than 2 decimal places rather than silently rounding.
        if v.as_tuple().exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return v


class ExpenseUpdate(BaseModel):
    amount: Optional[Decimal] = Field(default=None, gt=0)
    category: Optional[Category] = None
    date: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("amount")
    @classmethod
    def validate_amount_precision(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v.as_tuple().exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return v


class ExpenseOut(BaseModel):
    id: str
    amount: float
    category: Category
    date: date
    note: Optional[str] = None
    created_at: datetime


class PaginatedExpenses(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ExpenseOut]


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------

class CategoryTotal(BaseModel):
    category: Category
    total: float
    percentage: float
    count: int


class SummaryReport(BaseModel):
    from_date: date
    to_date: date
    total_spent: float
    categories: list[CategoryTotal]
    budget: Optional[float] = None
    remaining: Optional[float] = None
    over_budget: Optional[bool] = None


class MonthTotal(BaseModel):
    year: int
    month: int
    total: float
    count: int


class MonthlyReport(BaseModel):
    year: int
    months: list[MonthTotal]


class TopExpense(BaseModel):
    id: str
    amount: float
    category: Category
    date: date
    note: Optional[str] = None
