"""A level as a saved design: the templates a designer starts from, the controls each offers, and the document a
design is saved as (the factory's roadmap 312 and 313; `docs/AUTHORING_LOOP.md`).

THREE KINDS OF STATE, the no-AI authoring plan's section 7: the DESIGN is authored source -- the template, the
choices, the intent -- saved and versioned, edited only through operations; the brief the pipeline reads is
DERIVED from it (`brief_from_design`) and recorded with each build; generated output is rebuilt, never edited.

EVERY CONTROL IS TRUTHFUL. `capabilities` lists each control a template offers with its support state:
``supported`` (a consumer reads it and the level changes), ``conditional`` (it does, with a stated substitution),
``intent`` (saved for the designer and for review; nothing builds from it yet). Option lists are read off the
owning code -- the road grammars, the surroundings, the times `_preset_for` resolves -- so a control cannot offer a
value its consumer does not know. `tests/service/test_design.py` holds both directions.

A DESIGN LIVES OUTSIDE THE GODOT PROJECT AND THE TOOL REPOS: ``<factory>/levels/<slug>/design.json``, its factory
workspace beside it in ``workspace/`` once a build makes one. ``levels`` is where START_HERE.md already puts a first
level, and the doctor's long-path check already measures it.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

from packages.service import schemas

DESIGN_SCHEMA = "gabagool.design.v1"
TEMPLATE_SCHEMA = "gabagool.template.v1"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DESIGN_FILE = "design.json"
DESIGN_KEYS = {"schema", "design_id", "revision", "template", "name", "slug", "choices", "intent",
               "created_at", "updated_at"}
#: The candidate counts the planner is asked for; `FactoryService.validate_brief`'s range.
CANDIDATES = (1, 8)


class DesignError(ValueError):
    """A design or a change to one that cannot be accepted; ``code`` is the stable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---- templates ------------------------------------------------------------------------------------------------

def templates() -> dict[str, dict]:
    """Every template shipped beside this module, by id."""
    out = {}
    for p in sorted(TEMPLATES_DIR.glob("*.json")):
        t = json.loads(p.read_text(encoding="utf-8"))
        if t.get("schema") != TEMPLATE_SCHEMA:
            raise DesignError("template_unreadable", "%s is not a %s" % (p.name, TEMPLATE_SCHEMA))
        problems = schemas.check(t, TEMPLATE_SCHEMA)
        if problems or t["template_id"] != p.stem:
            raise DesignError("template_unreadable", "%s: %s" % (
                p.name, "; ".join(problems) or "template_id %r is not the file's name" % t["template_id"]))
        out[t["template_id"]] = t
    return out


def template(template_id: str) -> dict:
    t = templates().get(template_id)
    if t is None:
        raise DesignError("unknown_template", "no template %r; known: %s" % (template_id, ", ".join(templates())))
    return t


# ---- the capability catalog -----------------------------------------------------------------------------------

_TIMES = (("morning", "Morning"), ("noon", "High noon"), ("afternoon", "Afternoon"), ("evening", "Evening"),
          ("midnight", "Midnight"))
_GRAMMAR_LABELS = {"T": "A T junction", "cross": "Crossroads",
                   "block": "A block with a service lane behind (a loop)",
                   "avenue": "One street, no junction (an avenue)"}
_SURROUNDING_LABELS = {"": "Chosen by the level", "borough": "More of the borough", "none": "Nothing (the plate's edge)",
                       "yards": "Rail and freight yards", "parkland": "Parkland", "roadside": "Roadside lots"}
#: The Level Standard's designer brief (docs/LEVEL_STANDARD.md, the walker's section 16) that no tool reads yet:
#: saved with the design for the designer and for review, and kept OUT of the pipeline's brief, whose fields are
#: level_factory.mission_brief.v0.1's. Its HEIST, LOCATION and TIME are the template, Streets / Beyond the edge and
#: Time of day; its PLAYERS is the Players control; its TARGET SESSION is the template's ``target_minutes``, which
#: Lot's pacing estimate is measured against.
STANDARD_INTENT = (("fantasy", "Fantasy", "longtext",
                    "One sentence: what the crew is trying to do here, and what makes this place worth it."),
                   ("scale", "Scale", "text", "Small, medium or large, in your words."),
                   ("density", "Density", "text", "How tightly the place is built and used."),
                   ("tone", "Tone", "text", "Three to five words: familiar, worn, mundane, warm..."),
                   ("playstyle", "Playstyle", "text", "Stealth, loud, or how one turns into the other."))
