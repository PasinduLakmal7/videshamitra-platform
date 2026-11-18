from typing import Generator
from app.core.permissions import UserRole

async def get_current_user():
    return {"id": "user-demo-id", "role": UserRole.WORKER, "phone": "+94770000000"}

async def get_admin_user():
    return {"id": "admin-demo-id", "role": UserRole.ADMIN, "email": "admin@videshamitra.lk"}
