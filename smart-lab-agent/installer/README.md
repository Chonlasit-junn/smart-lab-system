# Smart Lab Agent MSI

The MSI is built with Microsoft's **Visual Studio Installer Projects** extension. The installer provides two Windows entry points backed by one shared executable, which keeps the bundled Qt/Python runtime from being duplicated:

- **Register This Computer** signs in with an Admin account, loads active Labs, and registers this computer to the selected Lab.
- **Smart Lab Agent** uses that credential to report to the Backend and enforce the Lab policy.

The MSI is per-machine and defaults to `Program Files\Smart Lab\Device Agent`; the setup wizard lets the installer choose another destination. It adds the Agent and registration shortcuts under **Start → Smart Lab**, plus an **Uninstall Smart Lab Agent** shortcut and a standard entry in Windows Apps/Programs. The installer also offers a checkbox to add both app shortcuts to the Desktop, selected by default. It does not register a Windows service or start the Agent automatically. The Agent is a desktop application and must run in the signed-in Lab Windows session.

## Registering a Lab computer

1. Install the MSI with an account that has permission to install software.
2. Sign in to the Windows account that will be used on that computer. The supported setup is one shared Windows account per Lab PC.
3. Open **Start → Smart Lab → Register This Computer**, enter the Backend URL, Admin email and password, then select **Load Labs**. Choose the target Lab and enter a descriptive computer name.
4. Select **Register Computer**. The password is cleared after sign-in, the Admin access token is kept in memory only, and after registration succeeds open **Start → Smart Lab → Smart Lab Agent**.

The MSI does not contain Admin credentials. The returned device token is saved for the signed-in Windows account under `%LOCALAPPDATA%\SmartLabAgent\device_registration.json`. Keep that file private; it grants this workstation access to the Agent API. Register each physical computer separately. The Backend must include the Admin-authenticated `POST /admin/lab-devices/register` endpoint before using this version of the registration utility.

The Backend URL saved with the device credential is used by the Agent. `SMART_LAB_API_URL`, if set on the Windows account, intentionally overrides the saved URL.

## Usage and violation delivery

The Agent checkpoints a running application's usage every 30 seconds into its
SQLite outbox. On a crash, completed checkpoints survive; the most recent partial
interval can still be lost. At the end of a warning, it checks whether the detected
application is still present before ending the session.

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

## Chrome and Edge website rules

Add a **Website** rule in Admin Blacklist using a domain such as `example.com`.
The rule includes subdomains but not lookalikes such as `example.com.evil.com`.
With operator approval, apply `backend/migrations/013_website_domain_policy.sql`
before creating these rules; deploy Backend before distributing this Agent.

The MSI includes the URL reader. It uses the Windows PowerShell/.NET UI Automation
components already installed on Windows 10/11, with one hidden, persistent helper
and one bounded background worker. No browser extension or extra Python package
is required. Environments that disable Windows PowerShell or UI Automation cannot
use website detection. The reader does not change execution policy, browser flags,
permissions, clipboard, keyboard focus or security settings.

Only the active tab in a foreground Chrome/Edge window is sampled, on the existing
five-second monitor timer. Warning rechecks target the original browser window.
Only the domain is sent with violations; paths, queries, fragments and page titles
are not sent as URL evidence. This is policy detection, not a network firewall or
a record of all browser tabs/history. Brief visits between samples may be missed.
Inaccessible/hidden address bars, full-screen mode and an address bar currently
being edited produce no evidence, not a guessed violation. Browser updates and
different Windows/browser versions need compatibility testing on a Lab PC.

Program and website rules share the existing warning, grace, durable outbox,
signed-policy validation and idempotent point handling. On logout/exit the URL
helper is closed. This feature does not change device registration or lab login.

### Domain contract v1

Frontend, Backend and Agent use Unicode 16 UTS #46 non-transitional mapping.
`faß.de` becomes `xn--fa-hia.de`, not `fass.de`; Thai, Chinese, Emoji and existing
Punycode names use the same canonical ASCII domain. Invalid Punycode, Bidi/Joiner
sequences, credentials, percent-encoded hosts and wildcard rules are rejected.
Only one trailing DNS dot is stripped. Single-label non-IP hosts are unsupported.

IPv4 browser aliases such as `127.1`, `0177.0.0.1` and `0x7f000001` become
`127.0.0.1`. IPv6 is bracketed/compressed, with IPv4-mapped addresses rendered as
hexadecimal, e.g. `[::ffff:c000:201]`. Ports are validated then discarded. IP rules
match exactly, never as domain suffixes. No paths, queries or fragments persist.

