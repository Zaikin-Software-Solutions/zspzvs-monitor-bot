from aiogram import Router

from .admin import router as admin_router


def build_root_router() -> Router:
    root = Router()
    root.include_router(admin_router)
    return root


__all__ = ["build_root_router"]
