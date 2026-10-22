"""Offline parity: JS frontend vs Backend Python 3.11 vs Agent Python 3.14.

Uses only synthetic domains and subprocess pipes. No HTTP, DB or saved tokens.
Run from the root with smart-lab-agent/venv/Scripts/python.exe -B.
"""
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/domain-contract.json").read_text(encoding="utf-8"))


def run():
    values = [value for value, _ in FIXTURE["normalization"]]
    rng = random.Random(46)
    # Unicode 16 letters/marks and mixed RTL/LTR, Joiners, Emoji, composed forms.
    alphabet = list("abcßẞςσéüไทย例子العربيةאבג012.-_😀·") + [
        "\u200c", "\u200d", "\u0301", "\u094d", "\U000105c0", "\U00011380", "\U000113b8",
    ]
    for _ in range(2500):
        label = "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 12)))
        values.append(rng.choice(["", "https://", "HTTP://"]) + label + rng.choice([".example", ".de", ".مثال"]))
        # Include pre-encoded labels (valid and invalid NFC/Joiner/Bidi forms).
        values.append("xn--" + label.encode("punycode").decode("ascii") + ".example")
    for _ in range(300):
        number = rng.randrange(2 ** 32)
        values.extend([str(number), hex(number), f"{number >> 24}.{number & 0xffffff}"])
        groups = [format(rng.randrange(65536) if rng.randrange(3) == 0 else 0, "x") for _ in range(8)]
        values.append("https://[" + ":".join(groups) + "]:443/private?secret=1")
    values.extend(["a" * 63 + ".example", "a" * 64 + ".example", ".".join(["a" * 63] * 4)])
    # Visit all Unicode 16 additions used by this project's libraries, not just Latin.
    values.extend(chr(codepoint) + ".example" for codepoint in range(0x11380, 0x113E0))
    input_bytes = json.dumps(values, ensure_ascii=True).encode()
    js = json.loads(subprocess.check_output(["node", "scripts/domain-contract-runner.mjs"],
                                            input=input_bytes, cwd=ROOT))
    python_code = (
        "import sys,json;sys.path.insert(0,sys.argv[1]);"
        "from domain_normalization import normalize_domain as n;"
        "v=json.load(sys.stdin);print(json.dumps([{'domain':n(x),'idempotent':n(x) is None or n(n(x))==n(x)} for x in v]))"
    )
    outputs = {}
    for name, directory in (("backend", "backend"), ("agent", "smart-lab-agent")):
        python = ROOT / directory / "venv/Scripts/python.exe"
        if not python.is_file():
            raise RuntimeError(f"Missing {name} test runtime: {python}")
        outputs[name] = json.loads(subprocess.check_output([str(python), "-B", "-c", python_code, directory],
                                                          input=input_bytes, cwd=ROOT))
    failures = []
    for index, value in enumerate(values):
        domains = [js[index]["domain"], outputs["backend"][index]["domain"], outputs["agent"][index]["domain"]]
        if len(set(domains)) != 1 or not all(output[index]["idempotent"] for output in [js, *outputs.values()]):
            failures.append({"input": value, "website_backend_agent": domains})
        if js[index]["payload"] != js[index]["domain"]:
            failures.append({"input": value, "error": "Form payload differs from domain"})
    if failures:
        print(json.dumps({"failed": len(failures), "examples": failures[:15]}, ensure_ascii=True, indent=2))
        return 1
    print(json.dumps({"cases": len(values), "runtimes": ["frontend", "backend", "agent"],
                      "normalization": "PASS", "idempotence": "PASS", "frontend_payload": "PASS"}))
    return 0


if __name__ == "__main__":
    sys.exit(run())