_INTENT_LABELS = {"route_shape": "Route shape", "objective_hypotheses": "Objective steps",
                  "extraction_relationship": "Way out", "verticality": "Verticality", "landmark": "Landmark",
                  "seed_policy": "Seed policy"}


def capabilities(template_id: str) -> list[dict]:
    """The controls a template offers, in form order, each with its support state, its options or range, its
    default (the template's own value), and what reads it."""
    from apps.cli.commands import UNBUILT_BRIEF_FIELDS
    from packages.core.models import MissionBrief
    from packages.pipeline.road_grammar import GRAMMARS
    from packages.pipeline.site_variation import SURROUNDINGS

    brief = template(template_id)["brief"]
    grammar = str(brief.get("road_grammar") or "T")
    rows = [
        {"key": "name", "label": "Level name", "type": "text", "default": template(template_id)["label"],
         "support": "supported", "consumer": "the level's display name and its folder"},
        {"key": "time_of_day", "label": "Time of day", "type": "choice",
         "options": [{"value": v, "label": lbl} for v, lbl in _TIMES], "default": brief.get("time_of_day", "afternoon"),
         "support": "supported", "consumer": "the Lux lighting preset (apps.cli.commands._preset_for)",
         "rebuilds": "lighting"},
        {"key": "weather", "label": "Weather", "type": "choice",
         "options": [{"value": "clear", "label": "Clear"},
                     {"value": "rain", "label": "Rain (an overcast day: it replaces the time of day)"}],
         "default": brief.get("weather", "clear"), "support": "conditional",
         "note": "Rain replaces the time of day: it is the Heavy Rain look, an overcast day.",
         "consumer": "the Lux lighting preset (apps.cli.commands._preset_for)", "rebuilds": "lighting"},
        {"key": "road_grammar", "label": "Streets", "type": "choice",
         "options": [{"value": g, "label": _GRAMMAR_LABELS.get(g, g)} for g in GRAMMARS], "default": grammar,
         "support": "supported", "consumer": "the site's road graph (packages.pipeline.road_grammar)",
         "rebuilds": "layout"},
        {"key": "surroundings", "label": "Beyond the edge", "type": "choice",
         "options": [{"value": s, "label": _SURROUNDING_LABELS.get(s, s)} for s in ("",) + tuple(SURROUNDINGS)],
         "default": str(brief.get("surroundings") or ""), "support": "supported",
         "consumer": "the backdrop recipe (packages.pipeline.site_variation)", "rebuilds": "backdrop"},
        {"key": "candidate_count", "label": "Layouts to generate", "type": "integer", "min": CANDIDATES[0],
         "max": CANDIDATES[1], "default": int(brief.get("candidate_count", 3)), "support": "supported",
         "consumer": "the planner's candidate seeds (packages.pipeline.planner)", "rebuilds": "layout"},
        {"key": "roof_props", "label": "Roof clutter", "type": "boolean", "default": bool(brief.get("roof_props", True)),
         "support": "supported", "consumer": "Zoo's rooftop scatter", "rebuilds": "art"},
        # the standard's PLAYERS (0.253.0): one spawn per crew member, and the crew Laser Tag plays
        {"key": "crew_size", "label": "Players", "type": "integer", "min": 1, "max": 4,
         "default": int(brief.get("crew_size", MissionBrief.__dataclass_fields__["crew_size"].default)),
         "support": "supported", "consumer": "Lot's crew spawns (lot/site_spawns.crew_spawns) and Laser Tag's crew",
         "rebuilds": "layout"},
    ]
    for key, label, kind, hint in STANDARD_INTENT:
        rows.append({"key": key, "label": label, "type": kind, "default": "", "support": "intent",
                     "note": "%s From the Level Standard's designer brief. Saved with the level for you and for "
                             "review; nothing builds from it yet." % hint})
    for key in UNBUILT_BRIEF_FIELDS:
        value = brief.get(key, [] if key == "objective_hypotheses" else "")
        rows.append({"key": key, "label": _INTENT_LABELS.get(key, key),
                     "type": "list" if isinstance(value, list) else "text", "default": value, "support": "intent",
                     "note": "Saved with the level for you and for review; nothing builds from it yet."})
    rows.append({"key": "notes", "label": "Notes", "type": "longtext", "default": "", "support": "intent",
                 "note": "For you and for review. Writing here does not change what is built."})
    return rows


