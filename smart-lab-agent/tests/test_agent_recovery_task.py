import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import agent_recovery_task as recovery


class AgentRecoveryTaskTests(unittest.TestCase):
    def test_xml_uses_interactive_account_and_repeats_each_minute(self):
        executable = Path(r"C:\Lab's & Tools\SmartLabDevice.exe")
        document = ElementTree.fromstring(
            recovery.recovery_task_xml(executable, "S-1-5-21-123", Path(r"C:\Windows\System32"))
        )
        namespace = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(document.findtext(".//t:Principal/t:UserId", namespaces=namespace), "S-1-5-21-123")
        self.assertEqual(document.findtext(".//t:LogonType", namespaces=namespace), "InteractiveToken")
        self.assertEqual(document.findtext(".//t:RunLevel", namespaces=namespace), "LeastPrivilege")
        self.assertEqual(document.findtext(".//t:Interval", namespaces=namespace), "PT1M")
        self.assertIn("Lab''s & Tools", document.findtext(".//t:Arguments", namespaces=namespace))

    @patch.object(recovery, "installed_recovery_executable", return_value=Path("SmartLabDevice.exe"))
    @patch.dict(os.environ, {"SystemRoot": r"C:\Windows"})
    @patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True)
    @patch.object(subprocess, "run")
    def test_existing_task_is_left_alone(self, run, _installed):
        run.return_value.returncode = 0
        self.assertEqual(recovery.ensure_recovery_task(), "already_configured")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][1:], ["/Query", "/TN", recovery.TASK_NAME])

    @patch.object(recovery, "installed_recovery_executable", return_value=Path("SmartLabDevice.exe"))
    @patch.dict(os.environ, {"SystemRoot": r"C:\Windows"})
    @patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True)
    @patch.object(subprocess, "run")
    def test_creates_missing_task_without_overwrite(self, run, _installed):
        def handle_command(command, **_kwargs):
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
        self.assertEqual(run.call_count, 3)
