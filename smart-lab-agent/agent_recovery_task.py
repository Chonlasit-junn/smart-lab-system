"""Provision the visible per-user Agent Recovery task for a locally registered device."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from agent_device import installed_agent_setting


TASK_NAME = r"\Smart Lab Agent Recovery"
RECOVERY_EXECUTABLE = "SmartLabAgentRecovery.exe"
TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
TASK_DESCRIPTION = "Reopen Smart Lab Agent if it stops in the Lab Windows account."


def installed_recovery_executable() -> Path | None:
    executable = Path(sys.executable)
    approved_path = installed_agent_setting("RecoveryAgentPath")
    if not approved_path or os.path.normcase(str(executable)) != os.path.normcase(approved_path):
        return None
    return executable


def _legacy_recovery_arguments(executable: Path) -> str:
    agent_literal = "'" + str(executable).replace("'", "''") + "'"
    check = (
        f"$agent = {agent_literal}; "
        "if (-not (Test-Path -LiteralPath $agent -PathType Leaf)) { exit }; "
        "$session = (Get-Process -Id $PID).SessionId; "
        "$running = Get-Process -Name SmartLabDevice -ErrorAction SilentlyContinue | "
        "Where-Object { $_.SessionId -eq $session -and $_.Path -eq $agent }; "
        "if (-not $running) { Start-Process -FilePath $agent }"
    )
    return '-NoProfile -NonInteractive -WindowStyle Hidden -Command "' + check + '"'


def recovery_task_xml(executable: Path, account_sid: str) -> str:
    start = (datetime.now().astimezone() + timedelta(minutes=1)).isoformat(timespec="seconds")
    sid = escape(account_sid)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="{TASK_NAMESPACE}">
  <RegistrationInfo>
    <Description>{TASK_DESCRIPTION}</Description>
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
    <Exec><Command>{escape(str(executable))}</Command></Exec>
  </Actions>
</Task>
"""


def _upgrade_task_xml(existing_xml, agent, helper, account_sid):
    namespace = {"": TASK_NAMESPACE}
    try:
        task = ElementTree.fromstring(existing_xml)
    except ElementTree.ParseError:
        return None
    if (
        task.findtext("RegistrationInfo/Description", namespaces=namespace) != TASK_DESCRIPTION
        or task.findtext("Principals/Principal/UserId", namespaces=namespace) != account_sid
        or task.findtext("Settings/Enabled", namespaces=namespace) == "false"
    ):
        return None
    actions = task.find("Actions", namespace)
    if actions is None or len(actions) != 1:
        return None
    command = actions.find("Exec/Command", namespace)
    arguments = actions.find("Exec/Arguments", namespace)
    if (
        command is None or Path(command.text or "").name.casefold() != "powershell.exe"
        or arguments is None or arguments.text != _legacy_recovery_arguments(agent)
    ):
        return None
    command.text = str(helper)
    actions[0].remove(arguments)
    return ElementTree.tostring(task, encoding="unicode", default_namespace=None)


def ensure_recovery_task() -> str:
    executable = installed_recovery_executable()
    if executable is None:
        return "not_installed"
    helper = executable.with_name(RECOVERY_EXECUTABLE)
    if not helper.is_file():
        return "recovery_executable_missing"

    system_dir = Path(os.environ["SystemRoot"]) / "System32"
    schtasks = str(system_dir / "schtasks.exe")
    run_options = dict(
        stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    armed = subprocess.run([str(helper), "--arm"], **run_options)
    if armed.returncode:
        return f"recovery_arm_failed_{armed.returncode}"
    existing = subprocess.run([schtasks, "/Query", "/TN", TASK_NAME, "/XML"], **run_options)

    identity = subprocess.run(
        [str(system_dir / "whoami.exe"), "/user", "/fo", "csv", "/nh"], **run_options,
    )
    if identity.returncode != 0:
        return "account_lookup_failed"
    account = next(csv.reader(identity.stdout.decode(errors="replace").splitlines()), [])
    if len(account) != 2 or not account[1].startswith("S-1-"):
        return "account_lookup_failed"

    if existing.returncode == 0:
        task_xml = _upgrade_task_xml(existing.stdout, executable, helper, account[1])
        if task_xml is None:
            return "already_configured"
    else:
        task_xml = recovery_task_xml(helper, account[1])

    with tempfile.TemporaryDirectory(prefix="smart-lab-recovery-") as temp_dir:
        xml_file = Path(temp_dir) / "task.xml"
        xml_file.write_text(task_xml, encoding="utf-16")
        command = [schtasks, "/Create", "/TN", TASK_NAME, "/XML", str(xml_file)]
        if existing.returncode == 0:
            command.append("/F")
        created = subprocess.run(
            command, **run_options,
        )
    if created.returncode:
        return f"create_failed_{created.returncode}"
    return "updated" if existing.returncode == 0 else "created"
