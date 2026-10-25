"""Bundled lookup values. An alias references another name, never a second copy."""

from functools import lru_cache
from importlib.resources import files
from pathlib import Path
import json
import os
import re

# Same selection as the article, without embedding any result values.
SELECTED = [
    "SEA",
    "PRESENT",
    "Noekeon",
    "Ascon",
    "APN_6",
    "WAGE",
    "AES",
    "Camellia",
    "Kuznyechik",
    "Skipjack",
    "SKINNY_8",
    "Safer",
    "CSS",
    "DryGASCON256",
]


class Lookup(list):
    """Outputs of F: F_2^n -> F_2^m in input order; ``m`` defaults to ``n``.

    A rectangular lookup (m != n) is limited to nine input and output bits,
    so that its zero-padded square table stays within the dense commands.
    """

    def __init__(self, values, m=None):
        super().__init__(values)
        size = len(self)
        if size < 2 or size & (size - 1):
            raise ValueError("a lookup must have power-of-two length, at least two")
        self.n = (size - 1).bit_length()
        self.m = self.n if m is None else m
        if type(self.m) is not int or self.m < 1:
            raise ValueError("the output width m must be a positive integer")
        if self.m != self.n and max(self.n, self.m) > 9:
            raise ValueError("rectangular lookups are limited to 9 input and output bits")
        if any(type(v) is not int or not 0 <= v < 1 << self.m for v in self):
            raise ValueError(f"lookup entries must be integers in 0..2^{self.m}-1")


def data_path():
    explicit = os.environ.get("BOXQ_DATA")
    if explicit:
        return Path(explicit).expanduser()
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "boxq/sboxes.json"


@lru_cache(maxsize=1)
def _extra():
    return json.loads(files("boxq").joinpath("data/misty1.json").read_text())


@lru_cache(maxsize=1)
def _catalog():
    path = data_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"S-box catalog missing at {path}; run 'boxq generate-sboxes' or set BOXQ_DATA"
        )
    data = json.loads(path.read_text())
    return {"catalog": data["catalog"], "extra": {**data.get("extra", {}), **_extra()}}


def names(*, extras=False):
    data = _catalog()
    return sorted([*data["catalog"], *(data["extra"] if extras else [])], key=str.casefold)


def lookup(name: str) -> Lookup:
    """Resolve a catalog name, ``FI:0000``, or ``@path/to/lookup.json``.

    User JSON contains an integer array, or an object with a ``lut`` array
    and an optional output width ``m``. FI always requires an explicit
    four-hex-digit subkey.
    """
    m = None
    if name.startswith("@"):
        value = json.loads(Path(name[1:]).expanduser().read_text())
        if isinstance(value, dict):
            value, m = value.get("lut"), value.get("m")
    elif name.casefold() == "midori64:0000":
        from .midori import lookup as midori_lookup

        value = midori_lookup()
    elif name.upper().startswith("FI:"):
        from .misty1 import Misty1

        key = name.partition(":")[2]
        if not re.fullmatch(r"[0-9a-fA-F]{4}", key):
            raise ValueError("FI requires four hexadecimal digits, e.g. FI:0000")
        value = Misty1(lookup("MISTY1_S7"), lookup("MISTY1_S9")).fi_lookup(int(key, 16))
    elif name.upper() in _extra():
        value = _extra()[name.upper()]
    else:
        data = {**_catalog()["catalog"], **_catalog()["extra"]}
        canonical = {key.casefold(): key for key in data}.get(name.casefold())
        if canonical is None:
            raise ValueError(f"unknown S-box {name!r}; use 'boxq list'")
        value = data[canonical]
        while isinstance(value, str):
            value = data[value]
    if not isinstance(value, list):
        raise ValueError("a lookup must contain an integer array")
    return Lookup(value, m)


def select(requested=(), *, all_names=False, selected=False, unique=False):
    chosen = list(requested) or (
        names() if all_names else SELECTED if selected else ["PRESENT", "AES"]
    )
    result, seen = [], set()
    for name in chosen:
        values = lookup(name)
        key = tuple(values)
        if not unique or key not in seen:
            result.append((name, values))
            seen.add(key)
    return result
