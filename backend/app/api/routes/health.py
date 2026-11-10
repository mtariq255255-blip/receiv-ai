from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.database import engine


router = APIRouter(
    tags=["Health"]
)


@router.get("/health")
def check_database_connection():

    try:

        with engine.connect() as connection:

            connection.execute(text("SELECT 1"))

        return {
            "status": "connected",
            "database": "neondb",
            "service": "ReceivAI UAE"
        }

    except Exception as error:

        raise HTTPException(
            status_code=503,
            detail="Database connection failed. Check backend configuration."
        ) from error