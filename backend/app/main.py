
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

from app.api.routes import (
    health,
    auth,
    dashboard,
    invoices,
    payments,
    reminders,
    documents
)


# Create FastAPI application
app = FastAPI(
    title="ReceivAI UAE API",
    description=(
        "Agentic Finance Operations and "
        "Invoice Intelligence Platform"
    ),
    version="1.0.0"
)


# Configure frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# Public health endpoint
app.include_router(health.router)

# Administrator authentication
app.include_router(auth.router)

# Protected finance endpoints
app.include_router(dashboard.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(reminders.router)

# Protected document intelligence endpoints
app.include_router(documents.router)


# Root endpoint
@app.get("/")
def root():
    return {
        "message": "Welcome to ReceivAI UAE API",
        "status": "running",
        "version": "1.0.0",
        "documentation": "/docs"
    }
