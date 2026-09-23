from fastapi import APIRouter

from app.api.routers import (
    account,
    bank,
    certificate,
    companies,
    coord,
    deals,
    dictionaries,
    files,
    mentorship,
    micro,
    orgs,
    profile,
    route,
    schedule,
    search,
)
from app.bot import webhook as bot_webhook

API_ROUTERS: list[APIRouter] = [
    schedule.router,
    search.router,
    deals.router,
    companies.router,
    route.router,
    certificate.router,
    account.router,
    profile.router,
    dictionaries.router,
    micro.router,
    bank.router,
    mentorship.router,
    coord.router,
    orgs.router,
    orgs.operator_router,
]

ROOT_ROUTERS: list[APIRouter] = [
    certificate.check_router,
    files.router,
    bot_webhook.router,
]

def build_api_router() -> APIRouter:
    api = APIRouter(prefix="/api/v1")
    for router in API_ROUTERS:
        api.include_router(router)
    return api
