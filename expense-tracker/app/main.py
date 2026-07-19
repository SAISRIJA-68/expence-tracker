from fastapi import FastAPI

from app.database import ensure_indexes
from app.routers import auth, expenses, reports, users

app = FastAPI(
    title="Expense Tracker API",
    description="Track expenses and get category/monthly spending summaries via MongoDB aggregation pipelines.",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(expenses.router)
app.include_router(reports.router)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()


@app.get("/health")
async def health():
    return {"status": "ok"}
