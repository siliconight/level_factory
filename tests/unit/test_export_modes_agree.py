"""The CLI's --mode choices and the exporter's modes are one list.

Written after `export --mode art-unlit` failed on a real workspace with
`internal error: 'art-unlit'` -- a KeyError from a third list holding the
same fact. This reads main.py's argparse choices out of the SOURCE rather
than from a copy, so the two cannot drift apart again quietly.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.exporting.export import MODES  # noqa: E402

MAIN = ROOT / "apps" / "cli" / "main.py"


def _mode_choices():
    """Every `choices=[...]` attached to a `--mode` argument in main.py.

    Parsed, not imported: `main.py` builds its parser inside a function and
    importing it to ask would run the CLI's own wiring. The literal is what
    a user is actually constrained by.
    """
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "--mode"):
            continue
        for kw in node.keywords:
            if kw.arg == "choices" and isinstance(kw.value, (ast.List, ast.Tuple)):
                found.append(frozenset(
                    e.value for e in kw.value.elts
                    if isinstance(e, ast.Constant)))
    return found


def test_main_declares_mode_choices_somewhere():
    """If this fails the parse broke, and every test below is vacuous."""
    assert _mode_choices(), "no --mode choices found in main.py"


def test_every_cli_choice_is_a_mode_the_exporter_knows():
    """THE BUG. `art-unlit` was a choice the code could not honour."""
    for choices in _mode_choices():
        unknown = choices - MODES
        assert not unknown, f"CLI offers {sorted(unknown)}, exporter knows {sorted(MODES)}"


def test_every_mode_the_exporter_knows_is_reachable_from_the_cli():
    """The other direction: a mode nobody can type is a mode nobody uses."""
    offered = set()
    for choices in _mode_choices():
        offered |= set(choices)
    missing = MODES - offered
    assert not missing, f"exporter knows {sorted(missing)} but no --mode offers it"


def test_all_the_mode_arguments_offer_the_same_set():
    """`export` and `portability-test` both take --mode. A package you can
    build in a mode you cannot then portability-test is half a feature."""
    sets = _mode_choices()
    assert len(set(sets)) == 1, f"--mode choices differ between commands: {sets}"


def test_cmd_export_does_not_keep_its_own_copy():
    """The identity dict, asserted gone.

    `mode_map` mapped each CLI string to the constant of that same value and
    existed only to raise KeyError on a mode it had not learned. Its absence
    is the fix; this is what stops it growing back.
    """
    src = (ROOT / "apps" / "cli" / "commands" / "__init__.py").read_text(
        encoding="utf-8")
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    assert "mode_map" not in code
