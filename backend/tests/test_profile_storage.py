import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
