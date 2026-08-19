"""Aggregates all v1 API routers."""
from fastapi import APIRouter

from app.api.v1.endpoints import inspections

api_router = APIRouter()
api_router.include_router(inspections.router)
