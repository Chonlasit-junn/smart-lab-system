"""Single executable entry point for the Agent and registration wizard."""

from __future__ import annotations

import sys
import os


def main() -> int:
    """Dispatch the requested entry point without duplicating the Qt runtime."""

    arguments = sys.argv[1:]
    if "--qa-no-booking-time" in arguments:
        sys.argv = [argument for argument in sys.argv if argument != "--qa-no-booking-time"]
        os.environ["SMART_LAB_AGENT_QA_NO_BOOKING_TIME"] = "1"
        app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if app_data:
            os.environ["SMART_LAB_AGENT_DATA_DIR"] = os.path.join(app_data, "SmartLabAgentQA")
        arguments = sys.argv[1:]

    if "--register" in arguments:
        sys.argv = [argument for argument in sys.argv if argument != "--register"]
        from register_device_gui import main as register_main

        return register_main()

    from agent import run_agent

    return run_agent()


if __name__ == "__main__":
    raise SystemExit(main())
