boxq
====

Explore differential, linear, and boomerang properties of S-boxes through
DDT, LAT, and BCT lookup tables. The package turns each table into a reduced
automaton whose paths encode input/output bit pairs. Shared subgraphs avoid
repeating identical parts of the table. A query supplies constraints on those
paths, such as fixed bits, masks, weights, value thresholds, or regular
expressions. The query engine walks the table and query automata together,
so it can count matches without listing every matching table cell.

This repository is the companion artifact of the paper "Querying
Differential, Linear, and Boomerang Tables with Quaternary Decision
Automata". It reproduces all nine tables and the numbers in the text, and
exports results as CSV, DKVP, or LaTeX.

Getting started
---------------

Install uv, then run from this checkout:

    uv sync --frozen
    uv run --frozen boxq --help
    uv run --frozen boxq generate-sboxes
    uv run --frozen boxq list
    uv run --frozen boxq matrix PRESENT -f csv
    uv run --frozen boxq query PRESENT --input 5 -f dkvp
    uv run --frozen boxq query AES --max-weight 4 --at-least 2 -f dkvp
    uv run --frozen boxq query PRESENT --against Noekeon -f dkvp

Use -o FILE to save a result, or leave it out to write to stdout. The output
formats are csv, dkvp (key=value pairs), and tex (a LaTeX tabular fragment).
Use --columns to select fields and --precision to set decimal places. Run
"uv run boxq COMMAND --help" for the full options of any command.

"stats" reports state counts, ratios and payload sizes, and "spectrum"
reports value frequencies. An input named @lookup.json reads an integer
lookup array from a local JSON file. FI keys are four hexadecimal digits,
such as FI:0000.

A JSON object {"lut": [...], "m": 4} declares a rectangular lookup from n
to m bits, with n and m at most 9. Its DDT or LAT is embedded in a
zero-filled square table of side 2^max(n, m), so the same automaton and
query engine apply; every query is restricted to the actual 2^n x 2^m cells.
BCT remains defined for square permutations only.

Reproducing a submission in progress
------------------------------------

Run the complete experiment suite (all nine tables, raw timing repetitions,
PRESENT endpoints/witnesses, per-S-box results, random samples, alternative
encodings, XZ streams and per-result manifests):

    uv run --frozen boxq reproduce --output-dir results/

The default pins timings to the first allowed CPU. --cpu selects another;
--repeats defaults to 15, after one Table 4 warm-up. PRESENT uses 15 complete
passes over its 240 fixed endpoints. Every result identifies its producer,
package fingerprint, Python/NumPy, CPU/governor/affinity and input/output
hashes. Table 4 records backend order, exact repetitions, setup and IQRs.
Preprocessing is excluded from query timers. The --reuse DIR option reuses
archived small-run JSON while preserving its original producer identity.

The three 16-bit DDTs are constructed, checked against all 2^32 cells,
inspected per level, and packed. Completed builds can be reused only after
full-verification evidence and output hashes are checked:

    uv run --frozen boxq experiment large --output-dir results/large
    uv run --frozen boxq reproduce --large-results results/large \
        --output-dir export/

Budget at least 16 GiB of free scratch disk and 8 GiB of available RAM for
these sequential large builds; retain additional disk for graph copies.
The partition option limits hash workspaces, not total process memory.
Midori uses at least 1024 MiB for its larger bottom dictionary; FI/random
use 128 MiB. No full 16-bit dense matrix is allocated. All outputs and
scratch files use the requested output directory. --small-only explicitly
omits the large experiments and labels the corresponding table exports.

Individual producers and conventional table exports remain available:

    uv run --frozen boxq experiment catalog --output-dir results/
    uv run --frozen boxq experiment random --output-dir results/ --seed 1
    uv run --frozen boxq experiment variants --output-dir results/
    uv run --frozen boxq experiment compression --output-dir results/
    uv run --frozen boxq experiment queries --output-dir results/
    uv run --frozen boxq experiment timing --output-dir results/
    uv run --frozen boxq experiment present --output-dir results/
    uv run --frozen boxq experiment sharing --graph results/large/fi-0000.qnf \
        --output-dir sharing/

