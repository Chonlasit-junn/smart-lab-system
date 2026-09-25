param(
    [string]$Version = "1.0.0",
    [string]$PythonPath = "",
    [string]$PrebuiltPayloadPath = ""
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

$agentRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
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
        Join-Path $agentRoot "venv\Scripts\python.exe"
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Project Python environment not found at '$python'. Create smart-lab-agent\venv first."
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
    & $python -B -c "import PyInstaller; assert PyInstaller.__version__ == '6.20.0'; import PyQt6, psutil, requests, pygetwindow"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 6.20.0 and the project runtime dependencies are required. Install with: `"$python`" -m pip install pyinstaller==6.20.0"
    }
}

$buildId = "{0}-{1}" -f $Version, (Get-Date -Format "yyyyMMdd-HHmmss")
$buildRoot = Join-Path $agentRoot "build_msi\$buildId"
$payloadRoot = Join-Path $buildRoot "payload"
$distRoot = Join-Path $agentRoot "dist_msi\$buildId"
$projectPath = Join-Path $buildRoot "SmartLabAgentInstaller.vdproj"
$solutionPath = Join-Path $buildRoot "SmartLabAgentInstaller.sln"
$buildLog = Join-Path $buildRoot "visualstudio-build.log"

New-Item -ItemType Directory -Path $payloadRoot, $distRoot, (Join-Path $buildRoot "pyinstaller-work\device"), (Join-Path $buildRoot "spec") -Force | Out-Null

if ($usePrebuiltPayload) {
    $prebuiltPayload = Join-Path $resolvedPrebuiltPayloadPath "SmartLabDevice.exe"
    if (-not (Test-Path -LiteralPath $prebuiltPayload -PathType Leaf)) {
        throw "Expected prebuilt application payload was not found: '$prebuiltPayload'."
    }
    Copy-Item -LiteralPath $prebuiltPayload -Destination $payloadRoot
} else {
    $deviceBuildArgs = @(
        "-B", "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "SmartLabDevice",
        "--distpath", $payloadRoot,
        "--workpath", (Join-Path $buildRoot "pyinstaller-work\device"),
        "--specpath", (Join-Path $buildRoot "spec"),
        (Join-Path $agentRoot "smart_lab_device.py")
    )
    & $python @deviceBuildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed while packaging the shared Agent and registration executable (exit code $LASTEXITCODE)."
    }
}

$deviceExe = Join-Path $payloadRoot "SmartLabDevice.exe"
if (-not (Test-Path -LiteralPath $deviceExe -PathType Leaf)) {
    throw "Expected application payload was not created: '$deviceExe'."
}

