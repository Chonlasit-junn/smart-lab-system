"""Origin enforcement with synthetic endpoints; no database or external calls."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cors_middleware import OriginCheckedCORSMiddleware


ALLOWED_ORIGIN = "https://web.example.com"
AUTHORIZATION = "Bearer synthetic-test-token"
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class PermissiveProxy:
    """Model an edge answering preflights and replacing app CORS headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if scope["method"] == "OPTIONS" and origin:
            return await Response(headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": headers["access-control-request-method"],
            })(scope, receive, send)

        async def rewrite(message):
            if message["type"] == "http.response.start" and origin:
                MutableHeaders(scope=message)["Access-Control-Allow-Origin"] = origin
            await send(message)

        await self.app(scope, receive, rewrite)


class OriginMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.auth_calls = 0
        self.endpoint_calls = 0
        self.app = FastAPI()
        self.app.add_middleware(
            OriginCheckedCORSMiddleware,
            allow_origins=[ALLOWED_ORIGIN, "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=METHODS,
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=["Retry-After", "Content-Disposition"],
        )

        def authenticate(request: Request):
            self.auth_calls += 1
            if request.headers.get("authorization") != AUTHORIZATION:
                raise HTTPException(401, "Not authenticated")

        @self.app.api_route("/probe", methods=METHODS, dependencies=[Depends(authenticate)])
        async def endpoint(request: Request):
            self.endpoint_calls += 1
            body = await request.body()
            return {"body": body.decode(), "method": request.method}

        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_allowed_web_and_development_origins_preserve_requests(self):
        for origin in (ALLOWED_ORIGIN, "http://127.0.0.1:5173"):
            with self.subTest(origin=origin):
                response = self.client.post("/probe", json={"message": "unchanged"}, headers={
                    "Origin": origin, "Authorization": AUTHORIZATION,
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn("unchanged", response.json()["body"])
                self.assertEqual(response.headers["access-control-allow-origin"], origin)
                self.assertIn("Content-Disposition", response.headers["access-control-expose-headers"])
        self.assertEqual(self.endpoint_calls, 2)

    def test_preflight_does_not_call_authentication_or_endpoint(self):
        for origin, status in ((ALLOWED_ORIGIN, 200), ("https://attacker.example", 403)):
            response = self.client.options("/probe", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            })
            self.assertEqual(response.status_code, status)
        self.assertEqual(self.auth_calls, 0)
        self.assertEqual(self.endpoint_calls, 0)

    def test_untrusted_actual_requests_are_rejected_before_auth_and_endpoint(self):
        for method in METHODS:
            for content_type in ("application/json", "application/x-www-form-urlencoded", "text/plain"):
                with self.subTest(method=method, content_type=content_type):
                    response = self.client.request(method, "/probe", content="sensitive body", headers={
                        "Origin": "https://attacker.example", "Authorization": AUTHORIZATION,
                        "Content-Type": content_type,
                    })
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.headers["cache-control"], "no-store")
                    self.assertIn("Origin", response.headers["vary"])
                    self.assertNotIn("access-control-allow-origin", response.headers)
                    if method != "HEAD":
                        self.assertEqual(response.json(), {"detail": "Request origin is not allowed."})
        self.assertEqual(self.auth_calls, 0)
        self.assertEqual(self.endpoint_calls, 0)

    def test_origin_matching_is_exact_and_ambiguous_or_opaque_origins_fail(self):
        for origin in (
            "", "null", "http://web.example.com", "https://web.example.com:444",
            "https://web.example.com.attacker.example", "https://sub.web.example.com",
            "https://web.example.com/path", "https://web.example.com@attacker.example",
            f"{ALLOWED_ORIGIN}, https://attacker.example", f"{ALLOWED_ORIGIN} https://attacker.example",
        ):
            with self.subTest(origin=origin):
                response = self.client.get("/probe", headers={"Origin": origin, "Authorization": AUTHORIZATION})
                self.assertEqual(response.status_code, 403)
        for origins in ((ALLOWED_ORIGIN, "https://attacker.example"), ("https://attacker.example", ALLOWED_ORIGIN), (ALLOWED_ORIGIN, ALLOWED_ORIGIN)):
            response = self.client.get("/probe", headers=[
                ("Origin", origins[0]), ("Origin", origins[1]), ("Authorization", AUTHORIZATION),
            ])
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.auth_calls, 0)

    def test_native_clients_without_origin_keep_form_and_file_uploads(self):
        for payload in ({"data": {"device_id": "synthetic-device"}}, {"files": {"face_image": ("test.jpg", b"synthetic-image", "image/jpeg")}}):
            response = self.client.post("/probe", headers={"Authorization": AUTHORIZATION}, **payload)
            self.assertEqual(response.status_code, 200)
            self.assertIn("synthetic", response.json()["body"])
            self.assertNotIn("access-control-allow-origin", response.headers)
        self.assertEqual(self.endpoint_calls, 2)

    def test_allowed_origin_and_absent_origin_do_not_bypass_authentication(self):
        for headers in ({}, {"Origin": ALLOWED_ORIGIN}):
            response = self.client.get("/probe", headers=headers)
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.auth_calls, 2)
        self.assertEqual(self.endpoint_calls, 0)

    def test_proxy_can_approve_preflight_but_cannot_enable_actual_request(self):
        with TestClient(PermissiveProxy(self.app)) as client:
            origin = "https://attacker.example"
            response = client.options("/probe", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
            for method in ("GET", "POST"):
                response = client.request(method, "/probe", headers={"Origin": origin, "Authorization": AUTHORIZATION})
                self.assertEqual(response.headers["access-control-allow-origin"], origin)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["detail"], "Request origin is not allowed.")
            self.assertEqual(self.auth_calls, 0)
            self.assertEqual(self.endpoint_calls, 0)
            response = client.post("/probe", headers={"Origin": ALLOWED_ORIGIN, "Authorization": AUTHORIZATION})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.endpoint_calls, 1)


class ASGIOriginMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejection_never_reads_request_body_or_calls_application(self):
        app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
        middleware = OriginCheckedCORSMiddleware(app, allow_origins=[ALLOWED_ORIGIN])
        await middleware({"type": "http", "headers": [(b"origin", b"https://attacker.example")]}, receive, send)
        app.assert_not_awaited()
        receive.assert_not_awaited()
        self.assertEqual(send.await_args_list[0].args[0]["status"], 403)

    async def test_lifespan_events_still_reach_application(self):
        app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
        scope = {"type": "lifespan"}
        middleware = OriginCheckedCORSMiddleware(app, allow_origins=[ALLOWED_ORIGIN])
        await middleware(scope, receive, send)
        app.assert_awaited_once_with(scope, receive, send)


if __name__ == "__main__":
    unittest.main()
