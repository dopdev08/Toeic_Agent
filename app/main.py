from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.enrichments import router as enrichments_router
from app.api.import_questions import router as import_router
from app.api.questions import router as questions_router
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TOEIC AI Agent API",
    version="1.0.0",
    description="Question import and practice pipeline for TOEIC AI Agent (Part 5 focus)",
    lifespan=lifespan,
)

app.include_router(import_router)
app.include_router(questions_router)
app.include_router(enrichments_router)
