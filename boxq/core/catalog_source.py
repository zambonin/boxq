"""Read the pinned upstream lookup declarations without installing SageMath.

The upstream module is evaluated only after its exact source hash is checked.
Only the SBox value container is substituted; no Sage library is imported.
Source and extracted data keep their upstream provenance and terms.
"""

import ast
import hashlib
import sys
from types import ModuleType

SAGE_REVISION = "686dc1a8d420c2e0aabadd4f602d9a0aa4690c50"
SAGE_BASE = f"https://raw.githubusercontent.com/sagemath/sage/{SAGE_REVISION}/"
SAGE_URL = SAGE_BASE + "src/sage/crypto/sboxes.py"
SAGE_SOURCE_SHA256 = "8eaafe0400bb4697bb267d9d5bb6f9decf8dc77af7caf8a5636781caa945237b"


class _Lookup:
    def __init__(self, *values, **options):
        self.values = (
            list(values[0])
            if len(values) == 1 and isinstance(values[0], (list, tuple))
            else list(values)
        )


def read_catalog(source):
    """Extract lookup arrays from the exact Sage10.9 source used by the paper."""
    if hashlib.sha256(source).hexdigest() != SAGE_SOURCE_SHA256:
        raise ValueError("catalog source differs from the pinned SageMath10.9 module")
    tree = ast.parse(source.decode("utf-8"))
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.ImportFrom)
            and node.module in ("sage.crypto.sbox", "sage.misc.functional")
        )
    ]
    name = "_boxq_upstream_catalog"
    module = ModuleType(name)
    module.__dict__.update(SBox=_Lookup, is_odd=lambda x: x % 2 == 1, is_even=lambda x: x % 2 == 0)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(tree, "pinned-sboxes.py", "exec"), module.__dict__)
        return {key: list(value.values) for key, value in module.sboxes.items()}
    finally:
        if previous is None:
            del sys.modules[name]
        else:
            sys.modules[name] = previous
