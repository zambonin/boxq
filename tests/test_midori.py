"""The independent Midori definition matches the reference experiment input."""

import hashlib
import json

import pytest

from boxq.core.midori import lookup, midori64_super_sbox


def test_complete_midori_lookup():
    values = lookup()
    assert len(set(values)) == 65536
    assert all(values[values[x]] == x for x in range(65536))
    assert (
        hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
        == "70753b06e452b573dd0128093a81be572c0f1ff772b077dd0e9729706ecd7d51"
    )
    assert [values[x] for x in (0, 1, 0x1234, 65535)] == [0, 0x1110, 0xC79E, 65535]


@pytest.mark.parametrize("value", [-1, 65536, True, 1.0])
def test_midori_rejects_nonwords(value):
    with pytest.raises(ValueError):
        midori64_super_sbox(value)
