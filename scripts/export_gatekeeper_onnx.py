"""Export the existing trusted MiniFASNetV2 weights to a checked FP32 graph."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gatekeeper"))


def export():
    import numpy as np
    import onnx
    import torch
    from liveness_reference import load_torch_reference
    from liveness_runtime import MODEL_RELATIVE_DIR, MODEL_STEM, OnnxLiveness

    source = ROOT / "gatekeeper" / MODEL_RELATIVE_DIR / f"{MODEL_STEM}.pth"
    target = source.with_name(f"{MODEL_STEM}.fp32.onnx")
    predictor = load_torch_reference(ROOT / "gatekeeper")
    model = torch.nn.Sequential(predictor.model, torch.nn.Softmax(dim=1)).float().eval()
    # Never replace the usable model until graph checks and parity both pass.
    with tempfile.TemporaryDirectory(dir=target.parent, prefix="onnx-export-") as folder:
        candidate = Path(folder) / target.name
        with torch.inference_mode():
            torch.onnx.export(
                model, torch.zeros(1, 3, 80, 80, dtype=torch.float32), str(candidate),
                input_names=["bgr_image"], output_names=["probabilities"],
                opset_version=17, do_constant_folding=True,
            )
        graph = onnx.load(str(candidate))
        onnx.checker.check_model(graph, full_check=True)
        if any(t.data_type != onnx.TensorProto.FLOAT for t in graph.graph.initializer):
            raise ValueError("Export contains non-FP32 model weights.")
        manifest = {
            "model": MODEL_STEM, "precision": "FP32", "opset": 17,
            "preprocessing": "BGR_NCHW_FLOAT32_0_255", "real_class_index": 1,
            "output": "softmax_probabilities", "source": source.name,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "onnx_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "torch_version": torch.__version__, "onnx_version": onnx.__version__,
        }
        candidate.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        runtime = OnnxLiveness(candidate)
        rng = np.random.default_rng(42)
        max_error = 0.0
        for _ in range(16):
            image = rng.integers(0, 256, (80, 80, 3), dtype=np.uint8)
            expected = predictor.predict(image, str(source))
            actual = runtime.predict(image)
            np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-5)
            max_error = max(max_error, float(np.abs(actual - expected).max()))
        candidate.replace(target)
        candidate.with_suffix(".json").replace(target.with_suffix(".json"))
    print(json.dumps({"path": str(target), "bytes": target.stat().st_size,
                      "precision": "FP32", "max_absolute_error": max_error, **manifest}))


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    export()
