import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import agent_recovery_task as recovery


class AgentRecoveryTaskTests(unittest.TestCase):
    @patch.object(subprocess, "run")
    @patch.object(recovery, "installed_agent_setting", return_value=None)
    def test_disabled_recovery_does_not_call_task_scheduler(self, setting, run):
        self.assertEqual(recovery.ensure_recovery_task(), "not_installed")
        setting.assert_called_once_with("RecoveryAgentPath")
        run.assert_not_called()

    @patch.object(recovery, "installed_agent_setting")
    def test_recovery_opt_in_uses_approved_path_without_autostart(self, setting):
        setting.return_value = sys.executable
        self.assertEqual(recovery.installed_recovery_executable(), Path(sys.executable))
        setting.return_value = str(Path(sys.executable).with_name("different.exe"))
        self.assertIsNone(recovery.installed_recovery_executable())

    def test_xml_uses_interactive_account_and_repeats_each_minute(self):
        executable = Path(r"C:\Lab's & Tools\SmartLabAgentRecovery.exe")
        document = ElementTree.fromstring(
            recovery.recovery_task_xml(executable, "S-1-5-21-123")
        )
        namespace = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(document.findtext(".//t:Principal/t:UserId", namespaces=namespace), "S-1-5-21-123")
        self.assertEqual(document.findtext(".//t:LogonType", namespaces=namespace), "InteractiveToken")
        self.assertEqual(document.findtext(".//t:RunLevel", namespaces=namespace), "LeastPrivilege")
        self.assertEqual(document.findtext(".//t:Interval", namespaces=namespace), "PT1M")
        self.assertEqual(document.findtext(".//t:Command", namespaces=namespace), str(executable))
        self.assertIsNone(document.find(".//t:Arguments", namespace))

    @patch.object(Path, "is_file", return_value=True)
    @patch.object(recovery, "installed_recovery_executable", return_value=Path("SmartLabDevice.exe"))
    @patch.dict(os.environ, {"SystemRoot": r"C:\Windows"})
    @patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True)
    @patch.object(subprocess, "run")
    def test_existing_task_is_left_alone(self, run, _installed, _is_file):
        run.side_effect = [
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0, stdout=b'<OtherTask />'),
            subprocess.CompletedProcess([], 0, stdout=b'"LAB\\User","S-1-5-21-123"\r\n'),
        ]
        self.assertEqual(recovery.ensure_recovery_task(), "already_configured")
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].args[0][1:], ["--arm"])
        self.assertEqual(run.call_args_list[1].args[0][1:], ["/Query", "/TN", recovery.TASK_NAME, "/XML"])

    @patch.object(Path, "is_file", return_value=True)
    @patch.object(recovery, "installed_recovery_executable", return_value=Path("SmartLabDevice.exe"))
    @patch.dict(os.environ, {"SystemRoot": r"C:\Windows"})
    @patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True)
    @patch.object(subprocess, "run")
    def test_creates_missing_task_without_overwrite(self, run, _installed, _is_file):
        def handle_command(command, **_kwargs):
            if "--arm" in command:
                return subprocess.CompletedProcess(command, 0)
            if "/Query" in command:
                return subprocess.CompletedProcess(command, 1)
            if "/user" in command:
                return subprocess.CompletedProcess(command, 0, stdout=b'"LAB\\User","S-1-5-21-123"\r\n')
            self.assertIn("/Create", command)
            self.assertNotIn("/F", command)
            xml_path = Path(command[-1])
            self.assertIn("S-1-5-21-123", xml_path.read_text(encoding="utf-16"))
            return subprocess.CompletedProcess(command, 0)

        run.side_effect = handle_command
        self.assertEqual(recovery.ensure_recovery_task(), "created")
        self.assertEqual(run.call_count, 4)

    def test_updates_the_legacy_action_and_preserves_schedule(self):
        agent = Path(r"C:\Lab & Tools\SmartLabDevice.exe")
        helper = agent.with_name(recovery.RECOVERY_EXECUTABLE)
        ns = {"": recovery.TASK_NAMESPACE}
        sid = "S-1-5-21-123"
        legacy = ElementTree.fromstring(recovery.recovery_task_xml(helper, sid))
        legacy.find("Actions/Exec/Command", ns).text = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        args = ElementTree.SubElement(legacy.find("Actions/Exec", ns), f"{{{recovery.TASK_NAMESPACE}}}Arguments")
        args.text = recovery._legacy_recovery_arguments(agent)
        updated = ElementTree.fromstring(recovery._upgrade_task_xml(ElementTree.tostring(legacy), agent, helper, sid))
        self.assertEqual(updated.findtext("Actions/Exec/Command", namespaces=ns), str(helper))
        self.assertIsNone(updated.find("Actions/Exec/Arguments", ns))
        self.assertEqual(ElementTree.tostring(updated.find("Triggers", ns)), ElementTree.tostring(legacy.find("Triggers", ns)))
        ElementTree.SubElement(legacy.find("Settings", ns), f"{{{recovery.TASK_NAMESPACE}}}Enabled").text = "false"
        self.assertIsNone(recovery._upgrade_task_xml(ElementTree.tostring(legacy), agent, helper, sid))
