"""What setup downloads is said first, licences included, and every pin is held to its licence (0.255.0).

The walker's call, 2026-10-26: a release carries no third-party package; the user's own setup downloads them from
PyPI (the factory's docs/THIRD_PARTY.md). So the user is told what and under which licences BEFORE anything
downloads, and `make_venv` refuses an environment whose packages are not the recorded versions under the recorded
licences -- moving a pin onto a release that changed its licence fails instead of shipping. FAILS ON 0.254.0.
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packages.tools import interpreter  # noqa: E402

HELD = {**interpreter.PINNED, **interpreter.CONSTRAINED}


def _answer(**override):
    """A fake interpreter answering the licence question as recorded, with ``override`` changes."""
    found = {n: [HELD[n], lic] for n, lic in interpreter.LICENSES.items()}
    found.update(override)

    def run(argv, **kw):
        if argv[1:3] == ["-m", "venv"]:
            py = Path(argv[-1], *(("Scripts", "python.exe") if sys.platform.startswith("win") else ("bin", "python")))
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("stand-in\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[1:2] == ["-c"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(found) + "\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


def test_every_download_has_a_recorded_licence_and_is_said_first():
    assert set(interpreter.LICENSES) == set(HELD)
    said = interpreter.downloads_said()
    assert "12 packages from PyPI" in said and "THIRD_PARTY.md" in said
    for row in interpreter.downloads():
        assert "%s %s (%s)" % (row["name"], row["version"], row["licence"]) in said


def test_an_environment_as_recorded_is_accepted(tmp_path):
    py, err = interpreter.make_venv(tmp_path, "/base/python", run=_answer())
    assert err == "" and py


@pytest.mark.parametrize("override,said", [
    ({"wrapt": ["2.5.1", "BSD-3-Clause"]}, "wrapt 2.5.1 declares licence 'BSD-3-Clause', not the recorded"),
    ({"pillow": ["12.4.0", "MIT-CMU"]}, "pillow is 12.4.0, not the pinned 12.3.0"),
    ({"pygltflib": [None, None]}, "pygltflib is not installed"),
])
def test_a_package_not_as_recorded_refuses_the_environment(tmp_path, override, said):
    py, err = interpreter.make_venv(tmp_path, "/base/python", run=_answer(**override))
    assert py == "" and said in err


def test_an_interpreter_that_does_not_answer_is_a_problem_not_a_pass():
    run = lambda argv, **kw: SimpleNamespace(returncode=1, stdout="", stderr="boom")  # noqa: E731
    assert interpreter.licence_problems("/x/python", run=run) == ["/x/python did not say which packages it has (exit 1)"]


def test_the_question_reads_real_metadata():
    """The script itself, run by this interpreter against distributions it has: every answer is a version and a
    licence read the way the recorded ones were."""
    got = subprocess.run([sys.executable, "-c", interpreter._ASK_LICENCES, "pytest", "no-such-distribution"],
                         capture_output=True, text=True, timeout=120)
    found = json.loads(got.stdout.strip().splitlines()[-1])
    assert found["no-such-distribution"] == [None, None]
    assert found["pytest"][0] and found["pytest"][1] == "MIT"


def test_the_factorys_own_environment_is_as_recorded():
    """Where the factory has prepared its environment, it holds the recorded versions under the recorded licences."""
    from packages.tools import discovery
    root = discovery.factory_root()
    py = interpreter.venv_python(root / interpreter.VENV) if root else None
    if py is None:
        pytest.skip("no factory .venv on this machine")
    assert interpreter.licence_problems(str(py)) == []
