"""
API Key Authentication
======================
Đọc API_KEY từ biến môi trường.
Nếu API_KEY không được set → bỏ qua auth (development mode).
"""

import os
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_api_key() -> str | None:
    return os.getenv("API_KEY", "").strip() or None


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """
    FastAPI dependency — xác thực X-API-Key header.
    - Nếu API_KEY env chưa set → bỏ qua (dev mode), cho đi qua.
    - Nếu API_KEY đã set → bắt buộc phải có header đúng.
    """
    server_key = get_api_key()

    if server_key is None:
        # Dev mode: không cấu hình key → allow all
        return

    if not api_key or api_key != server_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key. Please provide X-API-Key header.",
        )
