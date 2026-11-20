from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SmartExam Ethiopia API",
    version="0.1.0",
    description="Role-based online examination system API.",
)

# Development origin only. Production origins must be configured explicitly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Process health endpoint; database readiness is added in the DB phase."""
    return {"status": "ok", "service": "smart-exam-ethiopia-api"}
