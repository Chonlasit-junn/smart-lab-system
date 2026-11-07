"""Explicit test-build behavior for Agent QA workstations."""

from __future__ import annotations

QA_BOOKING_TIME_BYPASS_HEADER = "X-SmartLab-QA-No-Booking-Time"


def start_session_headers(access_token: str, *, qa_no_booking_time: bool = False) -> dict[str, str]:
    """Build authenticated Agent headers, marking only the QA booking test."""
    headers = {"Authorization": f"Bearer {access_token}"}
    if qa_no_booking_time:
        headers[QA_BOOKING_TIME_BYPASS_HEADER] = "1"
    return headers
