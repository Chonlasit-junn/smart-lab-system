"""Provision the visible per-user Agent Recovery task after device validation."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape


TASK_NAME = r"\Smart Lab Agent Recovery"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def installed_recovery_executable() -> Path | None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None

    import winreg

    executable = Path(sys.executable)
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, RUN_KEY, 0,
            winreg.KEY_QUERY_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            startup_command, _ = winreg.QueryValueEx(key, "SmartLabAgent")
    except OSError:
        return None
    # Match the normal MSI's sign-in entry, including custom installation paths.
    # The QA variant uses a separate sign-in entry and Windows task configuration.
    if not isinstance(startup_command, str):
        return None
    if os.path.normcase(str(executable)) != os.path.normcase(startup_command.strip().strip('"')):
        return None
    return executable


def recovery_task_xml(executable: Path, account_sid: str, system_dir: Path) -> str:
    agent_literal = "'" + str(executable).replace("'", "''") + "'"
    check = (
        f"$agent = {agent_literal}; "
        "if (-not (Test-Path -LiteralPath $agent -PathType Leaf)) { exit }; "
        "$session = (Get-Process -Id $PID).SessionId; "
        "$running = Get-Process -Name SmartLabDevice -ErrorAction SilentlyContinue | "
        "Where-Object { $_.SessionId -eq $session -and $_.Path -eq $agent }; "
        "if (-not $running) { Start-Process -FilePath $agent }"
    )
    arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -Command "' + check + '"'
    powershell = system_dir / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    start = (datetime.now().astimezone() + timedelta(minutes=1)).isoformat(timespec="seconds")
    sid = escape(account_sid)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Reopen Smart Lab Agent if it stops in the Lab Windows account.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger><UserId>{sid}</UserId></LogonTrigger>
    <TimeTrigger>
      <Repetition><Interval>PT1M</Interval></Repetition>
      <StartBoundary>{start}</StartBoundary>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="LabUser">
      <UserId>{sid}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
  </Settings>
  <Actions Context="LabUser">
    <Exec><Command>{escape(str(powershell))}</Command><Arguments>{escape(arguments)}</Arguments></Exec>
  </Actions>
</Task>
"""


def ensure_recovery_task() -> str:
    executable = installed_recovery_executable()
    if executable is None:
        return "not_installed"

    system_dir = Path(os.environ["SystemRoot"]) / "System32"
    schtasks = str(system_dir / "schtasks.exe")
    run_options = dict(
        stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    existing = subprocess.run([schtasks, "/Query", "/TN", TASK_NAME], **run_options)
    if existing.returncode == 0:
        return "already_configured"

    identity = subprocess.run(
        [str(system_dir / "whoami.exe"), "/user", "/fo", "csv", "/nh"], **run_options,
    )
    if identity.returncode != 0:
        return "account_lookup_failed"
    account = next(csv.reader(identity.stdout.decode(errors="replace").splitlines()), [])
    if len(account) != 2 or not account[1].startswith("S-1-"):
        return "account_lookup_failed"

    with tempfile.TemporaryDirectory(prefix="smart-lab-recovery-") as temp_dir:
        xml_file = Path(temp_dir) / "task.xml"
        xml_file.write_text(recovery_task_xml(executable, account[1], system_dir), encoding="utf-16")
        created = subprocess.run(
            [schtasks, "/Create", "/TN", TASK_NAME, "/XML", str(xml_file)], **run_options,
        )
    return "created" if created.returncode == 0 else f"create_failed_{created.returncode}"
