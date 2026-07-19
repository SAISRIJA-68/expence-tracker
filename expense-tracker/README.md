# Expense Tracker API

A FastAPI + MongoDB expense tracker built around aggregation pipelines. CRUD
is the easy 20%; the point of this project is the reporting endpoints, so
read `app/routers/reports.py` first.

## Stack

- **FastAPI** for the HTTP layer
- **MongoDB** via **Motor** (async driver)
- **JWT** auth (`python-jose`) with bcrypt-hashed passwords (`passlib`)
- **Pydantic v2** for validation

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set MONGO_URI to your MongoDB instance, set a real JWT_SECRET

uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`.

You need a running MongoDB instance (local `mongod`, Docker, or Atlas).
Quick local option: `docker run -d -p 27017:27017 mongo:7`.

## Auth flow

1. `POST /auth/register` — `{"email": "...", "password": "...", "monthly_budget": 20000}`
2. `POST /auth/login` — form-encoded (`username`, `password`), returns a bearer token
3. Send `Authorization: Bearer <token>` on every other request

## Core design decisions

**Money is stored as integer paise, never floats.** A request with
`"amount": 149.50` is converted to `14950` (paise) before it touches the
database (`app/models.py::rupees_to_paise`). All aggregation `$sum`/`$avg`
operations therefore run on integers, which is exact — no floating point
drift when you add thousands of expenses. The API converts back to rupees
only when shaping a response.

**Dates are stored as midnight-UTC datetimes.** Because every stored date
has zero time-of-day, an inclusive `$lte` on the `to` date correctly
includes an expense dated exactly on that day, with no off-by-one bug.

**Reports are pure aggregation pipelines**, not Python loops over fetched
documents:
- `/reports/summary` uses `$facet` to compute per-category totals and the
  overall total in a single pipeline call, then derives percentages from
  those integer paise totals.
- `/reports/monthly` uses `$group` on `{$year, $month}` extracted from the
  date field.
- `/reports/top-expenses` uses `$sort` + `$limit`, no in-memory sort.

**Every query is scoped by `user_id`** (taken from the JWT, never from the
request body), so one user can never see or aggregate another's expenses.

## Endpoints

### Expenses
- `POST /expenses` — create (422 on non-positive amount or invalid category)
- `GET /expenses?from=&to=&category=&min_amount=&max_amount=&page=&page_size=`
- `GET /expenses/{id}`
- `PUT /expenses/{id}`
- `DELETE /expenses/{id}`

### Reports
- `GET /reports/summary?from=&to=` — category breakdown + percentages;
  defaults to the current month; includes `budget`/`remaining`/`over_budget`
  when the range is the current month and a budget is set
- `GET /reports/monthly?year=2026` — one entry per month with data
- `GET /reports/top-expenses?limit=5` — largest expenses this month
- `GET /reports/export?from=&to=` — CSV download (stretch goal)

### Users
- `GET /users/me`
- `PUT /users/me/budget` — `{"monthly_budget": 20000}`

## Testing the aggregation logic

`app/routers/reports.py` pipelines were verified against a known dataset
using `mongomock` (see project notes) — category totals summed correctly,
percentages summed to 100%, and a boundary-date expense (dated exactly on
`to`) was included while one day past it was excluded, confirming the
inclusive date-range logic has no off-by-one error.

## Project layout

```
app/
  main.py            FastAPI app, router registration
  config.py          Settings (env vars)
  database.py        Motor client, collections, indexes
  security.py        Password hashing, JWT, get_current_user dependency
  models.py          Pydantic schemas + money helpers
  routers/
    auth.py          register/login
    users.py         profile, budget
    expenses.py      CRUD + filtered list
    reports.py       summary, monthly, top-expenses, CSV export
```

## Stretch goals implemented

- CSV export (`/reports/export`)
- Top 5 largest expenses this month (`/reports/top-expenses`)