def _controls(template_id: str) -> dict[str, dict]:
    return {c["key"]: c for c in capabilities(template_id)}


def check_value(control: dict, value):
    """``value`` for ``control``, or `DesignError` naming what is wrong with it."""
    key, kind = control["key"], control["type"]
    if kind == "choice":
        allowed = [o["value"] for o in control["options"]]
        if value not in allowed:
            raise DesignError("bad_choice", "%s must be one of %s, not %r" % (key, allowed, value))
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int) or not control["min"] <= value <= control["max"]:
            raise DesignError("bad_choice", "%s must be a whole number from %d to %d" % (key, control["min"],
                                                                                     control["max"]))
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise DesignError("bad_choice", "%s must be true or false" % key)
    elif kind == "list":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise DesignError("bad_choice", "%s must be a list of words" % key)
    elif not isinstance(value, str):
        raise DesignError("bad_choice", "%s must be text" % key)
    return value


# ---- the design document --------------------------------------------------------------------------------------

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return (s or "level")[:40]


def levels_root(factory_root: Path) -> Path:
    return Path(factory_root) / "levels"


def new_design(template_id: str, name: str, choices: dict | None = None, intent: dict | None = None) -> dict:
    """A revision-1 design from a template, its controls at the template's defaults but for ``choices`` and
    ``intent``, each checked against the catalog."""
    controls = _controls(template_id)
    if not isinstance(name, str) or not name.strip():
        raise DesignError("bad_choice", "a level needs a name")
    ch, it = {}, {}
    for key, c in controls.items():
        if key == "name":
            continue
        (ch if c["support"] in ("supported", "conditional") else it)[key] = c["default"]
    for given, into, kinds in ((choices or {}, ch, ("supported", "conditional")), (intent or {}, it, ("intent",))):
        for key, value in given.items():
            c = controls.get(key)
            if c is None or c["support"] not in kinds:
                raise DesignError("unknown_control", "%s is not a %s control of %s" % (
                    key, "choice" if kinds[0] == "supported" else "intent", template_id))
            into[key] = check_value(c, value)
    now = _now()
    return {"schema": DESIGN_SCHEMA, "design_id": uuid.uuid4().hex, "revision": 1, "template": template_id,
            "name": name.strip(), "slug": slugify(name), "choices": ch, "intent": it, "created_at": now,
            "updated_at": now}


def validate(doc) -> tuple[list[str], list[str]]:
    """``(problems, unknown_fields)`` for a design read from disk. Problems make it unusable; unknown fields are
    reported to the designer, never silently dropped."""
    if not isinstance(doc, dict):
        return ["the design is not a JSON object"], []
    problems = []
    if doc.get("schema") != DESIGN_SCHEMA:
        problems.append("schema is %r; this factory reads %r" % (doc.get("schema"), DESIGN_SCHEMA))
        return problems, []
    unknown = sorted(set(doc) - DESIGN_KEYS)
    # the document's shape is the schema's (0.252.0); the values under choices and intent are the catalog's, below
    problems += schemas.check(doc, DESIGN_SCHEMA)
    try:
        controls = _controls(str(doc.get("template")))
    except DesignError as exc:
        return problems + [str(exc)], unknown
    for part in ("choices", "intent"):
        if not isinstance(doc.get(part), dict):
            continue                                 # the schema has said so
        for key, value in doc[part].items():
            c = controls.get(key)
            if c is None:
                unknown.append("%s.%s" % (part, key))
                continue
            try:
                check_value(c, value)
            except DesignError as exc:
                problems.append(str(exc))
    return problems, unknown


def write_design(folder: Path, doc: dict) -> Path:
    """Save ``doc`` as ``folder/design.json``, atomically: the whole file or the previous one. A document that is
    not a valid ``gabagool.design.v1`` raises `schemas.SchemaError` and nothing is written."""
    schemas.require(doc, DESIGN_SCHEMA)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / DESIGN_FILE
    tmp = folder / (".design.%s.tmp" % uuid.uuid4().hex)
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return path