function ConvertTo-VdprojValue([string]$Value) {
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

$productHash = [System.Security.Cryptography.MD5]::Create()
try {
    $productBytes = $productHash.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("SmartLabDeviceAgent:$Version"))
} finally {
    $productHash.Dispose()
}
$productCode = ([guid]::new($productBytes)).ToString('B').ToUpperInvariant()
$packageCode = [guid]::NewGuid().ToString('B').ToUpperInvariant()
$msiPath = Join-Path $distRoot "SmartLabAgent.msi"
$templatePath = Join-Path $PSScriptRoot "SmartLabAgent.vdproj.template"
$projectTemplate = Get-Content -LiteralPath $templatePath -Raw
$replacements = @{
    "__OUTPUT_MSI__" = ConvertTo-VdprojValue $msiPath
    "__DEVICE_EXE__" = ConvertTo-VdprojValue $deviceExe
    "__PRODUCT_CODE__" = $productCode
    "__PACKAGE_CODE__" = $packageCode
    "__VERSION__" = $Version
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
Project("{978C614F-708E-4E1A-B201-565925725DBA}") = "SmartLabAgentInstaller", "SmartLabAgentInstaller.vdproj", "$projectGuid"
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
& $devenv @devenvArgs
if ($LASTEXITCODE -ne 0) {
    throw "Visual Studio Installer Projects failed to build the MSI (exit code $LASTEXITCODE). See '$buildLog'."
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
            Name = 'Smart Lab Agent'
            FileName = 'SmartLabDevice.exe'
            Arguments = ''
            Component = 'SmartLabDesktopAgentShortcut'
            ComponentId = '{C41B79CE-2E28-41BD-B743-7607AB300021}'
            RegistryKeyPath = 'SmartLabDesktopAgentShortcutKeyPath'
            RegistryValue = 'DesktopAgentShortcut'
        },
        @{
            Name = 'Register This Computer'
            FileName = 'SmartLabDevice.exe'
            Arguments = '--register'
            Component = 'SmartLabDesktopRegisterShortcut'
            ComponentId = '{C41B79CE-2E28-41BD-B743-7607AB300022}'
            RegistryKeyPath = 'SmartLabDesktopRegisterShortcutKeyPath'
            RegistryValue = 'DesktopRegisterShortcut'
        }
    )

    if ($desktopShortcutIds.Count -ne $desktopShortcutDefinitions.Count) {
        throw "The MSI does not contain exactly the two expected Desktop shortcuts."
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
        $insertRegistrySql = "INSERT INTO ``Registry`` (``Registry``, ``Root``, ``Key``, ``Name``, ``Value``, ``Component_``) VALUES ('$registryKeyPath', 2, 'Software\Smart Lab\Device Agent', '$registryValue', '1', '$component')"
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
        if (-not $record -or $record.IntegerData(1) -ne 2 -or $record.StringData(2) -ne 'Software\Smart Lab\Device Agent' -or $record.StringData(3) -ne $registryValue -or $record.StringData(4) -ne '1' -or $record.StringData(5) -ne $component) {
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
        if ($shortcutName -eq 'Smart Lab Agent') {
            $startMenuDirectories[$record.StringData(2)] = $true
        }
    }
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    if ($startMenuDirectories.Count -ne 1) {
        throw "The MSI does not contain exactly one Smart Lab Start Menu folder."
    }
    $startMenuDirectory = @($startMenuDirectories.Keys)[0]
    if ($startMenuDirectory -notmatch '^[A-Za-z0-9_]+$') {
        throw "Unexpected MSI identifier for the Smart Lab Start Menu folder: '$startMenuDirectory'."
    }

    $uninstallComponent = 'SmartLabUninstallShortcut'
    $uninstallShortcut = 'SmartLabUninstallShortcut'
    $uninstallComponentId = '{C41B79CE-2E28-41BD-B743-7607AB300023}'
    $uninstallRegistryKeyPath = 'SmartLabUninstallShortcutKeyPath'
    $insertComponentSql = "INSERT INTO ``Component`` (``Component``, ``ComponentId``, ``Directory_``, ``Attributes``, ``Condition``, ``KeyPath``) VALUES ('$uninstallComponent', '$uninstallComponentId', '$startMenuDirectory', 4, NULL, '$uninstallRegistryKeyPath')"
    $view = $database.OpenView($insertComponentSql)
    $view.Execute()
    $view.Close()
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    $view = $null

    $insertRegistrySql = "INSERT INTO ``Registry`` (``Registry``, ``Root``, ``Key``, ``Name``, ``Value``, ``Component_``) VALUES ('$uninstallRegistryKeyPath', 2, 'Software\Smart Lab\Device Agent', 'StartMenuUninstallShortcut', '1', '$uninstallComponent')"
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

    $insertUninstallShortcutSql = "INSERT INTO ``Shortcut`` (``Shortcut``, ``Directory_``, ``Name``, ``Component_``, ``Target``, ``Arguments``, ``Description``, ``IconIndex``, ``ShowCmd``) VALUES ('$uninstallShortcut', '$startMenuDirectory', 'Uninstall Smart Lab Agent', '$uninstallComponent', '[SystemFolder]msiexec.exe', '/x [ProductCode]', 'Uninstall Smart Lab Device Agent', 0, 1)"
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
    if (-not $record -or $record.IntegerData(1) -ne 2 -or $record.StringData(2) -ne 'Software\Smart Lab\Device Agent' -or $record.StringData(3) -ne 'StartMenuUninstallShortcut' -or $record.StringData(4) -ne '1' -or $record.StringData(5) -ne $uninstallComponent) {
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

Write-Host "MSI created: $msiPath"
