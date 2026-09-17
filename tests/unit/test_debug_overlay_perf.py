"""The walk overlay carries a perf readout, and the readout does not bend.

The walker walked cold run 9062's card shop on 2026-09-16, reported it
"chugging", and asked for framerate on screen "for us to start taking into
consideration as we add more stuff". A frame counter is easy; a frame counter
that can be believed is the part with rules, and every rule below was bought by
a measurement that came out against the obvious implementation.

WHY EACH ONE EXISTS, measured on this machine, Godot 4.7.stable,
gl_compatibility, RTX 2060, in the card block package itself:

* `Engine.get_frames_per_second()` REFRESHES AT 1 Hz. It held one value across
  300 consecutive frames and then stepped. An fps line built on it cannot show
  a stutter, which is the only thing the walker asked it to show -- so the
  window is measured in this file, off the clock.

* `_process`'s delta IS CLAMPED. Three stations reported 150.000 ms on the nose
  as their worst frame while the same frames, timed between two
  `Time.get_ticks_usec()` calls, were 191, 356 and 527 ms. A meter built on the
  delta understates every real hitch and does it consistently.

* `Performance.TIME_PROCESS` IS NOT THIS FRAME'S CPU TIME. It is the worst idle
  step within the last completed second: a deliberate 60 ms stall came back as
  68.317 ms and was still being reported 285 frames later. It is shown, and it
  is labelled as the hitch it is rather than as a frame time.

* THE MEASUREMENT MUST NOT MOVE WHAT IT MEASURES. The per-frame path is a clock
  read and three adds -- 8.9-19.1 us measured -- and everything expensive waits
  for the sample tick, 215-385 us, PERF_HZ times a second. A per-frame monitor
  read or a per-frame string would be the ruler bending.

These read the GDScript rather than run it -- the unit suite has no Godot -- so
they hold the SHAPE those measurements depend on. Every one of them fails
against 0.94.0's overlay, which had no perf panel at all.

Run:  python -m pytest tests/unit/test_debug_overlay_perf.py
"""
import re
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2]
          / "assets" / "godot" / "debug_overlay.gd")


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _func(src: str, name: str) -> str:
    """The body of `func <name>`, up to the next top-level `func`."""
    m = re.search(r"^func %s\(.*?(?=^func |\Z)" % re.escape(name), src,
                  re.S | re.M)
    assert m, f"no func {name} in {SCRIPT.name}"
    return m.group(0)


def test_the_readout_answers_all_five_questions_asked_of_it():
    """fps, frame time, GPU time, draw calls, triangles -- the brief's list.

    Checked at the call site rather than in the text, because a label saying
    "gpu" over a number that came from somewhere else is exactly the failure
    this file is about.
    """
    body = _func(_src(), "_perf_text")
    assert "viewport_get_measured_render_time_gpu" in _src(), "no GPU figure"
    assert "RENDER_TOTAL_DRAW_CALLS_IN_FRAME" in body, "no draw calls"
    assert "RENDER_TOTAL_PRIMITIVES_IN_FRAME" in body, "no triangle count"
    assert "fps" in body and "ms/frame" in body, "no fps or frame time"


def test_frame_time_is_wall_clock_not_the_clamped_delta():
    """The engine's delta tops out; ticks_usec does not. See the header."""
    tick = _func(_src(), "_perf_tick")
    assert "Time.get_ticks_usec" in tick, (
        "frame time must come off the wall clock -- _process's delta is "
        "clamped and reports a 527 ms hitch as 150.000 ms")
    assert not re.search(r"_acc_time \+= delta", tick), (
        "the clamped delta is being accumulated as if it were a frame time")


def test_the_window_carries_a_worst_frame_and_not_only_a_mean():
    """A mean of 60 fps stutters. What the walker felt is the worst frame."""
    text = _func(_src(), "_perf_text")
    assert "worst frame" in text, "no worst-frame line"
    tick = _func(_src(), "_perf_tick")
    assert "_acc_worst" in tick, "nothing tracks the worst frame per bucket"


def test_the_expensive_half_runs_on_the_sample_clock_only():
    """No monitor read, no formatting and no Label write on an ordinary frame.

    The test is positional: everything costly must sit AFTER the period test
    that returns early, or it is running every frame whatever the constant
    says.
    """
    tick = _func(_src(), "_perf_tick")
    m = re.search(r"if _acc_time \* PERF_HZ < 1\.0:\s*\n\s*return", tick)
    assert m, "no sample-period gate in _perf_tick"
    before = tick[:m.start()]
    for costly in ("Performance.get_monitor", "_perf_text", "_perf.text",
                   "viewport_get_measured_render_time", '" % ['):
        assert costly not in before, (
            f"{costly!r} runs on every frame, ahead of the sample gate")
    assert "PERF_HZ" in _src()


