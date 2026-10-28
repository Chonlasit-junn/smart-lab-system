import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from liveness_policy import evaluate_liveness
from liveness_runtime import MODEL_RELATIVE_DIR, MODEL_STEM, OnnxLiveness, load_liveness, prepare_input
from liveness_samples import BASE_DIR, samples


class OnnxRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor, cls.path = load_liveness(BASE_DIR, "onnx")

    def test_preprocessing_preserves_bgr_pixel_scale_and_layout(self):
        image = np.zeros((80, 80, 3), dtype=np.uint8)
        image[:] = [5, 127, 255]
        tensor = prepare_input(image)
        self.assertEqual(tensor.shape, (1, 3, 80, 80))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertTrue(tensor.flags.c_contiguous)
        np.testing.assert_array_equal(tensor[0, :, 0, 0], [5, 127, 255])
        for invalid in (image.astype(np.float32), image[:79], image[:, :, 0], None):
            with self.assertRaises(ValueError):
                prepare_input(invalid)

    def test_model_output_is_finite_fp32_probability_with_real_class_at_index_one(self):
        result = self.predictor.predict(np.zeros((80, 80, 3), dtype=np.uint8), self.path)
        self.assertEqual(result.shape, (1, 3))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(np.isfinite(result).all())
        self.assertAlmostEqual(float(result.sum()), 1.0, places=5)
        self.assertEqual(self.predictor.session.get_providers(), ["CPUExecutionProvider"])

    def test_missing_or_corrupted_model_never_falls_back_to_pytorch(self):
        with tempfile.TemporaryDirectory(dir=BASE_DIR / "runtime") as folder:
            missing = Path(folder) / "missing.onnx"
            with self.assertRaises(FileNotFoundError):
                OnnxLiveness(missing)
            model = Path(folder) / Path(self.path).name
            shutil.copyfile(self.path, model)
            shutil.copyfile(Path(self.path).with_suffix(".json"), model.with_suffix(".json"))
            model.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "integrity"):
                OnnxLiveness(model)

    def test_bad_probability_output_and_model_change_are_rejected(self):
        image = np.zeros((80, 80, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            self.predictor.predict(image, "another-model.onnx")
        for values in ([float("nan"), 0, 1], [-0.1, 0.1, 1], [0.5, 0.5, 0.5]):
            with patch.object(self.predictor.session, "run", return_value=[np.array([values], dtype=np.float32)]):
                with self.assertRaises(ValueError):
                    self.predictor.predict(image)

    def test_unknown_backend_does_not_silently_change_detection(self):
        with self.assertRaises(ValueError):
            load_liveness(BASE_DIR, "automatic")

    def test_onnx_runtime_works_when_pytorch_import_is_blocked(self):
        code = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('torch', 'onnx', 'liveness_reference', 'src'):
            raise ImportError('Export-only dependency was imported: ' + fullname)
sys.meta_path.insert(0, Block())
import numpy as np
from liveness_runtime import load_liveness
predictor, path = load_liveness('.', 'onnx')
assert predictor.predict(np.zeros((80,80,3), dtype=np.uint8), path).shape == (1,3)
"""
        subprocess.run([sys.executable, "-B", "-c", code], cwd=BASE_DIR, check=True, capture_output=True, timeout=30)


@unittest.skipUnless(
    importlib.util.find_spec("torch") and (BASE_DIR / MODEL_RELATIVE_DIR / f"{MODEL_STEM}.pth").is_file(),
    "Parity requires requirements-export.txt and the original .pth weights",
)
class OnnxParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.onnx, _ = load_liveness(BASE_DIR, "onnx")
        cls.torch, cls.torch_path = load_liveness(BASE_DIR, "pytorch")
        cls.samples = samples()
        cls.expected = [cls.torch.predict(image, cls.torch_path) for _, image in cls.samples]
        cls.actual = [cls.onnx.predict(image) for _, image in cls.samples]

    def test_all_class_probabilities_and_per_frame_decisions_match_pytorch(self):
        for (name, _), expected, actual in zip(self.samples, self.expected, self.actual):
            with self.subTest(sample=name):
                np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-5)
                self.assertEqual(int(actual.argmax()), int(expected.argmax()))
                self.assertEqual(float(actual[0, 1]) >= 0.72, float(expected[0, 1]) >= 0.72)

    def test_five_frame_decisions_match_with_and_without_motion(self):
        for offset in range(len(self.samples) - 4):
            for motion in ([3.0] * 4, [0.0] * 4):
                decisions = [evaluate_liveness(
                    [float(scores[0, 1]) for scores in values[offset:offset+5]], motion,
                    threshold=0.72, required_samples=5, required_passes=4, min_motion_score=2.0,
                ) for values in (self.expected, self.actual)]
                self.assertEqual(decisions[0].accepted, decisions[1].accepted)
                self.assertEqual(decisions[0].reason, decisions[1].reason)
                self.assertEqual(decisions[0].passed_samples, decisions[1].passed_samples)

    def test_numpy_input_is_identical_to_original_silent_face_transform(self):
        from src.data_io.transform import ToTensor
        for _, image in self.samples:
            np.testing.assert_array_equal(prepare_input(image), ToTensor()(image).unsqueeze(0).numpy())


@unittest.skipUnless(sys.platform == "win32", "Kiosk uses Windows UI APIs")
class OnnxGatekeeperFlowTests(unittest.TestCase):
    def test_real_onnx_liveness_cannot_override_booking_guest_or_ban_denial(self):
        import smart_gatekeeper as kiosk

        predictor, path = load_liveness(BASE_DIR, "onnx")
        frame = next((image for _, image in samples() if predictor.predict(image)[0, 1] >= 0.72), None)
        self.assertIsNotNone(frame, "Parity fixtures must include a passing real-class sample")
        for allowed, detail in ((True, "Test User"), (False, "booking_required"),
                                (False, "guest_approval_required"), (False, "user_banned")):
            with self.subTest(detail=detail):
                instance = SimpleNamespace(
                    model_path=path, anti_spoof=predictor, _scan_is_current=Mock(return_value=True),
                    _stop_event=SimpleNamespace(wait=Mock(return_value=False)),
                    _get_latest_frame=Mock(return_value=frame),
                    _detect_faces=Mock(return_value=[(0, 0, 80, 80)]),
                    _crop_face=Mock(return_value=frame), _frame_motion_score=Mock(return_value=3.0),
                    _identify_face=Mock(return_value=(allowed, detail)), _post_ui=Mock(),
                    _show_identity_result=Mock(), _set_status=Mock(), _reset_state=Mock(),
                )
                kiosk.GatekeeperDemo._run_liveness(instance, frame, frame, 0)
                instance._identify_face.assert_called_once()
                result = instance._post_ui.call_args.args
                self.assertIs(result[1], allowed)
                self.assertEqual(result[3], detail)

    def test_runtime_load_failure_does_not_mark_scanner_ready(self):
        import smart_gatekeeper as kiosk

        instance = SimpleNamespace(models_loaded=False, _post_ui=Mock(), _models_ready=Mock(), _set_status=Mock())
        with patch.object(kiosk, "load_liveness", side_effect=FileNotFoundError("synthetic missing model")):
            kiosk.GatekeeperDemo._load_models(instance)
        self.assertFalse(instance.models_loaded)
        self.assertEqual(instance._post_ui.call_args.args[1], "MODEL ERROR")
