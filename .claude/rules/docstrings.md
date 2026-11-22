---
paths:
  - "Toolbox/skatkis/**/*.py"
  - "Toolbox/market_data/**/*.py"
  - "Toolbox/value_investing/**/*.py"
  - "Toolbox/hand_o_midas/**/*.py"
  - "Toolbox/financial_planning/**/*.py"
---

# Docstrings

Docstrings are read by people and served to agents by the Midas index, so they follow
one structure. Code stays authoritative: a docstring describes what the code does, never
what it should do. Keep production identifiers exactly.

## Module docstring

numpydoc-style underlined sections, in this order. Omit a section that does not apply.

```
"""
<path from Toolbox/, e.g. value_investing/layers/graham.py>
<dashes, same length>
<One-line summary.>

<One to three paragraphs: purpose, where it sits in the pipeline, key ideas.>

Owns
----
<what this module is the single owner of, e.g. rules G1–G7, E1–E6>

Must not
--------
<what it must not compute or do, with the owner in brackets where known>

Public API
----------
name(signature-sketch)
    One line on what it does.

Computes
--------
<concept>, <concept> : <function>
    Formula or convention in one or two lines: units, period basis, bounds.

Dependency rule
---------------
<what it may and may not import>
"""
```

## `Computes` section

Every module that calculates a financial quantity lists it, so people and agents can
find an existing calculation before writing a new one. Required for
`skatkis/financial_logic`, `skatkis/backtest` and tool layers; omit it in modules that
only move, map or validate data.

- One entry per function: the concepts it calculates, comma-separated, in the words a
  quant would search for (`current ratio`, `graham number`, `excess return`), then
  ` : ` and the function name.
- The function must be defined in the module itself; a layer that calls a shared
  function does not list it.
- The description states the formula as the code implements it.

## Function and class docstrings

- Every public function and class has one; private helpers at least a one-line summary
  unless self-evident.
- Non-trivial public functions: summary, then `Parameters`, `Returns`, `Raises`; add
  `Notes` for behaviour that is easy to get wrong (mutation, ordering, NaN handling,
  bounds, look-ahead).
- `Parameters` and `Returns` give dtypes and units (USD, ratio, fraction, per share);
  calculation helpers give the formula, bounds and boundary behaviour (exact threshold,
  zero denominator).
- A rule implementation names its rule ID and the spec or README section that defines
  it (the reference chain, `midas/instructions/scribe.md`).
