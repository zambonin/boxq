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
