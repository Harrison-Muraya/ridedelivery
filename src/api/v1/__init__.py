from fastapi import APIRouter
from src.api.v1 import auth, customer, rider, admin, payments

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(customer.router)
api_router.include_router(rider.router)
api_router.include_router(admin.router)
api_router.include_router(payments.router)
