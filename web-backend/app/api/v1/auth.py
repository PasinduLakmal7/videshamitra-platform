from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_user

router = APIRouter()

@router.get("/")
async def get_auth_root(user: dict = Depends(get_current_user)):
    return {"module": "auth", "status": "active"}
