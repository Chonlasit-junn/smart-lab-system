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

## Build the MSI

Build on Windows for the target architecture. The build machine needs:

- Python environment `smart-lab-agent\venv` with the runtime requirements installed.
- PyInstaller 6.20.0 in that environment (`python -m pip install pyinstaller==6.20.0`).
- Visual Studio 2022 or Visual Studio 2026 with the official [Microsoft Visual Studio Installer Projects extension](https://marketplace.visualstudio.com/items?itemName=VisualStudioClient.MicrosoftVisualStudio2022InstallerProjects).

From the repository root, run:

```powershell
.\smart-lab-agent\installer\build_msi.ps1 -Version 1.0.0
```

The default uses `smart-lab-agent\venv\Scripts\python.exe`. A different Python may be selected with `-PythonPath`, but it must have the project runtime dependencies and PyInstaller 6.20.0 installed.

If the runtime dependencies are already installed in the project virtual environment, install the build dependency there with:

```powershell
.\smart-lab-agent\venv\Scripts\python.exe -m pip install -r .\smart-lab-agent\requirements-build.txt
```

The script packages the shared Agent/registration entry point as a self-contained, one-file executable, generates a temporary Visual Studio Setup Project from `SmartLabAgent.vdproj.template`, and invokes `devenv.com` to create the MSI. The registration shortcut launches the same executable with the internal `--register` argument. It does not install Visual Studio or the extension, and it does not make registry changes. Microsoft documents that command-line builds of `.vdproj` projects may require running Visual Studio's `DisableOutOfProcBuild.exe` once for the same Windows account; see the [Microsoft build instructions](https://learn.microsoft.com/en-us/visualstudio/ide/reference/build-devenv-exe?view=visualstudio#build-a-setup-project).

For an installer-only rebuild using an already-built, verified shared executable, pass the directory containing `SmartLabDevice.exe` with `-PrebuiltPayloadPath`; this skips PyInstaller but still creates a new MSI:

```powershell
.\smart-lab-agent\installer\build_msi.ps1 -Version 1.1.1 -PrebuiltPayloadPath 'C:\build-output\payload'
```

Build files are placed in ignored `smart-lab-agent\build_msi\` and `smart-lab-agent\dist_msi\` directories. Each run uses a timestamped directory and does not overwrite an earlier MSI. This project does not include a code-signing certificate; production distribution should sign the MSI and executables with the organization's certificate. An unsigned build may trigger Windows reputation or SmartScreen warnings.
