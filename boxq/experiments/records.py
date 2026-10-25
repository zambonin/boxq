"""Read archived results without silently accepting incomplete large builds."""

import json
from pathlib import Path

from .large import LARGE_INPUTS
from .provenance import digest


def read(path):
    value = json.loads(Path(path).read_text())
    if value.get("producer", {}).get("schema") != "boxq-reproduction-v1":
        raise ValueError(f"missing versioned producer identity in {path}")
    return value


def large_records(folder):
    folder = Path(folder).resolve()
    records = {}
    for name in LARGE_INPUTS:
        path = folder / (name.lower().replace(":", "-") + ".json")
        record = read(path)
        check = record.get("construction", {}).get("verification", {})
        if (
            record.get("name") != name
            or record.get("status") != "complete"
            or not check.get("all_rows")
            or check.get("cells") != 2**32
        ):
            raise ValueError(f"incomplete verification in {path}")
        for output in record["outputs"]:
            target = (folder / output["path"]).resolve()
            if not target.is_relative_to(folder):
                raise ValueError("result output escapes the experiment directory")
            if digest(target) != output["sha256"]:
                raise ValueError(f"output checksum mismatch: {target}")
        records[name] = record
    return records
