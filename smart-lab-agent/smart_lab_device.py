"""Single executable entry point for the Agent and registration wizard."""

from __future__ import annotations

import sys


def main() -> int:
    """Dispatch the requested entry point without duplicating the Qt runtime."""

    if "--register" in sys.argv[1:]:
        sys.argv = [argument for argument in sys.argv if argument != "--register"]
        from register_device_gui import main as register_main

        return register_main()

    from agent import run_agent

    return run_agent()


if __name__ == "__main__":
    raise SystemExit(main())
