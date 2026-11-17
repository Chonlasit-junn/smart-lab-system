# Smart Lab Agent MSI

The MSI is built with Microsoft's **Visual Studio Installer Projects** extension. The installer provides two Windows entry points backed by one shared executable, which keeps the bundled Qt/Python runtime from being duplicated:

- **Register This Computer** signs in with an Admin account, loads active Labs, and registers this computer to the selected Lab.
- **Smart Lab Agent** uses that credential to report to the Backend and enforce the Lab policy.

The MSI is per-machine and defaults to `Program Files\Smart Lab\Device Agent`; the setup wizard lets the installer choose another destination. It adds the Agent and registration shortcuts under **Start → Smart Lab**, plus an **Uninstall Smart Lab Agent** shortcut and a standard entry in Windows Apps/Programs. The installer also offers a checkbox to add both app shortcuts to the Desktop, selected by default. The Agent opens at Windows sign-in and returns to its own full-screen login lock when a Lab Session ends. It does not log off Windows and is not a Windows service; the face scanner does not auto-start.

## Registering a Lab computer

1. Install the MSI with an account that has permission to install software.
2. Sign in to the Windows account that will be used on that computer. The supported setup is one shared Windows account per Lab PC.
3. Open **Start → Smart Lab → Register This Computer**, enter the Backend URL, Admin email and password, then select **Load Labs**. Choose the target Lab and enter a descriptive computer name.
4. Select **Register Computer**. The password is cleared after sign-in, the Admin access token is kept in memory only, and after registration succeeds open **Start → Smart Lab → Smart Lab Agent**.

The MSI does not contain Admin credentials. The returned device token is saved for the signed-in Windows account under `%LOCALAPPDATA%\SmartLabAgent\device_registration.json`. Keep that file private; it grants this workstation access to the Agent API. Register each physical computer separately. The Backend must include the Admin-authenticated `POST /admin/lab-devices/register` endpoint before using this version of the registration utility.

The Backend URL saved with the device credential is used by the Agent. `SMART_LAB_API_URL`, if set on the Windows account, intentionally overrides the saved URL.

## Recover the Agent after End task

Install the Agent MSI, then start the Agent from the shared Windows account used
in the Lab. After the registered Agent successfully checks its control state,
it creates its recovery task for that account with normal privileges. It keeps
an existing task as configured, including a task disabled by an administrator.
See `%LOCALAPPDATA%\SmartLabAgent\agent-recovery-task.log` for setup results.

If the workstation policy prevents a standard user from creating tasks, the
administrator can register the task with the companion script. Pass the shared
Windows account and use `-AgentPath` for a custom installation directory.

```powershell
.\Register-AgentRecoveryTask.ps1 -LabWindowsUser 'LAB-PC\LabUser'
```

The visible **Smart Lab Agent Recovery** task checks at sign-in and every minute
while that account is signed in. It runs with that account's normal privileges.
The MSI creates the usual sign-in entry on its own. Admins can manage the
recovery task in Windows Task Scheduler.

The Agent ignores window-close requests on the login and session windows. When
it restarts with an interrupted session, it shows its login lock, checks the
device's control state, ends the stale session through the outbox, and cleans
using the saved pre-session Downloads snapshot. A confirmed Admin maintenance
pause skips cleanup. If the Backend is unreachable during recovery, the login
window stays locked until the Agent can check the device state.

## Usage and violation delivery

The Agent checkpoints a running application's usage every 30 seconds into its
SQLite outbox. On a crash, completed checkpoints survive; the most recent partial
interval can still be lost. At the end of a warning, it checks whether the detected
application is still present before ending the session.

Session cleanup is enabled by default on the Agent MSI. When a Lab Session ends,
the Agent shows its login lock first, then closes applications owned by the current
Windows user, clears browser cookies, saved logins, history and session/cache data,
and deletes only files newly created in Downloads during that Lab Session. Browser
bookmarks, extensions and settings are preserved. Admin maintenance pauses skip
cleanup. This is an Agent window lock, not the Windows secure sign-in screen.
The Agent records cleanup counts and error categories in `session-cleanup.log`
in its local data directory (normally `%LOCALAPPDATA%\SmartLabAgent`).

