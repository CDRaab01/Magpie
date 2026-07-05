from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings


def client_key(request: Request) -> str:
    """Rate-limit key = the real client IP.

    Magpie is tailnet-only (no reverse proxy in front of it), so ``trust_proxy`` stays off
    by default like the suite's other apps — kept for parity in case a future deploy shape
    puts something in front of it.
    """
    if settings.trust_proxy:
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_key)
