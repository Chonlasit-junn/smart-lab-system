param(
    [string]$Version = "1.0.0",
    [string]$PythonPath = "",
    [string]$PrebuiltPayloadPath = "",
    [ValidateSet("Agent", "Gatekeeper")]
    [string]$Product = "Agent",
    [switch]$QaAgent,
    [switch]$UseVisualStudioAutomation
)

$ErrorActionPreference = "Stop"

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version must use the format Major.Minor.Patch, for example 1.0.0."
}
foreach ($part in $Version.Split('.')) {
    if ([int]$part -gt 255) {
        throw "Each MSI version part must be 255 or less."
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$agentRoot = Join-Path $repoRoot "smart-lab-agent"
$gatekeeperRoot = Join-Path $repoRoot "gatekeeper"
$projectRoot = if ($Product -eq "Gatekeeper") { $gatekeeperRoot } else { $agentRoot }
$isQaAgent = $Product -eq "Agent" -and $QaAgent.IsPresent
if ($QaAgent -and $Product -ne "Agent") {
    throw "-QaAgent is only valid when building the Agent product."
}

$appExeName = if ($Product -eq "Gatekeeper") { "SmartGatekeeper.exe" } else { "SmartLabDevice.exe" }
$appDisplayName = if ($Product -eq "Gatekeeper") { "Smart Lab Gatekeeper" } elseif ($isQaAgent) { "Smart Lab Agent QA" } else { "Smart Lab Agent" }
$registerShortcutName = if ($Product -eq "Gatekeeper") { "Register This Scanner" } elseif ($isQaAgent) { "Register QA Agent" } else { "Register This Computer" }
$registerShortcutArguments = if ($isQaAgent) { "--qa --register" } else { "--register" }
$productName = if ($Product -eq "Gatekeeper") { "Smart Lab Face Scanner" } elseif ($isQaAgent) { "Smart Lab Agent QA" } else { "Smart Lab Device Agent" }
$productComments = if ($Product -eq "Gatekeeper") { "Registers this computer as a face scanner and verifies lab access." } elseif ($isQaAgent) { "Isolated QA Agent build. Uses the same booking and access checks as the regular Agent." } else { "Registers this computer and runs the Smart Lab Agent." }
$installFolder = if ($Product -eq "Gatekeeper") { "Smart Lab\Face Scanner" } elseif ($isQaAgent) { "Smart Lab\Agent QA" } else { "Smart Lab\Device Agent" }
$buildVariant = if ($Product -eq "Gatekeeper") { "gatekeeper" } elseif ($isQaAgent) { "qa" } else { "agent" }
$installerProjectName = if ($Product -eq "Gatekeeper") { "SmartGatekeeperInstaller" } else { "SmartLabAgentInstaller" }
$registryBasePath = if ($Product -eq "Gatekeeper") { "Software\Smart Lab\Face Scanner" } elseif ($isQaAgent) { "Software\Smart Lab\Agent QA" } else { "Software\Smart Lab\Device Agent" }
$upgradeCode = if ($Product -eq "Gatekeeper") { "{6E77A21F-69D9-4D82-90D0-52BDF4F0C571}" } elseif ($isQaAgent) { "{87B146E3-9F71-4610-9D5A-E3D72384D8C9}" } else { "{78B9A7C1-A3F4-4D82-974A-A7A69E9121CC}" }

$componentIds = if ($Product -eq "Gatekeeper") {
    @{ Desktop = "{B119D16C-425B-43DD-9F29-32D1C7D05011}"; Register = "{B119D16C-425B-43DD-9F29-32D1C7D05012}"; Uninstall = "{B119D16C-425B-43DD-9F29-32D1C7D05013}" }
} elseif ($isQaAgent) {
    @{ Desktop = "{8E5A1D66-83A1-4E20-AF36-03720862A021}"; Register = "{8E5A1D66-83A1-4E20-AF36-03720862A022}"; Uninstall = "{8E5A1D66-83A1-4E20-AF36-03720862A023}" }
} else {
    @{ Desktop = "{C41B79CE-2E28-41BD-B743-7607AB300021}"; Register = "{C41B79CE-2E28-41BD-B743-7607AB300022}"; Uninstall = "{C41B79CE-2E28-41BD-B743-7607AB300023}" }
}
$primaryShortcutArguments = if ($isQaAgent) { "--qa" } else { "" }

$usePrebuiltPayload = -not [string]::IsNullOrWhiteSpace($PrebuiltPayloadPath)
$python = $null
$resolvedPrebuiltPayloadPath = $null
if ($usePrebuiltPayload) {
    $resolvedPrebuiltPayloadPath = (Resolve-Path -LiteralPath $PrebuiltPayloadPath).Path
    if (-not (Test-Path -LiteralPath $resolvedPrebuiltPayloadPath -PathType Container)) {
        throw "Prebuilt payload directory not found at '$resolvedPrebuiltPayloadPath'."
    }
} else {
    $python = if ($PythonPath) {
        (Resolve-Path -LiteralPath $PythonPath).Path
    } else {
        Join-Path $projectRoot $(if ($Product -eq "Gatekeeper") { ".venv\Scripts\python.exe" } else { "venv\Scripts\python.exe" })
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Project Python environment not found at '$python'."
    }
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
$devenv = $null
if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
    $vsPath = & $vswhere -latest -products * -property installationPath
    if ($LASTEXITCODE -eq 0 -and $vsPath) {
        $candidate = Join-Path $vsPath "Common7\IDE\devenv.com"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $devenv = $candidate
        }
    }
}
if (-not $devenv) {
    $command = Get-Command devenv.com -ErrorAction SilentlyContinue
    if ($command) {
        $devenv = $command.Source
    }
}
if (-not $devenv) {
    throw "Microsoft Visual Studio 2022 or 2026 with the Microsoft Visual Studio Installer Projects extension is required to build this MSI."
}

$vsiDirectory = Join-Path (Split-Path $devenv -Parent) "CommonExtensions\Microsoft\VSI"
if (-not (Test-Path -LiteralPath $vsiDirectory -PathType Container)) {
    throw "The Microsoft Visual Studio Installer Projects extension is not installed for this Visual Studio instance. Install the official extension, then retry."
}

if (-not $usePrebuiltPayload) {
    $dependencyCheck = if ($Product -eq "Gatekeeper") {
        "import PyInstaller; assert PyInstaller.__version__ == '6.20.0'; import cv2, numpy, onnxruntime, customtkinter, PIL, requests"
    } else {
        "import PyInstaller; assert PyInstaller.__version__ == '6.20.0'; import PyQt6, psutil, requests, pygetwindow"
    }
    & $python -B -c $dependencyCheck
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 6.20.0 and the project runtime dependencies are required. Install with: `"$python`" -m pip install -r requirements-build.txt"
    }
}

