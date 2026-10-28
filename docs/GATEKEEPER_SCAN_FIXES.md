# Gatekeeper scan reliability — 2026-10-28

This source update addresses the five scan audit findings. It does not migrate
data, regenerate existing face embeddings, deploy services, or replace an EXE.

## Capture and detection

- Use the already bundled upstream Caffe face detector through OpenCV DNN,
  preserving aspect ratio. Retain every detection above the upstream 0.6
  confidence threshold, including a second person; do not select only argmax.
  The detector's own NMS handles duplicate proposals. The packaging spec now
  includes both detection assets. No dependency or liveness weights changed.
- Collect five distinct, fresh, single-person frames within three seconds.
  Retry missed detections; reject multiple people or a large tracking jump.
  Camera sequence/generation/freshness prevent reusing a frozen or old frame.
- Keep the first five liveness scores, requiring four at least 0.72. Do not
  replace low scores with later favorable predictions. Additional frames can
  provide time for the motion cue, but cannot replace those five scores.
- Track facial texture in raw frames using forward/backward optical flow.
  Require displacement of at least 2% of face size in two distinct frames.
  Brightness and recentered crop differences no longer count as movement.
  This is supplementary motion evidence, not an independent anti-spoof proof.
- Match the upstream 2.7x crop edge handling. Mirror only the UI preview;
  inference and uploads use the original camera orientation.

## Enrollment and access

Enrollment applies EXIF orientation and uses an image up to 1024x1024 for
Facenet; saved avatars remain at most 200x200. Enrollment and scan share explicit
Facenet/OpenCV/alignment options and require exactly one face, at least 40 pixels
on each side. Invalid photos do not create accounts or consume valid OTPs.
Existing embeddings remain untouched; poor existing enrollment photos may still
need recapture through a separately authorized account update.

The Backend independently validates the face count; it does not trust the
client's count or select the first face. Camera credentials, active Lab, current
Bangkok booking, Guest approval, inactive accounts, Ban, and committing scan
history before granting remain mandatory. Face matching distance stays 0.40.

## Feedback

Capture failures have distinct audit reason codes for missing samples, no
motion, subject change and multiple faces. The kiosk distinguishes retry,
service unavailable and access denied, and wraps long text. Enrollment errors
are translated in Thai/English without returning users to the OTP step.

## Regression verification

Executed successfully on 2026-10-28: Gatekeeper 73 tests, Backend Gatekeeper 43,
registration OTP 29, frontend registration 6 (151 total). Targeted frontend
ESLint and `git diff --check` also passed. CustomTkinter reported a font-shape
fallback warning in the test environment; actual kiosk rendering needs QA.

Main implementation files: `gatekeeper/face_capture.py`,
`gatekeeper/liveness_capture.py`, `gatekeeper/liveness_policy.py`,
`gatekeeper/camera_stream.py`, `gatekeeper/smart_gatekeeper.py`,
`gatekeeper/access_client.py`, `gatekeeper/smart_gatekeeper.spec`,
`backend/face_service.py`, `backend/routers/auth.py`,
`backend/routers/gatekeeper.py`, and the frontend registration locale/error
helpers. Corresponding tests were added/updated; unrelated pending Agent and
frontend layout edits were preserved.

From `gatekeeper/`:

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -s tests
```

From `backend/` (tests use isolated SQLite and mock external services):

```powershell
$env:SQLALCHEMY_DATABASE_URL = 'sqlite:///:memory:'
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_gatekeeper*.py'
.\venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_registration_otp.py'
```

From `frontend/`:

```powershell
node --test tests/registrationOtp.test.js
node node_modules/eslint/bin/eslint.js src/utils/registrationOtp.js src/utils/locales.js tests/registrationOtp.test.js
```

Coverage includes the public one-face/duplicate-Haar reproduction, a composed
two-face scene, distinct overlapping detection boxes, missing/repeated/stale
frames, motion vs brightness, cancellation, low liveness scores, actual ONNX
predictions followed by Backend denials, Booking/Guest/Ban, registration cleanup
and OTP preservation. Public/synthetic fixtures are not a measured field false
accept/reject rate. QA still needs the installed camera, real two-person scenes,
and photo/screen replay checks before release.
