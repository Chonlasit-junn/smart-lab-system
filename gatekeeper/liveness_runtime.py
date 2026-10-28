"""FP32 inference for the original Silent-Face MiniFASNetV2 model."""

import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np


MODEL_STEM = "2.7_80x80_MiniFASNetV2"
MODEL_RELATIVE_DIR = Path("Silent-Face-Anti-Spoofing/resources/anti_spoof_models")


def inference_threads():
    value = os.getenv("SMART_GATEKEEPER_INFERENCE_THREADS", os.getenv("SMART_GATEKEEPER_TORCH_THREADS", "2"))
    try:
        return max(1, min(8, int(value)))
    except ValueError:
        return 2


def prepare_input(image):
    if not isinstance(image, np.ndarray) or image.shape != (80, 80, 3) or image.dtype != np.uint8:
        raise ValueError("Liveness input must be an 80x80 BGR uint8 image.")
    # The vendored Silent-Face ToTensor returns float values 0..255, without
    # dividing by 255 or swapping BGR/RGB. Preserve its exact pixel contract.
    return np.ascontiguousarray(image.transpose(2, 0, 1)[None], dtype=np.float32)


class OnnxLiveness:
    def __init__(self, model_path):
        self.model_path = Path(model_path)
        manifest = json.loads(self.model_path.with_suffix(".json").read_text(encoding="utf-8"))
        if (
            manifest.get("model") != MODEL_STEM or manifest.get("precision") != "FP32"
            or manifest.get("preprocessing") != "BGR_NCHW_FLOAT32_0_255"
            or manifest.get("real_class_index") != 1 or manifest.get("output") != "softmax_probabilities"
            or hashlib.sha256(self.model_path.read_bytes()).hexdigest() != manifest.get("onnx_sha256")
        ):
            raise ValueError("Liveness model integrity or preprocessing mismatch.")
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = inference_threads()
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(
            str(self.model_path), sess_options=options, providers=["CPUExecutionProvider"],
        )
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (
            len(inputs) != 1 or inputs[0].type != "tensor(float)" or inputs[0].shape != [1, 3, 80, 80]
            or len(outputs) != 1 or outputs[0].type != "tensor(float)" or outputs[0].shape != [1, 3]
        ):
            raise ValueError("Unexpected FP32 liveness model input/output contract.")
        self.input_name, self.output_name = inputs[0].name, outputs[0].name

    def predict(self, image, model_path=None):
        if model_path is not None and Path(model_path) != self.model_path:
            raise ValueError("Cannot change a loaded liveness model during a scan.")
        result = self.session.run([self.output_name], {self.input_name: prepare_input(image)})[0]
        # The ONNX graph already includes the original Softmax (real class = 1).
        if (
            result.shape != (1, 3) or result.dtype != np.float32 or not np.isfinite(result).all()
            or np.any(result < 0) or np.any(result > 1)
            or not np.allclose(result.sum(axis=1), 1.0, atol=1e-5)
        ):
            raise ValueError("Invalid liveness probability output.")
        return result


def load_liveness(base_dir, backend=None):
    backend = backend if backend is not None else os.getenv("SMART_GATEKEEPER_LIVENESS_BACKEND", "onnx")
    model_dir = Path(base_dir) / MODEL_RELATIVE_DIR
    if backend == "onnx":
        path = model_dir / f"{MODEL_STEM}.fp32.onnx"
        return OnnxLiveness(path), str(path)
    if backend == "pytorch" and not getattr(sys, "frozen", False):
        from liveness_reference import load_torch_reference

        path = model_dir / f"{MODEL_STEM}.pth"
        return load_torch_reference(base_dir), str(path)
    raise ValueError("Unsupported liveness backend; packaged Gatekeeper requires ONNX.")
