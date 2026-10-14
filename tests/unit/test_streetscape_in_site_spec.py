"""The site says what its street is (Level Factory 0.205.0, factory roadmap 241).

Lot 0.123.0 plants a city block's trees -- one every 30 ft, 30 ft clear of a corner, Philadelphia's own siting
guidelines (the factory root's `docs/reference/STREET_TREES.md`) -- on a street whose site spec says
`streetscape: "urban"`, and a strip's where it says nothing. The compose stage decides urban (`_urban`: a library
and `models.streetscape_effective` of the brief's field and its Empties) and until now kept the answer to itself.

Read as source: the stage runs only against a lot library, and the cold run that proves this release reads the
key off its own site spec.
"""
import inspect

import apps.cli.commands as cmds


def test_the_spec_is_told_where_the_stage_decides_and_nowhere_else():
    src = inspect.getsource(cmds._write_site_spec)
    decided = src.find("    _urban = bool(library) and bool(_se(")
    told = src.find("    if _urban:\n        spec[\"streetscape\"] = \"urban\"\n")
    assert decided != -1, "the stage decides urban here"
    assert told > decided, "and writes it into the spec right after"
    assert src.count("spec[\"streetscape\"]") == 1, "a strip's spec carries no key"