$buildId = "{0}-{1}-{2}" -f $Version, $buildVariant, (Get-Date -Format "yyyyMMdd-HHmmss")
$buildRoot = Join-Path $projectRoot "build_msi\$buildId"
$payloadRoot = Join-Path $buildRoot "payload"
$distRoot = Join-Path $projectRoot "dist_msi"
if ($Product -eq "Agent") {
    $distributionKind = if ($isQaAgent) { "qa" } else { "agent" }
    $distRoot = Join-Path $distRoot $distributionKind
}
$distRoot = Join-Path $distRoot $buildId
$projectPath = Join-Path $buildRoot "$installerProjectName.vdproj"
$solutionPath = Join-Path $buildRoot "$installerProjectName.sln"
$buildLog = Join-Path $buildRoot "visualstudio-build.log"

New-Item -ItemType Directory -Path $payloadRoot, $distRoot, (Join-Path $buildRoot "pyinstaller-work\device"), (Join-Path $buildRoot "spec") -Force | Out-Null

if ($usePrebuiltPayload) {
    $prebuiltPayload = Join-Path $resolvedPrebuiltPayloadPath $appExeName
    if (-not (Test-Path -LiteralPath $prebuiltPayload -PathType Leaf)) {
        throw "Expected prebuilt application payload was not found: '$prebuiltPayload'."
    }
    Copy-Item -LiteralPath $prebuiltPayload -Destination $payloadRoot
} else {
    if ($Product -eq "Gatekeeper") {
        $deviceBuildArgs = @(
            "-I", "-B", "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", $payloadRoot,
            "--workpath", (Join-Path $buildRoot "pyinstaller-work\gatekeeper"),
            (Join-Path $projectRoot "smart_gatekeeper.spec")
        )
        $buildWorkingDirectory = $projectRoot
    } else {
        $deviceBuildArgs = @(
            "-I", "-B", "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
            "--name", "SmartLabDevice",
            "--distpath", $payloadRoot,
            "--workpath", (Join-Path $buildRoot "pyinstaller-work\device"),
            "--specpath", (Join-Path $buildRoot "spec"),
            (Join-Path $agentRoot "smart_lab_device.py")
        )
        $buildWorkingDirectory = $agentRoot
    }
    # Do not resolve Qt's Windows ICU dependency from unrelated tools on PATH
    # (e.g. Poppler/Conda). Those DLLs are both incompatible and much larger.
    # qt_runtime.py already pins the Windows system ICU in the installed app.
    $pythonRuntimeRoot = & $python -I -B -c "import sys; print(sys.base_prefix)"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonRuntimeRoot -PathType Container)) {
        throw "Could not resolve the Python runtime for the isolated build."
    }
    $originalBuildPath = $env:PATH
    try {
        $env:PATH = @(
            (Join-Path $env:SystemRoot 'System32'),
            $env:SystemRoot,
            (Split-Path $python -Parent),
            $pythonRuntimeRoot,
            (Join-Path $pythonRuntimeRoot 'DLLs')
        ) -join [System.IO.Path]::PathSeparator
        Push-Location $buildWorkingDirectory
        & $python @deviceBuildArgs
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller failed while packaging $Product (exit code $LASTEXITCODE)."
        }
    } finally {
        if ((Get-Location).Path -eq $buildWorkingDirectory) { Pop-Location }
        $env:PATH = $originalBuildPath
    }
}

