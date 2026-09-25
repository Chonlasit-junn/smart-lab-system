import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import smart_lab_device  # noqa: E402


class SmartLabDeviceLauncherTests(unittest.TestCase):
    def test_register_argument_dispatches_to_registration_wizard(self):
        register_main = Mock(return_value=0)
        register_module = ModuleType("register_device_gui")
        register_module.main = register_main

        with (
            patch.object(sys, "argv", ["SmartLabDevice.exe", "--register"]),
            patch.dict(sys.modules, {"register_device_gui": register_module}),
        ):
            result = smart_lab_device.main()
            remaining_args = list(sys.argv)

        self.assertEqual(result, 0)
        register_main.assert_called_once_with()
        self.assertEqual(remaining_args, ["SmartLabDevice.exe"])

    def test_default_dispatch_starts_the_agent(self):
        run_agent = Mock(return_value=0)
        agent_module = ModuleType("agent")
        agent_module.run_agent = run_agent

        with (
            patch.object(sys, "argv", ["SmartLabDevice.exe"]),
            patch.dict(sys.modules, {"agent": agent_module}),
        ):
            result = smart_lab_device.main()

        self.assertEqual(result, 0)
        run_agent.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
