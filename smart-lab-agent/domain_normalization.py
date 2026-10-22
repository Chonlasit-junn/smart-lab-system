"""Domain contract v1: Unicode 16 UTS #46, non-transitional, domain-only.

Keep the Backend and Agent copies identical: independent deployments cannot
import a file outside their payload. Shared golden tests enforce this contract.
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata

import idna

if tuple(map(int, unicodedata.unidata_version.split("."))) < (16, 0, 0):
    # Backend Python 3.11 has Unicode 14; use the same data as Agent/JS.
    import unicodedata2 as unicodedata

_ASCII_TRIM = " \t\r\n\f\v"


def _ipv4(host):
    """WHATWG IPv4 numbers, including short, octal and hexadecimal forms."""
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    values = []
    for part in parts:
        base = 10
        if part.startswith("0x"):
            base, part = 16, part[2:]
        elif len(part) > 1 and part.startswith("0"):
            base, part = 8, part[1:]
        digits = {10: r"[0-9]*", 16: r"[0-9a-f]*", 8: r"[0-7]*"}[base]
        if not re.fullmatch(digits, part):
            return None
        values.append(int(part, base) if part else 0)
    if any(value > 255 for value in values[:-1]) or values[-1] >= 256 ** (5 - len(values)):
        return None
    number = values[-1] + sum(value * 256 ** (3 - index) for index, value in enumerate(values[:-1]))
    return str(ipaddress.IPv4Address(number))


def _remap(value):
    return unicodedata.normalize("NFC", idna.uts46_remap(value, std3_rules=True, transitional=False))


def _valid_joiner(label, index):
    if index and unicodedata.combining(label[index - 1]) == 9:
        return True
    if label[index] == "\u200d":
        return False
    def neighbor(characters):
        for character in characters:
            kind = idna.idnadata.joining_types.get(ord(character))
            if kind != ord("T"):
                return kind
        return None
    return (neighbor(reversed(label[:index])) in {ord("L"), ord("D")}
            and neighbor(label[index + 1:]) in {ord("R"), ord("D")})


def _valid_bidi(label):
    # UTS46/RFC5893: every label in a Bidi domain must satisfy these rules.
    directions = [unicodedata.bidirectional(character) for character in label]
    rtl = directions[0] in {"R", "AL"}
    if not rtl and directions[0] != "L":
        return False
    allowed = {"R", "AL", "AN", "EN", "ES", "CS", "ET", "ON", "BN", "NSM"} if rtl else {
        "L", "EN", "ES", "CS", "ET", "ON", "BN", "NSM",
    }
    significant = [direction for direction in directions if direction != "NSM"]
    endings = {"R", "AL", "EN", "AN"} if rtl else {"L", "EN"}
    return (all(direction in allowed for direction in directions)
            and significant[-1] in endings
            and not (rtl and "AN" in directions and "EN" in directions))


def _ascii_domain(host):
    # Use UTS46 mapping, not Python's legacy IDNA2003 codec (ß must not become ss).
    mapped = _remap(host)
    if mapped.endswith("."):
        mapped = mapped[:-1]
    labels = []
    for label in mapped.split("."):
        if not label:
            return None
        if label.startswith("xn--"):
            label = label[4:].encode("ascii").decode("punycode")
            if not label or label.isascii():
                return None
        # A decoded A-label must already be valid, mapped NFC, not repaired.
        if "." in label or _remap(label) != label:
            return None
        idna.check_hyphen_ok(label)
        if unicodedata.category(label[0]).startswith("M"):
            return None
        for index, character in enumerate(label):
            if character in "\u200c\u200d" and not _valid_joiner(label, index):
                return None
        labels.append(label)
    bidi = any(unicodedata.bidirectional(character) in {"R", "AL", "AN"}
               for label in labels for character in label)
    encoded = []
    for label in labels:
        if bidi and not _valid_bidi(label):
            return None
        ascii_label = label if label.isascii() else "xn--" + label.encode("punycode").decode("ascii")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", ascii_label):
            return None
        encoded.append(ascii_label)
    result = ".".join(encoded)
    return result if len(result) <= 253 else None


def normalize_domain(value):
    if not isinstance(value, str):
        return None
    raw = value.strip(_ASCII_TRIM)
    if not raw or len(raw) > 4096 or any(
        ord(character) <= 32 or ord(character) == 127 or character.isspace()
        or character in "\\\ufeff" for character in raw
    ):
        return None
    try:
        explicit_scheme = "://" in raw
        if "://" in raw:
            scheme, raw = raw.split("://", 1)
            if scheme.lower() not in {"http", "https"}:
                return None
        authority = re.split(r"[/?#]", raw, maxsplit=1)[0]
        if not authority or "@" in authority or "%" in authority:
            return None
        port = None
        ipv6 = False
        if authority.startswith("["):
            end = authority.find("]")
            if end < 0:
                return None
            host = authority[1:end]
            suffix = authority[end + 1:]
            if suffix:
                if not suffix.startswith(":"):
                    return None
                port = suffix[1:]
            ipv6 = True
        elif authority.count(":") > 1:
            if explicit_scheme:
                return None
            host, ipv6 = authority, True
        elif ":" in authority:
            host, port = authority.rsplit(":", 1)
        else:
            host = authority
        if port is not None and (not re.fullmatch(r"[0-9]{1,5}", port) or int(port) > 65535):
            return None
        if ipv6:
            # Python 3.14 renders IPv4-mapped IPv6 differently from 3.11.
            # Canonicalize packed bytes ourselves to WHATWG's hexadecimal form.
            packed = ipaddress.IPv6Address(host).packed
            groups = [format(int.from_bytes(packed[index:index + 2], "big"), "x")
                      for index in range(0, 16, 2)]
            best_start, best_length = 0, 0
            index = 0
            while index < 8:
                end = index
                while end < 8 and groups[end] == "0":
                    end += 1
                if end - index > best_length:
                    best_start, best_length = index, end - index
                index = max(end, index + 1)
            if best_length >= 2:
                address = ":".join(groups[:best_start]) + "::" + ":".join(groups[best_start + best_length:])
            else:
                address = ":".join(groups)
            return "[" + address + "]"
        host = _ascii_domain(host)
        if not host:
            return None
        last = host.rsplit(".", 1)[-1]
        if re.fullmatch(r"[0-9]+|0x[0-9a-f]*", last):
            return _ipv4(host)
        return host if "." in host else None
    except (ValueError, UnicodeError, OverflowError, idna.IDNAError):
        return None


def domain_matches(host, blocked):
    """Only DNS names have subdomains; IP literals require exact equality."""
    if host == blocked:
        return True
    if blocked.startswith("[") or re.fullmatch(r"[0-9.]+", blocked):
        return False
    return host.endswith("." + blocked)