$appExePath = Join-Path $payloadRoot $appExeName
if (-not (Test-Path -LiteralPath $appExePath -PathType Leaf)) {
    throw "Expected application payload was not created: '$appExePath'."
}

function ConvertTo-VdprojValue([string]$Value) {
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

$productHash = [System.Security.Cryptography.MD5]::Create()
try {
    $productIdentity = if ($Product -eq "Agent" -and -not $isQaAgent) {
        "SmartLabDeviceAgent:$Version"
    } else {
        "SmartLab:${Product}:${buildVariant}:$Version"
    }
    $productBytes = $productHash.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($productIdentity))
} finally {
    $productHash.Dispose()
}
$productCode = ([guid]::new($productBytes)).ToString('B').ToUpperInvariant()
$packageCode = [guid]::NewGuid().ToString('B').ToUpperInvariant()
$msiFileName = if ($Product -eq "Gatekeeper") { "SmartLabGatekeeper.msi" } elseif ($isQaAgent) { "SmartLabAgent-QA.msi" } else { "SmartLabAgent.msi" }
$msiPath = Join-Path $distRoot $msiFileName
$templatePath = Join-Path $PSScriptRoot "SmartLabAgent.vdproj.template"
$projectTemplate = Get-Content -LiteralPath $templatePath -Raw
$replacements = @{
    "__OUTPUT_MSI__" = ConvertTo-VdprojValue $msiPath
    "__APP_EXE_PATH__" = ConvertTo-VdprojValue $appExePath
    "__APP_EXE_NAME__" = $appExeName
    "__PRODUCT_CODE__" = $productCode
    "__PACKAGE_CODE__" = $packageCode
    "__VERSION__" = $Version
    "__PROJECT_NAME__" = $installerProjectName
    "__INSTALL_FOLDER__" = ConvertTo-VdprojValue $installFolder
    "__PRODUCT_NAME__" = $productName
    "__PRODUCT_COMMENTS__" = $productComments
    "__UPGRADE_CODE__" = $upgradeCode
    "__PRIMARY_SHORTCUT_NAME__" = $appDisplayName
    "__PRIMARY_SHORTCUT_ARGUMENTS__" = $primaryShortcutArguments
    "__REGISTER_SHORTCUT_NAME__" = $registerShortcutName
    "__REGISTER_SHORTCUT_ARGUMENTS__" = $registerShortcutArguments
}
foreach ($token in $replacements.Keys) {
    $projectTemplate = $projectTemplate.Replace($token, $replacements[$token])
}
if ($projectTemplate -match '__[A-Z_]+__') {
    throw "The Visual Studio installer template contains an unresolved replacement token."
}
Set-Content -LiteralPath $projectPath -Value $projectTemplate -Encoding UTF8

