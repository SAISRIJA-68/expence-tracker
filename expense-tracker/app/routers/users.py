from fastapi import APIRouter, Depends
from bson import ObjectId

from app.database import users_collection
from app.models import UserOut, BudgetUpdate
from app.security import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserOut(
        id=str(current_user["_id"]),
        email=current_user["email"],
        monthly_budget=current_user.get("monthly_budget"),
    )


@router.put("/me/budget", response_model=UserOut)
async def set_budget(payload: BudgetUpdate, current_user: dict = Depends(get_current_user)):
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"monthly_budget": float(payload.monthly_budget)}},
    )
    return UserOut(
        id=str(current_user["_id"]),
        email=current_user["email"],
        monthly_budget=float(payload.monthly_budget),
    )
