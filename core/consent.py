"""Simple in-process OTP bridge for mocked consent pulls.

Tools request an OTP, the browser submits it to server.py, and the waiting tool
continues. This is intentionally one-process demo state, matching SessionState.
"""

import asyncio
import uuid

from loguru import logger

from core import ui_bus

_pending: dict[str, asyncio.Future[str]] = {}


async def request_otp(provider: str) -> str:
    request_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _pending[request_id] = future
    logger.info(f"OTP requested for {provider}: {request_id}")
    await ui_bus.emit({
        "type": "otp_request",
        "payload": {
            "request_id": request_id,
            "provider": provider,
        },
    })
    try:
        return await future
    finally:
        _pending.pop(request_id, None)


async def submit_otp(request_id: str, otp: str) -> bool:
    future = _pending.get(request_id)
    if not future or future.done():
        logger.warning(f"OTP submit rejected for inactive request: {request_id}")
        return False
    logger.info(f"OTP submitted for active request: {request_id}")
    future.set_result(otp)
    return True