The random driver enumerates all 8! permutations at width 3, then uses one
sequential NumPy PCG64 seed-1 stream: 200 samples at widths 4-7, 60 at width
8, and 5 at width 9. The separate 16-bit input uses PCG64 seed 2026. Every
sample retains its lookup, digest and state count.

XZ uses row-major uint8 indices into a sorted value dictionary, without the
dictionary in the compressed stream, XZ CRC64 and preset 9/extreme. The
retained .indices.bin can also be compressed with:

    xz --format=xz --check=crc64 -9e --stdout AES.indices.bin > AES.indices.xz

The independent NumPy/tuple oracle in experiments/reference.py preserves
matrix definitions and reductions from the reviewed reference prototype.
It checks every distinct catalog matrix and graph cell, plus the query
work counts. Ported drivers replace the original standalone scripts;
original ZIP files are historical inputs rather than a second executable
package. The same uv.lock environment runs production and oracle code.

An expanded product is a distinct non-pruned (table state, query state,
depth) triple, including rejected final states; dead transitions and bound
rejections do not count. Tables 3/5 use layered constructors in
analysis/queries.py, not regex minimization. Native checked/cache counters
measure calls and memo behavior and are not distinct-product counts.

The dense payload includes dictionary indices and signed dictionary values.
Graph payload includes four destinations per state and terminal values;
bitmap includes its bitset, nonzero indices and dictionary, without rank
metadata. Each whole payload is rounded once to bytes. Fixed headers are
excluded; serialized QDD files add 40 bytes. Tests compare estimates against
actual serializers, including small dictionaries that add visible bytes.

Setup and development
---------------------

Python and NumPy are sufficient; SageMath is not installed or imported.
The scientific corpus has 288 names (259 distinct lookups). It is generated
as external user data at $XDG_DATA_HOME/boxq/sboxes.json, defaulting to
~/.local/share/boxq/sboxes.json. Override that path with BOXQ_DATA. Generated
catalogs are excluded from the source repository and wheel.

The 16-bit builds, the Table 4 timings and the PRESENT search compile the
included C++17 source with g++ or clang++ (override with CXX). Native
execution is tested on 64-bit Linux. uv.lock pins Python dependencies and
.python-version the experiment interpreter; use uv sync --frozen.

    uv run python -m pytest -q
    uvx ruff format boxq tests
    uvx ruff check boxq tests
    clang-tidy boxq/_native/*.cpp -- -std=c++17

Catalog provenance and licensing
--------------------------------

The generator reads hash-pinned SageMath 10.9 declarations with a lightweight
SBox container. It needs no Sage installation. By default it downloads the
pinned source and COPYING.txt, writes the external catalog, and retains
.sources.json and .SAGE-COPYING.txt next to it. Local inputs work offline:

    uv run --frozen boxq generate-sboxes --sage-file sboxes.py \
        --sage-license-file COPYING.txt --output /path/to/sboxes.json
    BOXQ_DATA=/path/to/sboxes.json uv run --frozen boxq generate-sboxes \
        --sage-file sboxes.py --check

Sage revision: 686dc1a8d420c2e0aabadd4f602d9a0aa4690c50
Source SHA256:
8eaafe0400bb4697bb267d9d5bb6f9decf8dc77af7caf8a5636781caa945237b
Expanded lookup SHA256:
b0f35b0fd14fa8f1b80a85775211e1b7b8e0635e99b207bba561a9371c9ea4f0
https://github.com/sagemath/sage/blob/10.9/src/sage/crypto/sboxes.py

MISTY1 S7/S9 are bundled from Botan 2.19.5, retaining Botan's BSD-2-Clause
notice and source hashes in boxq/data/. FI:0000 and Midori64:0000 work without
the external catalog. --rfc-file optionally checks the Botan tables against
RFC 2994; it is not a required download. Botan does not supply the Midori
super S-box: our implementation follows the original paper's Sb0 and
MixColumn, computes S^4 -> M -> S^4 with zero intermediate key and MSB-first
nibbles, and is exhaustively tested against the frozen lookup digest.

The project's own code is licensed under BSD-2-Clause. Botan inputs retain
BSD-2-Clause terms. External Sage sources and extracted data retain their
upstream provenance and terms; the code license does not relicense those inputs.
See LICENSE, THIRD-PARTY-NOTICES.txt and boxq/data/BOTAN-LICENSE.txt.

This is research software, not constant-time production encryption code.