def read_design(path: Path) -> dict:
    """``{"design", "problems", "unknown_fields", "path"}`` for a saved design; `DesignError` when it cannot be read."""
    path = Path(path)
    if path.is_dir():
        path = path / DESIGN_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DesignError("no_design", "no design at %s" % path) from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DesignError("design_unreadable", "%s is not UTF-8 JSON: %s" % (path, exc)) from None
    problems, unknown = validate(doc)
    return {"design": doc, "problems": problems, "unknown_fields": unknown, "path": str(path)}


def update_design(doc: dict, expected_revision, choices: dict | None = None, intent: dict | None = None,
                  name: str | None = None) -> dict:
    """``doc`` changed by ``choices``, ``intent`` and ``name``, as revision + 1. ``expected_revision`` is the revision
    the caller edited: when the saved design has moved since, the change is refused (``conflict``) rather than laid
    over somebody else's. Every value is checked against the template's catalog; an unchanged value is allowed and a
    change that changes nothing is refused (``nothing_changed``), so a revision always records a difference."""
    if isinstance(expected_revision, bool) or expected_revision != doc.get("revision"):
        raise DesignError("conflict", "this level was saved as revision %s since revision %s was opened; open it again"
                          % (doc.get("revision"), expected_revision))
    controls = _controls(doc["template"])
    new = json.loads(json.dumps(doc))
    for given, part, kinds in ((choices or {}, "choices", ("supported", "conditional")),
                               (intent or {}, "intent", ("intent",))):
        for key, value in given.items():
            c = controls.get(key)
            if c is None or c["support"] not in kinds:
                raise DesignError("unknown_control", "%s is not a %s control of %s" % (
                    key, "choice" if part == "choices" else "intent", doc["template"]))
            new[part][key] = check_value(c, value)
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            raise DesignError("bad_choice", "a level needs a name")
        new["name"] = name.strip()
    if (new["choices"], new["intent"], new["name"]) == (doc["choices"], doc["intent"], doc["name"]):
        raise DesignError("nothing_changed", "nothing to save: every value is what revision %d says" % doc["revision"])
    new["revision"] = doc["revision"] + 1
    new["updated_at"] = _now()
    return new


def rebuilds_between(old: dict, new: dict) -> list[str]:
    """What a change from ``old`` to ``new`` makes the pipeline rebuild: the `rebuilds` words of every control whose
    value moved (layout, lighting, backdrop, art), sorted. Intent rebuilds nothing."""
    controls = _controls(new["template"])
    words = set()
    for key, value in new["choices"].items():
        if old["choices"].get(key) != value and controls.get(key, {}).get("rebuilds"):
            words.add(controls[key]["rebuilds"])
    return sorted(words)


def free_folder(root: Path, slug: str) -> Path:
    """``root/slug``, or ``root/slug_2``, ``_3``... -- a folder no design is in yet."""
    n, folder = 1, Path(root) / slug
    while (folder / DESIGN_FILE).exists():
        n += 1
        folder = Path(root) / ("%s_%d" % (slug, n))
    return folder


# ---- what the pipeline receives ---------------------------------------------------------------------------------

_STANDARD_KEYS = {key for key, *_ in STANDARD_INTENT}


def mission_id(doc: dict) -> str:
    return "%s_001" % doc["slug"]


def brief_from_design(doc: dict) -> dict:
    """The mission brief the pipeline reads, derived from the design: the template's brief, the choices and the
    intent laid over it, the mission named for the design. Notes travel as the brief's ``notes``."""
    t = template(doc["template"])
    brief = json.loads(json.dumps(t["brief"]))
    brief["mission_id"] = mission_id(doc)
    brief["display_name"] = doc["name"]
    for key, value in doc["choices"].items():
        brief[key] = value
    for key, value in doc["intent"].items():
        if key in _STANDARD_KEYS:
            continue                    # the designer's, not the pipeline's: no brief field carries it
        if key == "notes":
            if value:
                brief["notes"] = value
            continue
        brief[key] = value
    if brief.get("road_grammar") == "T":
        brief["road_grammar"] = ""
    return brief