$projectGuid = "{E5520EAA-CCEF-4739-B75D-9FC6A866CC60}"
$solutionContent = @"
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 17
VisualStudioVersion = 17.0.31903.59
MinimumVisualStudioVersion = 10.0.40219.1
Project("{978C614F-708E-4E1A-B201-565925725DBA}") = "$installerProjectName", "$installerProjectName.vdproj", "$projectGuid"
EndProject
Global
	GlobalSection(SolutionConfigurationPlatforms) = preSolution
		Release|Any CPU = Release|Any CPU
	EndGlobalSection
	GlobalSection(ProjectConfigurationPlatforms) = postSolution
		${projectGuid}.Release|Any CPU.ActiveCfg = Release
		${projectGuid}.Release|Any CPU.Build.0 = Release
	EndGlobalSection
EndGlobal
"@
Set-Content -LiteralPath $solutionPath -Value $solutionContent -Encoding UTF8

$devenvArgs = @(
    $solutionPath,
    "/Build", "Release|Any CPU",
    "/Project", $projectPath,
    "/ProjectConfig", "Release",
    "/Out", $buildLog
)
if ($UseVisualStudioAutomation) {
    # Isolated hidden IDE instance: do not attach to or close the user's IDE.
    $ideVersion = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($devenv).FileMajorPart
    $dte = $null
    try {
        $dte = New-Object -ComObject "VisualStudio.DTE.$ideVersion.0"
        $dte.SuppressUI = $true
        $dte.MainWindow.Visible = $false
        $dte.Solution.Open($solutionPath)
        $dte.Solution.SolutionBuild.SolutionConfigurations.Item('Release').Activate()
        $dte.Solution.SolutionBuild.Build($true)
        if ($dte.Solution.SolutionBuild.LastBuildInfo -ne 0) {
            throw "Visual Studio automation reported MSI build errors."
        }
    } finally {
        if ($null -ne $dte) { $dte.Quit() }
    }
} else {
    & $devenv @devenvArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Visual Studio Installer Projects failed to build the MSI (exit code $LASTEXITCODE). See '$buildLog'. If this is a command-line license error, retry with -UseVisualStudioAutomation."
    }
}
if (-not (Test-Path -LiteralPath $msiPath -PathType Leaf)) {
    throw "Visual Studio reported success, but the expected MSI was not found at '$msiPath'."
}

