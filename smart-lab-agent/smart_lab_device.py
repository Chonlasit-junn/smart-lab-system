"""Single executable entry point for the Agent and registration wizard."""

from __future__ import annotations

import sys
import os

from agent_device import append_agent_diagnostic


def main() -> int:
    """Dispatch the requested entry point without duplicating the Qt runtime."""

    arguments = sys.argv[1:]
    if "--qa" in arguments:
        sys.argv = [argument for argument in sys.argv if argument != "--qa"]
        app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if app_data:
            os.environ["SMART_LAB_AGENT_DATA_DIR"] = os.path.join(app_data, "SmartLabAgentQA")
        arguments = sys.argv[1:]

    if "--register" in arguments:
        sys.argv = [argument for argument in sys.argv if argument != "--register"]
        from register_device_gui import main as register_main

        return register_main()

    try:
        from agent import run_agent

        return run_agent()
    except Exception as error:
        append_agent_diagnostic("agent-runtime.log", f"startup_failed error={type(error).__name__}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
