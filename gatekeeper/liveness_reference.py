"""Development/export only: reuse the vendored PyTorch predictor for parity."""

from pathlib import Path
import sys

from liveness_runtime import MODEL_RELATIVE_DIR, MODEL_STEM, inference_threads


def load_torch_reference(base_dir):
    import torch

    torch.set_num_threads(inference_threads())
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    repo = Path(base_dir) / "Silent-Face-Anti-Spoofing"
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from src.anti_spoof_predict import AntiSpoofPredict

    # The kiosk supplies Haar face crops. Skip the unused Caffe detector and
    # its process-global chdir; retain the original weight loader and predict.
    predictor = AntiSpoofPredict.__new__(AntiSpoofPredict)
    predictor.device = torch.device("cpu")
    predictor.model = None
    predictor.model_path = None
    predictor.load_model(str(Path(base_dir) / MODEL_RELATIVE_DIR / f"{MODEL_STEM}.pth"))
    return predictor
