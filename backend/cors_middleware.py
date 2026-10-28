"""Enforce browser origins even when an upstream proxy rewrites CORS headers."""

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send


class OriginCheckedCORSMiddleware(CORSMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            origins = Headers(scope=scope).getlist("origin")
            # Ordinary CORS middleware only withholds response headers for an
            # untrusted actual request; its endpoint can still run. Reject it
            # before auth, body parsing or DB work, independently of those headers.
            if origins and (
                len(origins) != 1
                or not origins[0]
                or not self.is_allowed_origin(origins[0])
            ):
                response = JSONResponse(
                    {"detail": "Request origin is not allowed."},
                    status_code=403,
                    headers={"Cache-Control": "no-store", "Vary": "Origin"},
                )
                await response(scope, receive, send)
                return

        # Native Agent/Gatekeeper clients have no Origin. Their existing token
        # and device/session authorization still applies inside the application.
        await super().__call__(scope, receive, send)
