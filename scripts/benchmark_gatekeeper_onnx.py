"""Compare real FP32 models in separate CPU processes, without camera/API/DB."""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gatekeeper"))
sys.path.insert(0, str(ROOT / "gatekeeper/tests"))


def memory():
    if sys.platform != "win32":
        return None
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage",
            )
        ]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    values = Counters()
    values.cb = ctypes.sizeof(values)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(values), values.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"working_set_bytes": values.WorkingSetSize, "peak_working_set_bytes": values.PeakWorkingSetSize,
            "private_bytes": values.PrivateUsage}


def worker(backend, iterations):
    started = time.perf_counter()
    import numpy as np
    # Both kiosk runtimes need the same camera/image libraries. Include them
    # in BOTH isolated workers so legacy PyTorch imports do not skew RAM/cold
    # comparisons by loading OpenCV/Pillow only on the reference side.
    import cv2  # noqa: F401
    from PIL import Image  # noqa: F401
    from liveness_runtime import load_liveness

    predictor, path = load_liveness(ROOT / "gatekeeper", backend)
    cold_ms = (time.perf_counter() - started) * 1000
    image = np.random.default_rng(42).integers(0, 256, (80, 80, 3), dtype=np.uint8)
    for _ in range(10):
        predictor.predict(image, path)
    times = []
    cpu_started = time.process_time()
    for _ in range(iterations):
        started = time.perf_counter()
        predictor.predict(image, path)
        times.append((time.perf_counter() - started) * 1000)
    cpu_ms = (time.process_time() - cpu_started) * 1000
    module = sys.modules["torch" if backend == "pytorch" else "onnxruntime"]
    package_dir = Path(module.__file__).parent
    result = {"backend": backend, "version": module.__version__, "iterations": iterations,
              "cold_import_and_model_ms": cold_ms, "median_predict_ms": statistics.median(times),
              "p95_predict_ms": sorted(times)[int(len(times) * 0.95) - 1],
              "cpu_ms_per_predict": cpu_ms / iterations, "memory": memory(),
              "installed_package_bytes": sum(p.stat().st_size for p in package_dir.rglob("*") if p.is_file()),
              "torch_loaded": "torch" in sys.modules}
    print(json.dumps(result))


def compare(iterations, runs, output):
    import numpy as np
    from liveness_runtime import load_liveness, MODEL_RELATIVE_DIR, MODEL_STEM
    from liveness_policy import evaluate_liveness
    from liveness_samples import samples

    # Separate processes prevent either library's imported DLLs from skewing
    # the other one's memory/cold-load measurements. Alternate execution order.
    measurements = []
    env = dict(os.environ, SMART_GATEKEEPER_INFERENCE_THREADS="2", OMP_NUM_THREADS="2",
               MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", PYTHONDONTWRITEBYTECODE="1")
    for run in range(runs):
        order = ("pytorch", "onnx") if run % 2 == 0 else ("onnx", "pytorch")
        for backend in order:
            process = subprocess.run(
                [sys.executable, "-B", __file__, "--worker", backend, "--iterations", str(iterations)],
                env=env, capture_output=True, text=True, check=True, timeout=180,
            )
            measurements.append(json.loads(process.stdout.strip().splitlines()[-1]))

    torch, source = load_liveness(ROOT / "gatekeeper", "pytorch")
    onnx, _ = load_liveness(ROOT / "gatekeeper", "onnx")
    frames = samples()
    expected, actual, scores = [], [], []
    for name, image in frames:
        first, second = torch.predict(image, source), onnx.predict(image)
        np.testing.assert_allclose(first, second, rtol=1e-4, atol=1e-5)
        expected.append(float(first[0, 1]))
        actual.append(float(second[0, 1]))
        scores.append({"sample": name, "pytorch_real_score": expected[-1], "onnx_real_score": actual[-1],
                       "max_absolute_error": float(np.abs(first - second).max()),
                       "same_class": bool(first.argmax() == second.argmax()),
                       "same_threshold_decision": (expected[-1] >= 0.72) == (actual[-1] >= 0.72)})
    sequences = []
    for index in range(len(frames)):
        # Repeated crops simulate the same subject at five sampling instants;
        # motion values are controlled to exercise both motion-gate branches.
        for motion in (0.0, 3.0):
            decisions = [evaluate_liveness(
                [values[index]] * 5, [motion] * 4, threshold=0.72, required_samples=5,
                required_passes=4, min_motion_score=2.0,
            ) for values in (expected, actual)]
            sequences.append({"sample": frames[index][0], "motion_score": motion,
                              "pytorch_accepted": decisions[0].accepted, "onnx_accepted": decisions[1].accepted,
                              "same_decision": decisions[0].accepted == decisions[1].accepted,
                              "same_reason": decisions[0].reason == decisions[1].reason})
    assert all(row["same_class"] and row["same_threshold_decision"] for row in scores)
    assert all(row["same_decision"] and row["same_reason"] for row in sequences)
    summary = {}
    for backend in ("pytorch", "onnx"):
        rows = [row for row in measurements if row["backend"] == backend]
        summary[backend] = {key: statistics.median(row[key] for row in rows) for key in (
            "cold_import_and_model_ms", "median_predict_ms", "p95_predict_ms", "cpu_ms_per_predict",
            "installed_package_bytes",
        )}
        summary[backend]["memory"] = {key: statistics.median(row["memory"][key] for row in rows)
                                       for key in rows[0]["memory"]} if rows[0]["memory"] else None
    manifest_path = ROOT / "gatekeeper" / MODEL_RELATIVE_DIR / f"{MODEL_STEM}.fp32.json"
    result = {"scope": "CPU FP32 parity/performance; public demo images and synthetic inputs only; no camera/API/DB",
              "threads": 2, "runs_per_backend": runs, "iterations_per_run": iterations,
              "samples": len(scores), "max_absolute_error": max(row["max_absolute_error"] for row in scores),
              "sequences": len(sequences), "accepted_sequences": sum(row["pytorch_accepted"] for row in sequences),
              "all_decisions_match": True, "summary": summary, "raw_measurements": measurements,
              "frame_comparison": scores, "sequence_comparison": sequences,
              "manifest": json.loads(manifest_path.read_text(encoding="utf-8"))}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("raw_measurements", "frame_comparison", "sequence_comparison", "manifest")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("pytorch", "onnx"))
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "output/gatekeeper-onnx/comparison.json")
    args = parser.parse_args()
    if args.iterations < 20 or args.runs < 1:
        parser.error("Use at least 20 iterations and one run.")
    if args.worker:
        worker(args.worker, args.iterations)
    else:
        compare(args.iterations, args.runs, args.output)
