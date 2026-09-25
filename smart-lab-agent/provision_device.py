"""Register a Smart Lab workstation using an Admin account and Lab selection."""

from __future__ import annotations

import argparse
import getpass
import os
import platform
import sys

from agent_device import load_device_registration, save_device_registration
from device_registration import (
    DEFAULT_API_URL,
    LabSetupError,
    build_device_payload_for_api,
    normalize_api_url,
    register_device_as_admin,
)
from lab_setup import list_active_labs, login_admin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register this Windows workstation to a Lab using an Admin account.",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("SMART_LAB_API_URL", DEFAULT_API_URL),
        help="Smart Lab Backend URL",
    )
    parser.add_argument(
        "--device-name",
        default=platform.node() or "Smart Lab workstation",
        help="Display name for this workstation",
    )
    parser.add_argument(
        "--device-id",
        help="Optional existing device id; by default the saved id is reused",
    )
    parser.add_argument(
        "--agent-version",
        default=os.getenv("SMART_LAB_AGENT_VERSION", "source"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("Admin credentials are used only for setup and are not saved.\n")
    email = input("Admin Email: ").strip()
    password = getpass.getpass("Admin Password: ")

    try:
        api_url = normalize_api_url(args.api_url)
        try:
            access_token = login_admin(api_url, email, password)
        finally:
            password = ""

        labs = list_active_labs(api_url, access_token)
        if not labs:
            print("No active Labs were found.", file=sys.stderr)
            return 1

        print("\nActive Labs:")
        for index, lab in enumerate(labs, start=1):
            print(f"{index}. {lab.get('code', '-')} — {lab.get('name', '-')}")
        selected = int(input("Select Lab number: ").strip()) - 1
        if selected < 0 or selected >= len(labs):
            print("Invalid Lab number.", file=sys.stderr)
            return 1

        saved = load_device_registration() or {}
        saved_url = str(saved.get("api_url") or "").rstrip("/")
        if saved_url and saved_url != api_url and not args.device_id:
            saved = {}
        if args.device_id:
            saved = {"device_id": args.device_id.strip(), "api_url": api_url}
        payload = build_device_payload_for_api(
            saved,
            api_url,
            args.device_name,
            args.agent_version,
        )
        registration = register_device_as_admin(
            api_url,
            access_token,
            int(labs[selected]["id"]),
            payload,
        )
        path = save_device_registration(registration)
    except (ValueError, EOFError):
        print("The selected Lab number is invalid.", file=sys.stderr)
        return 2
    except LabSetupError as exc:
        print(f"Device registration failed: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Could not save device registration: {exc}", file=sys.stderr)
        return 1

    print("Device registered successfully.")
    print(f"Lab: {registration['lab_code']} - {registration['lab_name']}")
    print(f"Device ID: {registration['device_id']}")
    print(f"Saved registration: {path}")
    print("Restart Smart Lab Agent before starting the next user session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
