from fastapi import FastAPI

from app.routers import admin, auth, doctor_portal, doctors

app = FastAPI(title="ClinicSlot", description="Doctor appointment booking API", version="0.1.0")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(doctors.router)
app.include_router(doctor_portal.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
