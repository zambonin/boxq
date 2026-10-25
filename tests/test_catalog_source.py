"""Portable catalog import, without a Sage installation or copied catalog."""

import hashlib
import sys

import pytest

from boxq.core import catalog_source


def test_unknown_catalog_is_rejected_before_execution():
    with pytest.raises(ValueError, match="pinned"):
        catalog_source.read_catalog(b"raise AssertionError('must not execute')")


def test_lookup_extraction_preserves_aliases_without_sage(monkeypatch):
    source = b"""import sys
from sage.crypto.sbox import SBox
from sage.misc.functional import is_even
Example = SBox([1, 0], big_endian=True)
Alias = Example
sboxes = {k: v for k, v in vars(sys.modules[__name__]).copy().items() if isinstance(v, SBox)}
"""
    monkeypatch.setattr(catalog_source, "SAGE_SOURCE_SHA256", hashlib.sha256(source).hexdigest())
    before = {key for key in sys.modules if key == "sage" or key.startswith("sage.")}
    assert catalog_source.read_catalog(source) == {"Example": [1, 0], "Alias": [1, 0]}
    after = {key for key in sys.modules if key == "sage" or key.startswith("sage.")}
    assert before == after
    assert "_boxq_upstream_catalog" not in sys.modules
