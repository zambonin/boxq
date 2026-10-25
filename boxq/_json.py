"""Shared atomic JSON record output for input generators and experiments."""

import json
from pathlib import Path


def write_json(path, value):
    """Replace one sorted, indented UTF-8 record after its write completes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