After a session starts, the Agent synchronizes UTC time from the Backend and
advances that clock using Windows' monotonic timer. Changing the workstation's
date or time during a session therefore does not move usage or violation log
timestamps. Successful heartbeats refresh the time anchor. Rebuild and install
the Agent for this behavior; older installed builds continue using the local clock.

Deploy the Backend update before distributing the updated Agent. The policy API
now supplies a signed rule snapshot, which the Agent caches and attaches to queued
violations with their original UTC detection time. This lets the Backend validate
events after the blacklist changes, without a database migration. Keep the Backend
signing key stable while old outbox events are pending. Unsigned fallback policies
still require a match against current rules.

Enforcement now uses embedded EXE version metadata (OriginalFilename, InternalName,
or an exact ProductName fallback), not window titles or the observed filename.
Renaming a Notepad document or copying Notepad to `StarRail.exe` does not identify
it as a game. Legacy `process_name_or_title` rules use EXE identity only;
`window_title` rules no longer trigger penalties and need an executable-based
replacement. Unreadable files or files without usable metadata are not guessed
from their names. Metadata is not a cryptographic signature and does not protect
against deliberately modified binaries. Backend acknowledges old violations with
no executable identity without recording them or deducting points. Deploy Backend
first and rebuild/distribute the Agent; existing MSI files are not updated by a
source change.

## Program blacklist

The Agent checks blocked programs by executable identity. Deploy the Backend to
stop sending legacy website rules, then install the updated MSI on each Lab PC
to remove the browser URL reader. Previously recorded violations remain in reports.

## Build the MSI

Build on Windows for the target architecture. The build machine needs:

