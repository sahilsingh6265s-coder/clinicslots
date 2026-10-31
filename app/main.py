from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.routers import admin, appointments, auth, doctor_portal, doctors


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.assert_production_ready()  # refuse to start with a weak secret in production
    yield


app = FastAPI(
    title="ClinicSlot",
    description="Doctor appointment booking API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(doctors.router)
app.include_router(doctor_portal.router)
app.include_router(appointments.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
