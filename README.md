# ClinicSlot

Doctor appointment booking API (FastAPI + PostgreSQL).

## Run it
```bash
docker compose up --build
# in another terminal, create the tables:
docker compose exec api alembic revision --autogenerate -m "create tables"
docker compose exec api alembic upgrade head
```
Open http://localhost:8000/docs

## Run tests (no database needed, uses in-memory SQLite)
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
```
