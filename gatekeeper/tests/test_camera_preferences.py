import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from camera_preferences import load_camera_index, save_camera_index


class CameraPreferencesTests(unittest.TestCase):
    def test_preference_remembers_only_camera_index_separately_from_credentials(self):
        root = Path(__file__).resolve().parents[1] / "runtime"
        with tempfile.TemporaryDirectory(dir=root) as folder, patch.dict(os.environ, {"SMART_GATEKEEPER_DATA_DIR": folder}):
            self.assertEqual(load_camera_index(), 0)
            save_camera_index(3)
            self.assertEqual(load_camera_index(), 3)
            files = list(Path(folder).iterdir())
            self.assertEqual([file.name for file in files], ["camera_preferences.json"])
            self.assertEqual(json.loads(files[0].read_text()), {"camera_index": 3})

    def test_invalid_saved_values_fall_back_without_blocking_camera_start(self):
        root = Path(__file__).resolve().parents[1] / "runtime"
        with tempfile.TemporaryDirectory(dir=root) as folder, patch.dict(os.environ, {"SMART_GATEKEEPER_DATA_DIR": folder}):
            path = Path(folder) / "camera_preferences.json"
            for value in ("broken", "[]", '{"camera_index":true}', '{"camera_index":-1}', '{"camera_index":6}'):
                path.write_text(value)
                self.assertEqual(load_camera_index(default=2), 2)

    def test_invalid_selection_cannot_be_saved(self):
        for value in (True, -1, 6, "0"):
            with self.assertRaises(ValueError):
                save_camera_index(value)
