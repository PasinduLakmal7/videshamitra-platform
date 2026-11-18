from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_user

router = APIRouter()

@router.get("/")
async def get_verification_root(user: dict = Depends(get_current_user)):
    return {"module": "verification", "status": "active"}