- Python environment `smart-lab-agent\venv` with the runtime requirements installed.
- PyInstaller 6.20.0 in that environment (`python -m pip install pyinstaller==6.20.0`).
- Visual Studio 2022 or Visual Studio 2026 with the official [Microsoft Visual Studio Installer Projects extension](https://marketplace.visualstudio.com/items?itemName=VisualStudioClient.MicrosoftVisualStudio2022InstallerProjects).

The same builder can create the standalone Gatekeeper MSI. It uses
`gatekeeper\.venv` and the current `smart_gatekeeper.spec` with ONNX Runtime,
the bundled FP32 model, camera startup improvements, and the scanner registration
flow. The Gatekeeper MSI installs separately under `Smart Lab\Face Scanner`.

```powershell
# Isolated QA Agent; booking and access checks remain enabled
.\smart-lab-agent\installer\build_msi.ps1 -Product Agent -Version 1.1.14 -QaAgent

# Standalone face scanner
.\smart-lab-agent\installer\build_msi.ps1 -Product Gatekeeper -Version 1.0.0
```

The QA installer provides a **Register QA Agent** shortcut. It launches the
registration wizard in the same isolated QA data directory used by the QA Agent,
so the device credential saved after registration is visible to that Agent. The
QA Agent uses a separate local data directory from the regular Agent.
Registration state and outbox data are kept separately under
`%LOCALAPPDATA%\SmartLabAgentQA\SmartLabAgent`, so installing it beside a
regular Agent does not replace that Agent's saved device credential. QA sessions
must meet the same booking time-window, user approval, active Lab, registered
device, and ban checks as regular sessions. The QA build does not bypass booking
time or other access policies.
The QA Agent writes monitor exception timestamps and exception types only to
`%LOCALAPPDATA%\SmartLabAgentQA\SmartLabAgent\monitor-errors.log`.
Agent build version is embedded from `-Version`. Windows logoff is not performed;
the Agent ends its Lab Session and shows its own full-screen login lock instead.
`SMART_LAB_AGENT_DEBUG` can still override debug behavior per Windows account.

Gatekeeper registers a distinct `gatekeeper-…` device against its selected Lab
and stores its credential in the current Windows user's LocalAppData. Migration
017 (`backend/migrations/017_gatekeeper_scan_logs.sql`) must be applied to the
target QA database before scan-history logging can be tested; this build does not
run migrations. Verify the packaged face runtime without opening a camera or
calling the Backend with:

```powershell
& '.\gatekeeper\dist_msi\<build-folder>\payload\SmartGatekeeper.exe' `
  --liveness-self-test "$env:TEMP\gatekeeper-self-test.json"
```

From the repository root, run:

```powershell
.\smart-lab-agent\installer\build_msi.ps1 -Version 1.0.0
```

If command-line Visual Studio reports invalid license data but IDE builds work,
add `-UseVisualStudioAutomation`. This uses a new hidden IDE instance to build the
same project and applies the same shortcut validation; it does not repair/update
Visual Studio or modify registry settings.

The Agent default uses `smart-lab-agent\venv\Scripts\python.exe`; Gatekeeper uses `gatekeeper\.venv\Scripts\python.exe`. A different Python may be selected with `-PythonPath`, but it must have the product runtime dependencies and PyInstaller 6.20.0 installed.

If the runtime dependencies are already installed in the project virtual environment, install the build dependency there with:

```powershell
.\smart-lab-agent\venv\Scripts\python.exe -m pip install -r .\smart-lab-agent\requirements-build.txt
.\gatekeeper\.venv\Scripts\python.exe -m pip install -r .\gatekeeper\requirements-build.txt
```

The script packages the selected product as a self-contained, one-file executable, generates a temporary Visual Studio Setup Project from `SmartLabAgent.vdproj.template`, and invokes Visual Studio to create the MSI. Each product has its own upgrade identity, installation folder, Start Menu/Desktop shortcuts, and uninstall entry. Microsoft documents that command-line builds of `.vdproj` projects may require running Visual Studio's `DisableOutOfProcBuild.exe` once for the same Windows account; see the [Microsoft build instructions](https://learn.microsoft.com/en-us/visualstudio/ide/reference/build-devenv-exe?view=visualstudio#build-a-setup-project).

Packaging runs Python in isolated mode and temporarily restricts the build process's
`PATH` to Windows and the selected Python runtime. This prevents unrelated tools
such as Poppler/Conda from supplying incompatible ICU DLLs. The original `PATH`
is restored before Visual Studio runs, including when packaging fails; no user or
machine environment settings are changed. The application continues using the
Windows system ICU as configured in `qt_runtime.py`. Python, Qt, Tcl/Tk, software
OpenGL, TLS certificates and the URL reader remain included; no optional runtime
components are removed to meet the size target. Target machines still require
the supported Windows 10/11 environment, not a separate Python/Qt installation.
The Agent build rejects MSI output of 50,000,000 bytes or larger (decimal 50 MB),
including installer-only rebuilds, to catch future packaging size regressions.
Gatekeeper includes its camera, ONNX Runtime, and face model, so it uses its own
larger standalone package and is not subject to the Agent's 50 MB limit.

For an installer-only rebuild using an already-built, verified shared executable, pass the directory containing `SmartLabDevice.exe` with `-PrebuiltPayloadPath`; this skips PyInstaller but still creates a new MSI:

```powershell
.\smart-lab-agent\installer\build_msi.ps1 -Version 1.1.1 -PrebuiltPayloadPath 'C:\build-output\payload'
```

Build files are placed in ignored `smart-lab-agent\build_msi\` and `smart-lab-agent\dist_msi\` directories. Standard Agent builds go under `dist_msi\agent\`, and QA Agent builds go under `dist_msi\qa\`; each uses a timestamped directory and does not overwrite an earlier MSI. When a QA version is retired, move its release folder to `dist_msi\archive\qa\` and its intermediate build folder to `build_msi\qa-archive\builds\`. New QA builds continue to use `dist_msi\qa\`. Gatekeeper builds remain under its separate `gatekeeper\dist_msi\` directory. This project does not include a code-signing certificate; production distribution should sign the MSI and executables with the organization's certificate. An unsigned build may trigger Windows reputation or SmartScreen warnings.