def test_the_sample_rate_is_a_named_constant_that_is_actually_read():
    """A knob with no effect is a defect -- grep for the value being used."""
    src = _src()
    assert re.search(r"^const PERF_HZ :=", src, re.M), "PERF_HZ is not a const"
    uses = len(re.findall(r"\bPERF_HZ\b", src))
    assert uses >= 2, "PERF_HZ is declared and never read"
    assert re.search(r"^const PERF_BUCKETS :=", src, re.M)
    assert len(re.findall(r"\bPERF_BUCKETS\b", src)) >= 2, (
        "PERF_BUCKETS is declared and never read")


def test_both_panels_can_be_up_at_once():
    """Position AND perf: the walker reports WHERE a defect is and what it
    cost, in one screenshot. Separate keys, and neither touches the other's
    panel."""
    inp = _func(_src(), "_input")
    assert "KEY_F3" in inp and "KEY_F4" in inp, "the two panels share a key"
    f3, f4 = inp.split("KEY_F4", 1)
    assert "_perf_shown" not in f3, "F3 is switching the perf panel too"
    assert "_shown = not _shown" not in f4, "F4 is switching the F3 panel too"


def test_off_is_off_rather_than_hidden():
    """A hidden panel that keeps sampling is a cost with nothing to show for
    it, and the GPU timer queries are part of that cost."""
    tick = _func(_src(), "_perf_tick")
    assert re.search(r"if not _perf_shown[^\n]*:\s*\n\s*return", tick), (
        "_perf_tick keeps accumulating while the panel is down")
    inp = _func(_src(), "_input")
    assert "_set_measuring(_perf_shown)" in inp, (
        "the viewport render-time measurement does not follow the panel")
    assert "_reset_window()" in inp, (
        "the window survives the toggle, so frames from before it would be "
        "reported as if they were now")


def test_an_unmeasured_gpu_is_not_reported_as_zero():
    """Compatibility DOES return a GPU figure on this rig. Somewhere it will
    not, and a flat 0.00 ms would read as a measurement of nothing."""
    src = _src()
    assert "_gpu_seen" in src
    assert "n/a" in _func(src, "_perf_text"), (
        "an unavailable GPU timer must say so rather than print 0.00")


def test_the_worst_step_line_is_not_sold_as_a_frame_time():
    """TIME_PROCESS is a per-second maximum. Labelling it "cpu" would be the
    cheap observable standing in for the expensive truth, in the one file whose
    whole job is to not do that."""
    text = _func(_src(), "_perf_text")
    m = re.search(r'"([^"]*)" % \[\s*\n?\s*1000\.0 \* Performance\.get_monitor'
                  r'\(Performance\.TIME_PROCESS\)', text)
    assert m, "TIME_PROCESS is not formatted where this expects it"
    assert "worst step" in m.group(1), (
        "TIME_PROCESS is being presented as a frame time; it is the worst "
        "idle step in the last completed second")


def test_the_readout_says_whose_figures_these_are():
    """The walk copy runs the PACKAGE's renderer and light budget, so the
    number is the package's. A frame time with no resolution or vsync state
    beside it is not comparable to anything."""
    ctx = _func(_src(), "_context_line")
    for setting in ("application/config/name",
                    "rendering/renderer/rendering_method",
                    "rendering/limits/opengl/max_renderable_lights"):
        assert setting in ctx, f"the context line does not report {setting}"
    assert "window_get_vsync_mode" in ctx, (
        "without vsync state, a capped 60 fps reads as headroom")
    assert "window_get_size" in ctx, "no resolution beside the frame time"


def test_the_debug_build_guard_still_covers_everything():
    """Standing rule: walk copies only, never a player export. The guard is
    the first thing _ready does and it frees the node, so nothing below it --
    including every line of the perf panel -- can run in a release build."""
    ready = _func(_src(), "_ready")
    head = ready.split("\n", 6)
    assert "OS.is_debug_build()" in head[1], (
        "the debug-build guard is no longer the first thing _ready checks")
    assert "queue_free()" in "\n".join(head[:6])
    assert ready.index("queue_free()") < ready.index("PanelContainer.new()")


@pytest.mark.parametrize("trap", [
    # No implicit adjacent-string concatenation, and `%` binds tighter than
    # `+`. gdcheck.py owns these; this is the cheap version that runs in the
    # suite everyone runs.
    r'"\s*\n\s*"',
])
def test_no_gdscript_string_traps(trap):
    assert not re.search(trap, _src()), (
        "adjacent string literals across lines do not concatenate in "
        "GDScript -- see CLAUDE.md")
