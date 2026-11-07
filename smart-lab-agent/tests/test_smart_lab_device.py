import sys
import os
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

    def test_qa_booking_bypass_argument_is_removed_and_scoped_to_process(self):
        run_agent = Mock(return_value=0)
        agent_module = ModuleType("agent")
        agent_module.run_agent = run_agent

        with (
            patch.object(sys, "argv", ["SmartLabDevice.exe", "--qa-no-booking-time"]),
            patch.dict(os.environ, {
                "SMART_LAB_AGENT_QA_NO_BOOKING_TIME": "0",
                "SMART_LAB_AGENT_DATA_DIR": "normal-agent-data",
                "LOCALAPPDATA": r"C:\QA-Test\Local",
            }),
            patch.dict(sys.modules, {"agent": agent_module}),
        ):
            result = smart_lab_device.main()
            remaining_args = list(sys.argv)
            qa_setting = os.environ["SMART_LAB_AGENT_QA_NO_BOOKING_TIME"]
            qa_data_dir = os.environ["SMART_LAB_AGENT_DATA_DIR"]

        self.assertEqual(result, 0)
        run_agent.assert_called_once_with()
        self.assertEqual(remaining_args, ["SmartLabDevice.exe"])
        self.assertEqual(qa_setting, "1")
        self.assertEqual(qa_data_dir, os.path.join(r"C:\QA-Test\Local", "SmartLabAgentQA"))

    def test_qa_registration_uses_the_same_isolated_data_directory_as_agent(self):
        register_main = Mock(return_value=0)
        register_module = ModuleType("register_device_gui")
        register_module.main = register_main

        with (
            patch.object(
                sys,
                "argv",
                ["SmartLabDevice.exe", "--qa-no-booking-time", "--register"],
            ),
            patch.dict(
                os.environ,
                {
                    "SMART_LAB_AGENT_QA_NO_BOOKING_TIME": "0",
                    "SMART_LAB_AGENT_DATA_DIR": "normal-agent-data",
                    "LOCALAPPDATA": r"C:\QA-Test\Local",
                },
            ),
            patch.dict(sys.modules, {"register_device_gui": register_module}),
        ):
            result = smart_lab_device.main()
            remaining_args = list(sys.argv)
            qa_setting = os.environ["SMART_LAB_AGENT_QA_NO_BOOKING_TIME"]
            qa_data_dir = os.environ["SMART_LAB_AGENT_DATA_DIR"]

        self.assertEqual(result, 0)
        register_main.assert_called_once_with()
        self.assertEqual(remaining_args, ["SmartLabDevice.exe"])
        self.assertEqual(qa_setting, "1")
        self.assertEqual(qa_data_dir, os.path.join(r"C:\QA-Test\Local", "SmartLabAgentQA"))


class AgentQaHeaderTests(unittest.TestCase):
    def test_regular_build_does_not_send_qa_header(self):
        from agent_qa import start_session_headers

        self.assertEqual(
            start_session_headers("access-token"),
            {"Authorization": "Bearer access-token"},
        )

    def test_qa_build_marks_only_the_booking_time_test_header(self):
        from agent_qa import start_session_headers

        self.assertEqual(
            start_session_headers("access-token", qa_no_booking_time=True),
            {
                "Authorization": "Bearer access-token",
                "X-SmartLab-QA-No-Booking-Time": "1",
            },
        )


if __name__ == "__main__":
    unittest.main()
