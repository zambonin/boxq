"""Import the external pinned catalog, retaining upstream provenance and terms."""

import hashlib
import json
import re
from pathlib import Path
from urllib.request import urlopen

from .catalog import data_path, _extra

CATALOG_SHA256 = "b0f35b0fd14fa8f1b80a85775211e1b7b8e0635e99b207bba561a9371c9ea4f0"
ROW = re.compile(r"^\s*([0-9a-fA-F]{2,3}):\s+((?:[0-9a-fA-F]{2,3}\s+){15}[0-9a-fA-F]{2,3})\s*$")


def sage_catalog(source):
    from .catalog_source import read_catalog

    expanded = read_catalog(source)
    digest = hashlib.sha256(
        json.dumps(expanded, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != CATALOG_SHA256:
        raise ValueError("SageMath catalog differs from the bundled SageMath 10.9 data")

    first_name = {}
    catalog = {}
    for name, values in sorted(expanded.items()):
        key = tuple(values)
        catalog[name] = first_name.get(key, values)
        first_name.setdefault(key, name)
    return catalog


def rfc_table(text, label, size):
    section = text.split(f"{label}TABLE:", 1)
    if len(section) != 2:
        raise ValueError(f"{label} table missing from RFC 2994")

    values = []
    for line in section[1].splitlines():
        match = ROW.fullmatch(line)
        if match is None:
            if values:
                break
            continue
        offset = int(match[1], 16)
        if offset != len(values):
            raise ValueError(f"{label} table offset {offset:x} is out of sequence")
        values.extend(int(value, 16) for value in match[2].split())
        if len(values) == size:
            break

    if len(values) != size or any(value >= size for value in values):
        raise ValueError(f"{label} table is incomplete or has invalid values")
    return values


def render(data):
    lines = ["{"]
    for section, entries in data.items():
        lines.append(f'  "{section}": {{')
        names = list(entries)
        for index, name in enumerate(names):
            value = entries[name]
            comma = "," if index + 1 < len(names) else ""
            if isinstance(value, str):
                lines.append(f'    "{name}": "{value}"{comma}')
                continue
            lines.append(f'    "{name}": [')
            for start in range(0, len(value), 16):
                row = value[start : start + 16]
                row_comma = "," if start + 16 < len(value) else ""
                lines.append("      " + ", ".join(map(str, row)) + row_comma)
            lines.append("    ]" + comma)
        lines.append("  }" + ("," if section != "extra" else ""))
    return "\n".join([*lines, "}", ""])


def generate(*, rfc_file=None, sage_file=None, sage_license_file=None, output=None, check=False):
    """Fetch or read pinned source declarations; no Sage installation required."""
    from .catalog_source import SAGE_URL, SAGE_SOURCE_SHA256, SAGE_BASE, SAGE_REVISION

    if sage_file:
        source = Path(sage_file).read_bytes()
    else:
        with urlopen(SAGE_URL, timeout=30) as response:
            source = response.read()
    extras = _extra()
    if rfc_file:
        rfc = Path(rfc_file).read_text()
        for label, size in (("S7", 128), ("S9", 512)):
            if rfc_table(rfc, label, size) != extras["MISTY1_" + label]:
                raise ValueError("RFC MISTY1 lookup differs from the bundled Botan source")

    data = {"catalog": sage_catalog(source), "extra": extras}
    target = Path(output).expanduser() if output else data_path()
    generated = render(data)
    if check:
        if generated != target.read_text():
            raise SystemExit(f"{target} differs from the source tables")
        print(f"{target} is up to date")
    else:
        from importlib.resources import files
        from .._json import write_json

        license_url = SAGE_BASE + "COPYING.txt"
        if sage_license_file:
            license_text = Path(sage_license_file).read_bytes()
        else:
            with urlopen(license_url, timeout=30) as response:
                license_text = response.read()
        license_hash = hashlib.sha256(license_text).hexdigest()
        if license_hash != "b9ee4b098b0e631fd53cf1975b08f81c1f9bf369fd0ebbd7277a12813368e5dc":
            raise ValueError("Sage COPYING.txt differs from the pinned revision")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(generated)
        notice = target.with_suffix(".SAGE-COPYING.txt")
        notice.write_bytes(license_text)
        write_json(
            target.with_suffix(".sources.json"),
            {
                "catalog": {
                    "url": SAGE_URL,
                    "revision": SAGE_REVISION,
                    "source_sha256": SAGE_SOURCE_SHA256,
                    "expanded_sha256": CATALOG_SHA256,
                    "license_url": license_url,
                    "license_sha256": license_hash,
                    "license_file": notice.name,
                    "terms": "External Sage input retains upstream terms; not relicensed by boxq.",
                },
                "misty1": json.loads(
                    files("boxq").joinpath("data/misty1-provenance.json").read_text()
                ),
                "output_sha256": hashlib.sha256(generated.encode()).hexdigest(),
            },
        )
        print(f"wrote {target}")