The Python module `domain_normalization.py` is mirrored in Backend and Agent
because each is deployed independently. A test compares the copies byte-for-byte.
Both pin `idna==3.11`; Python older than 3.14 also bundles Unicode 16 data via
`unicodedata2`. Frontend pins `tr46==5.1.1`, loaded only with the Blacklist page.
These runtime dependencies are included in the MSI; Lab users install nothing else.

Shared expected results are in `tests/fixtures/domain-contract.json`. From the
repository root, after installing the normal project dependencies, run:

```powershell
.\smart-lab-agent\venv\Scripts\python.exe -B scripts/check_domain_contract.py
```

This offline check compares the real JS frontend, Backend Python and Agent Python
over the same synthetic cases, including form payloads and idempotence. It makes
no network requests, creates no production rules and cannot deduct real points.
Existing persisted rules are not automatically rewritten. Rebuild/distribute the
MSI after changing this contract; updating the website does not update Lab PCs.

## Build the MSI

Build on Windows for the target architecture. The build machine needs:

- Python environment `smart-lab-agent\venv` with the runtime requirements installed.
- PyInstaller 6.20.0 in that environment (`python -m pip install pyinstaller==6.20.0`).
- Visual Studio 2022 or Visual Studio 2026 with the official [Microsoft Visual Studio Installer Projects extension](https://marketplace.visualstudio.com/items?itemName=VisualStudioClient.MicrosoftVisualStudio2022InstallerProjects).

From the repository root, run:

```powershell
.\smart-lab-agent\installer\build_msi.ps1 -Version 1.0.0
```

If command-line Visual Studio reports invalid license data but IDE builds work,
add `-UseVisualStudioAutomation`. This uses a new hidden IDE instance to build the
same project and applies the same shortcut validation; it does not repair/update
Visual Studio or modify registry settings.

The default uses `smart-lab-agent\venv\Scripts\python.exe`. A different Python may be selected with `-PythonPath`, but it must have the project runtime dependencies and PyInstaller 6.20.0 installed.

If the runtime dependencies are already installed in the project virtual environment, install the build dependency there with:

```powershell
.\smart-lab-agent\venv\Scripts\python.exe -m pip install -r .\smart-lab-agent\requirements-build.txt
```

The script packages the shared Agent/registration entry point as a self-contained, one-file executable, generates a temporary Visual Studio Setup Project from `SmartLabAgent.vdproj.template`, and invokes `devenv.com` to create the MSI. The registration shortcut launches the same executable with the internal `--register` argument. It does not install Visual Studio or the extension, and it does not make registry changes. Microsoft documents that command-line builds of `.vdproj` projects may require running Visual Studio's `DisableOutOfProcBuild.exe` once for the same Windows account; see the [Microsoft build instructions](https://learn.microsoft.com/en-us/visualstudio/ide/reference/build-devenv-exe?view=visualstudio#build-a-setup-project).

Packaging runs Python in isolated mode and temporarily restricts the build process's
`PATH` to Windows and the selected Python runtime. This prevents unrelated tools
such as Poppler/Conda from supplying incompatible ICU DLLs. The original `PATH`
is restored before Visual Studio runs, including when packaging fails; no user or
machine environment settings are changed. The application continues using the
Windows system ICU as configured in `qt_runtime.py`. Python, Qt, Tcl/Tk, software
OpenGL, TLS certificates and the URL reader remain included; no optional runtime
components are removed to meet the size target. Target machines still require
the supported Windows 10/11 environment, not a separate Python/Qt installation.
The build rejects MSI output of 50,000,000 bytes or larger (decimal 50 MB),
including installer-only rebuilds, to catch future packaging size regressions.

For an installer-only rebuild using an already-built, verified shared executable, pass the directory containing `SmartLabDevice.exe` with `-PrebuiltPayloadPath`; this skips PyInstaller but still creates a new MSI:

```powershell
.\smart-lab-agent\installer\build_msi.ps1 -Version 1.1.1 -PrebuiltPayloadPath 'C:\build-output\payload'
```

Build files are placed in ignored `smart-lab-agent\build_msi\` and `smart-lab-agent\dist_msi\` directories. Each run uses a timestamped directory and does not overwrite an earlier MSI. This project does not include a code-signing certificate; production distribution should sign the MSI and executables with the organization's certificate. An unsigned build may trigger Windows reputation or SmartScreen warnings.
