import os
import sys
import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlsplit

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR)) if str(BACKEND_DIR) not in sys.path else None
os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"

import profile_storage  # noqa: E402


class ProfileStorageBatchSigningTests(unittest.TestCase):
    def _response(self, paths):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [
            {"path": path, "signedURL": f"/storage/v1/object/sign/profile-images/{path}?token=test"}
            for path in paths
        ]
        return response

    def test_private_avatar_paths_are_signed_in_chunks_and_keep_input_order(self):
        paths = [f"profiles/{index}/avatar.jpg" for index in range(205)]
        responses = [self._response(paths[offset:offset + 100]) for offset in (0, 100, 200)]
        with patch.object(profile_storage, "uses_supabase_storage", return_value=True), patch.object(
            profile_storage, "_require_supabase_config",
        ), patch.object(profile_storage, "SUPABASE_URL", "https://storage.example.test"), patch.object(
            profile_storage, "PROFILE_SIGNED_URL_BATCH_SIZE", 100,
        ), patch.object(profile_storage.httpx, "post", side_effect=responses) as post:
            result = profile_storage.get_profile_image_urls(paths)

        self.assertEqual(post.call_count, 3)
        self.assertEqual([len(call.kwargs["json"]["paths"]) for call in post.call_args_list], [100, 100, 5])
        self.assertTrue(all(
            call.args[0] == "https://storage.example.test/storage/v1/object/sign/profile-images"
            for call in post.call_args_list
        ))
        self.assertEqual(len(result), len(paths))
        self.assertEqual(
            result[0],
            "https://storage.example.test/storage/v1/object/sign/profile-images/profiles/0/avatar.jpg?token=test",
        )
        self.assertTrue(result[-1].endswith("profiles/204/avatar.jpg?token=test"))

    def test_external_and_legacy_paths_are_not_sent_to_supabase(self):
        with patch.object(profile_storage, "uses_supabase_storage", return_value=True), patch.object(
            profile_storage, "_require_supabase_config",
        ), patch.object(profile_storage.httpx, "post") as post:
            result = profile_storage.get_profile_image_urls([
                "https://cdn.example.test/avatar.jpg", "/uploads/local.jpg", None,
            ])
        self.assertEqual(result, ["https://cdn.example.test/avatar.jpg", "/uploads/local.jpg", None])
        post.assert_not_called()

    def test_batch_signing_failure_degrades_only_private_avatars_to_none(self):
        with patch.object(profile_storage, "uses_supabase_storage", return_value=True), patch.object(
            profile_storage, "_require_supabase_config",
        ), patch.object(profile_storage.httpx, "post", side_effect=httpx.ConnectError("offline")):
            self.assertEqual(
                profile_storage.get_profile_image_urls(["profiles/1/avatar.jpg"]),
                [None],
            )

    def test_local_production_avatar_uses_short_lived_signed_url(self):
        filename = "a" * 32 + ".jpg"
        with tempfile.TemporaryDirectory() as upload_dir:
            image_path = Path(upload_dir) / filename
            image_path.write_bytes(b"jpeg")
            with patch.object(profile_storage, "is_production", return_value=True), patch.object(
                profile_storage, "UPLOAD_DIR", upload_dir,
            ):
                url = profile_storage.get_profile_image_urls([
                    f"uploads/profiles/{filename}",
                ])[0]

                parts = urlsplit(url)
                query = parse_qs(parts.query)
                resolved = profile_storage.resolve_local_profile_image(
                    filename,
                    int(query["expires"][0]),
                    query["signature"][0],
                )
                rejected = profile_storage.resolve_local_profile_image(
                    filename,
                    int(query["expires"][0]),
                    "0" * 64,
                )

        self.assertEqual(parts.path, f"uploads/profiles/{filename}")
        self.assertEqual(resolved, image_path)
        self.assertIsNone(rejected)


class ProfileStorageDeletionTests(unittest.TestCase):
    def test_async_delete_sends_json_with_generic_request_and_is_best_effort(self):
        response = Mock()
        response.raise_for_status.return_value = None
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.request.return_value = response
        with (
            patch.object(profile_storage, "uses_supabase_storage", return_value=True),
            patch.object(profile_storage, "_require_supabase_config"),
            patch.object(profile_storage, "_bucket_object_url", return_value="https://storage.test/object"),
            patch.object(profile_storage, "_auth_headers", return_value={"Authorization": "Bearer test"}),
            patch.object(profile_storage.httpx, "AsyncClient", return_value=client),
        ):
            asyncio.run(profile_storage.delete_profile_image("profiles/8/avatar.jpg"))

        client.request.assert_awaited_once_with(
            "DELETE", "https://storage.test/object",
            json={"prefixes": ["profiles/8/avatar.jpg"]},
            headers={"Authorization": "Bearer test"},
        )

        client.request.side_effect = TypeError("cleanup request failed")
        with (
            patch.object(profile_storage, "uses_supabase_storage", return_value=True),
            patch.object(profile_storage, "_require_supabase_config"),
            patch.object(profile_storage.httpx, "AsyncClient", return_value=client),
        ):
            asyncio.run(profile_storage.delete_profile_image("profiles/8/avatar.jpg"))

    def test_sync_delete_uses_generic_request_for_json_body(self):
        response = Mock()
        response.raise_for_status.return_value = None
        with (
            patch.object(profile_storage, "uses_supabase_storage", return_value=True),
            patch.object(profile_storage, "_require_supabase_config"),
            patch.object(profile_storage, "_bucket_object_url", return_value="https://storage.test/object"),
            patch.object(profile_storage, "_auth_headers", return_value={"Authorization": "Bearer test"}),
            patch.object(profile_storage.httpx, "request", return_value=response) as request,
        ):
            profile_storage.delete_profile_image_sync("profiles/8/avatar.jpg")

        request.assert_called_once_with(
            "DELETE", "https://storage.test/object",
            json={"prefixes": ["profiles/8/avatar.jpg"]},
            headers={"Authorization": "Bearer test"}, timeout=20,
        )


if __name__ == "__main__":
    unittest.main()
