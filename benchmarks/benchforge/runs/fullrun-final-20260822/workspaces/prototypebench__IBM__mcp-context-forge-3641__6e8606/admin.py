from fastapi import APIRouter, Query
from typing import Optional
from settings import settings

router = APIRouter()

# Admin endpoints with pagination
@router.get("/users")
def get_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=settings.pagination_max_page_size),
):
    pass

@router.get("/organizations")
def get_organizations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=settings.pagination_max_page_size),
):
    pass

@router.get("/projects")
def get_projects(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=settings.pagination_max_page_size),
):
    pass