# Visual Studio Installer Projects attaches shortcuts to the target EXE's
# component. Move Desktop shortcuts to dedicated components so the checkbox
# cannot accidentally suppress either installed application.
$installer = $null
$database = $null
$view = $null
try {
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $database = $installer.OpenDatabase($msiPath, 1)

    # This installer is per-machine (Program Files, HKLM markers, and shared
    # Lab PCs). ALLUSERS=2 can fall back to per-user context; force machine
    # context so DesktopFolder resolves to the shared desktop for all users.
    $view = $database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property`` = 'ALLUSERS'")
    $view.Execute()
    $record = $view.Fetch()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    if ($record) {
        $view = $database.OpenView("UPDATE ``Property`` SET ``Value`` = '1' WHERE ``Property`` = 'ALLUSERS'")
    } else {
        $view = $database.OpenView("INSERT INTO ``Property`` (``Property``, ``Value``) VALUES ('ALLUSERS', '1')")
    }
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    # Desktop shortcuts should be created by default, while remaining optional
    # through the installer's checkbox. Secure the public property so the
    # selected value survives the elevated per-machine install transaction.
    $view = $database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property`` = 'CREATE_DESKTOP_SHORTCUTS'")
    $view.Execute()
    $record = $view.Fetch()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    if ($record) {
        $view = $database.OpenView("UPDATE ``Property`` SET ``Value`` = '1' WHERE ``Property`` = 'CREATE_DESKTOP_SHORTCUTS'")
    } else {
        $view = $database.OpenView("INSERT INTO ``Property`` (``Property``, ``Value``) VALUES ('CREATE_DESKTOP_SHORTCUTS', '1')")
    }
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property`` = 'SecureCustomProperties'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record) {
        throw "The MSI is missing the SecureCustomProperties property."
    }
    $secureProperties = @($record.StringData(1) -split ';' | Where-Object { $_ })
    if ($secureProperties -notcontains 'CREATE_DESKTOP_SHORTCUTS') {
        $secureProperties += 'CREATE_DESKTOP_SHORTCUTS'
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $securePropertiesValue = $secureProperties -join ';'
    $view = $database.OpenView("UPDATE ``Property`` SET ``Value`` = '$securePropertiesValue' WHERE ``Property`` = 'SecureCustomProperties'")
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView('SELECT `Shortcut`, `Name` FROM `Shortcut` WHERE `Directory_` = ''DesktopFolder''')
    $view.Execute()

    $desktopShortcutIds = @{}
    while ($record = $view.Fetch()) {
        $shortcutId = $record.StringData(1)
        $shortcutName = ($record.StringData(2) -split '\|')[-1]
        if ($shortcutId -notmatch '^[A-Za-z0-9_]+$') {
            throw "Unexpected MSI identifier for a Desktop shortcut: '$shortcutId'."
        }
        if ($desktopShortcutIds.ContainsKey($shortcutName)) {
            throw "The MSI contains more than one Desktop shortcut named '$shortcutName'."
        }
        $desktopShortcutIds[$shortcutName] = $shortcutId
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $desktopShortcutDefinitions = @(
        @{
            Name = $appDisplayName
            FileName = $appExeName
            Arguments = $primaryShortcutArguments
            Component = 'SmartLabDesktopPrimaryShortcut'
            ComponentId = $componentIds.Desktop
            RegistryKeyPath = 'SmartLabDesktopPrimaryShortcutKeyPath'
            RegistryValue = 'DesktopPrimaryShortcut'
        },
        @{
            Name = $registerShortcutName
            FileName = $appExeName
            Arguments = $registerShortcutArguments
            Component = 'SmartLabDesktopRegisterShortcut'
            ComponentId = $componentIds.Register
            RegistryKeyPath = 'SmartLabDesktopRegisterShortcutKeyPath'
            RegistryValue = 'DesktopRegisterShortcut'
        }
    )

    if ($desktopShortcutIds.Count -ne $desktopShortcutDefinitions.Count) {
        throw "The MSI does not contain exactly the two expected Desktop shortcuts for $Product."
    }

    $view = $database.OpenView('SELECT `Name`, `Arguments` FROM `Shortcut`')
    $view.Execute()
    $registrationShortcutCount = 0
    while ($record = $view.Fetch()) {
        $shortcutName = ($record.StringData(1) -split '\|')[-1]
        if ($shortcutName -ne $registerShortcutName) {
            continue
        }
        $registrationShortcutCount++
        if ($record.StringData(2) -ne $registerShortcutArguments) {
            throw "The '$registerShortcutName' shortcut does not use the expected registration arguments."
        }
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null
    if ($registrationShortcutCount -ne 2) {
        throw "The MSI must contain Start Menu and Desktop '$registerShortcutName' shortcuts."
    }

    $fileKeysByName = @{}
    $view = $database.OpenView('SELECT `File`, `FileName` FROM `File`')
    $view.Execute()
    while ($record = $view.Fetch()) {
        $fileKey = $record.StringData(1)
        $fileName = ($record.StringData(2) -split '\|')[-1]
        if ($fileKeysByName.ContainsKey($fileName)) {
            throw "The MSI contains more than one file named '$fileName'."
        }
        $fileKeysByName[$fileName] = $fileKey
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    foreach ($definition in $desktopShortcutDefinitions) {
        if (-not $desktopShortcutIds.ContainsKey($definition.Name)) {
            throw "The MSI is missing the expected Desktop shortcut '$($definition.Name)'."
        }
        if (-not $fileKeysByName.ContainsKey($definition.FileName)) {
            throw "The MSI is missing the executable file '$($definition.FileName)' for the Desktop shortcut."
        }

        $component = $definition.Component
        $componentGuid = $definition.ComponentId
        $registryKeyPath = $definition.RegistryKeyPath
        $fileKey = $fileKeysByName[$definition.FileName]
        $shortcutId = $desktopShortcutIds[$definition.Name]
        $shortcutTarget = "[#${fileKey}]"
        # A null KeyPath makes DesktopFolder the component's key path. Since
        # that folder already exists, Windows Installer can treat the shortcut
        # component as already installed and skip creating its shortcut. Give
        # each shortcut component its own registry marker as its key path.
        $insertComponentSql = "INSERT INTO ``Component`` (``Component``, ``ComponentId``, ``Directory_``, ``Attributes``, ``Condition``, ``KeyPath``) VALUES ('$component', '$componentGuid', 'DesktopFolder', 4, 'CREATE_DESKTOP_SHORTCUTS=1', '$registryKeyPath')"
        $view = $database.OpenView($insertComponentSql)
        $view.Execute()
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null

        $registryValue = $definition.RegistryValue
        $insertRegistrySql = "INSERT INTO ``Registry`` (``Registry``, ``Root``, ``Key``, ``Name``, ``Value``, ``Component_``) VALUES ('$registryKeyPath', 2, '$registryBasePath', '$registryValue', '1', '$component')"
        $view = $database.OpenView($insertRegistrySql)
        $view.Execute()
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null

        $insertFeatureComponentSql = "INSERT INTO ``FeatureComponents`` (``Feature_``, ``Component_``) VALUES ('DefaultFeature', '$component')"
        $view = $database.OpenView($insertFeatureComponentSql)
        $view.Execute()
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null

        $updateShortcutSql = "UPDATE ``Shortcut`` SET ``Component_`` = '$component' WHERE ``Shortcut`` = '$shortcutId'"
        $view = $database.OpenView($updateShortcutSql)
        $view.Execute()
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null

        # These shortcuts are owned by shortcut-only components, so they must
        # be non-advertised and point directly to the installed EXE. An
        # advertised shortcut would require its owner component to contain the
        # target file as its key file.
        $updateTargetSql = "UPDATE ``Shortcut`` SET ``Target`` = '$shortcutTarget' WHERE ``Shortcut`` = '$shortcutId'"
        $view = $database.OpenView($updateTargetSql)
        $view.Execute()
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null

        $view = $database.OpenView("SELECT ``Condition``, ``Directory_``, ``Attributes``, ``KeyPath`` FROM ``Component`` WHERE ``Component`` = '$component'")
        $view.Execute()
        $record = $view.Fetch()
        if (-not $record -or $record.StringData(1) -ne 'CREATE_DESKTOP_SHORTCUTS=1' -or $record.StringData(2) -ne 'DesktopFolder' -or $record.IntegerData(3) -ne 4 -or $record.StringData(4) -ne $registryKeyPath) {
            throw "The MSI Desktop shortcut component '$component' did not pass validation."
        }
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null

        $view = $database.OpenView("SELECT ``Root``, ``Key``, ``Name``, ``Value``, ``Component_`` FROM ``Registry`` WHERE ``Registry`` = '$registryKeyPath'")
        $view.Execute()
        $record = $view.Fetch()
        if (-not $record -or $record.IntegerData(1) -ne 2 -or $record.StringData(2) -ne $registryBasePath -or $record.StringData(3) -ne $registryValue -or $record.StringData(4) -ne '1' -or $record.StringData(5) -ne $component) {
            throw "The MSI registry key path for Desktop shortcut component '$component' did not pass validation."
        }
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null

        $view = $database.OpenView("SELECT ``Component_``, ``Target``, ``Arguments`` FROM ``Shortcut`` WHERE ``Shortcut`` = '$shortcutId'")
        $view.Execute()
        $record = $view.Fetch()
        if (-not $record -or $record.StringData(1) -ne $component -or $record.StringData(2) -ne $shortcutTarget -or $record.StringData(3) -ne $definition.Arguments) {
            throw "The MSI Desktop shortcut '$($definition.Name)' was not assigned to its dedicated component or launch arguments."
        }
        $view.Close()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
        $view = $null
    }

    # Add an explicit uninstall entry to the Smart Lab Start Menu folder.
    # Windows Installer also registers the product in Apps/Programs and
    # Features; this shortcut provides a familiar, direct route as well.
    $startMenuDirectories = @{}
    $view = $database.OpenView("SELECT ``Name``, ``Directory_`` FROM ``Shortcut`` WHERE ``Directory_`` <> 'DesktopFolder'")
    $view.Execute()
    while ($record = $view.Fetch()) {
        $shortcutName = ($record.StringData(1) -split '\|')[-1]
        if ($shortcutName -eq $appDisplayName) {
            $startMenuDirectories[$record.StringData(2)] = $true
        }
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    if ($startMenuDirectories.Count -ne 1) {
        throw "The MSI does not contain exactly one $Product Start Menu folder."
    }
    $startMenuDirectory = @($startMenuDirectories.Keys)[0]
    if ($startMenuDirectory -notmatch '^[A-Za-z0-9_]+$') {
        throw "Unexpected MSI identifier for the Smart Lab Start Menu folder: '$startMenuDirectory'."
    }

    $uninstallComponent = 'SmartLabUninstallShortcut'
    $uninstallShortcut = 'SmartLabUninstallShortcut'
    $uninstallComponentId = $componentIds.Uninstall
    $uninstallRegistryKeyPath = 'SmartLabUninstallShortcutKeyPath'
    $insertComponentSql = "INSERT INTO ``Component`` (``Component``, ``ComponentId``, ``Directory_``, ``Attributes``, ``Condition``, ``KeyPath``) VALUES ('$uninstallComponent', '$uninstallComponentId', '$startMenuDirectory', 4, NULL, '$uninstallRegistryKeyPath')"
    $view = $database.OpenView($insertComponentSql)
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $insertRegistrySql = "INSERT INTO ``Registry`` (``Registry``, ``Root``, ``Key``, ``Name``, ``Value``, ``Component_``) VALUES ('$uninstallRegistryKeyPath', 2, '$registryBasePath', 'StartMenuUninstallShortcut', '1', '$uninstallComponent')"
    $view = $database.OpenView($insertRegistrySql)
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $insertFeatureComponentSql = "INSERT INTO ``FeatureComponents`` (``Feature_``, ``Component_``) VALUES ('DefaultFeature', '$uninstallComponent')"
    $view = $database.OpenView($insertFeatureComponentSql)
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $uninstallShortcutName = "Uninstall $productName"
    $insertUninstallShortcutSql = "INSERT INTO ``Shortcut`` (``Shortcut``, ``Directory_``, ``Name``, ``Component_``, ``Target``, ``Arguments``, ``Description``, ``IconIndex``, ``ShowCmd``) VALUES ('$uninstallShortcut', '$startMenuDirectory', '$uninstallShortcutName', '$uninstallComponent', '[SystemFolder]msiexec.exe', '/x [ProductCode]', 'Uninstall $productName', 0, 1)"
    $view = $database.OpenView($insertUninstallShortcutSql)
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Component_``, ``Target``, ``Arguments`` FROM ``Shortcut`` WHERE ``Shortcut`` = '$uninstallShortcut'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record -or $record.StringData(1) -ne $uninstallComponent -or $record.StringData(2) -ne '[SystemFolder]msiexec.exe' -or $record.StringData(3) -ne '/x [ProductCode]') {
        throw "The Start Menu uninstall shortcut did not pass validation."
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Attributes``, ``KeyPath`` FROM ``Component`` WHERE ``Component`` = '$uninstallComponent'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record -or $record.IntegerData(1) -ne 4 -or $record.StringData(2) -ne $uninstallRegistryKeyPath) {
        throw "The Start Menu uninstall shortcut component did not pass key path validation."
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Root``, ``Key``, ``Name``, ``Value``, ``Component_`` FROM ``Registry`` WHERE ``Registry`` = '$uninstallRegistryKeyPath'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record -or $record.IntegerData(1) -ne 2 -or $record.StringData(2) -ne $registryBasePath -or $record.StringData(3) -ne 'StartMenuUninstallShortcut' -or $record.StringData(4) -ne '1' -or $record.StringData(5) -ne $uninstallComponent) {
        throw "The Start Menu uninstall shortcut registry key path did not pass validation."
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property`` = 'CREATE_DESKTOP_SHORTCUTS'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record -or $record.StringData(1) -ne '1') {
        throw "Desktop shortcuts are not enabled by default in the MSI."
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property`` = 'ALLUSERS'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record -or $record.StringData(1) -ne '1') {
        throw "The MSI is not configured for a per-machine installation."
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Property`` FROM ``Control`` WHERE ``Dialog_`` = 'CustomCheckA' AND ``Control`` = 'Checkbox1'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record -or $record.StringData(1) -ne 'CREATE_DESKTOP_SHORTCUTS') {
        throw "The Desktop shortcut checkbox is not bound to CREATE_DESKTOP_SHORTCUTS."
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $view = $database.OpenView("SELECT ``Value`` FROM ``Property`` WHERE ``Property`` = 'SecureCustomProperties'")
    $view.Execute()
    $record = $view.Fetch()
    if (-not $record -or @($record.StringData(1) -split ';') -notcontains 'CREATE_DESKTOP_SHORTCUTS') {
        throw "The Desktop shortcut selection is not preserved for elevated installations."
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $database.Commit()
} finally {
    if ($view) {
        try { $view.Close() } catch { }
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    }
    if ($database) {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($database)
    }
    if ($installer) {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($installer)
    }
}

$msiBytes = (Get-Item -LiteralPath $msiPath).Length
if ($Product -eq "Agent" -and $msiBytes -ge 50000000) {
    throw "MSI exceeds the distribution limit of 50,000,000 bytes ($msiBytes bytes). Inspect the bundled dependencies before distributing it: '$msiPath'."
}
Write-Host "MSI created: $msiPath ($msiBytes bytes)"
