"""The site's cover is a kit job (roadmap 22).

The planner fans out a `zoo_kit_build` for archetype "site" over Lot's
`site.slots.json`, and the themed site assembly waits for it, so the modules
exist when Lot resolves `cover_modules`.
"""
import inspect

from packages.pipeline import planner


def test_the_planner_source_fans_out_a_site_kit_and_the_themed_site_waits():
    src = inspect.getsource(planner)
    i = src.index('archetype="site"')
    assert "_STAGE_ZOO_KIT" in src[i - 400:i]
    assert "depends_on=[compose_jid, site_kit_jid]" in src


def test_the_spec_writer_carries_cover_modules():
    import apps.cli.commands as cmds
    sig = inspect.signature(cmds._write_site_spec)
    assert "cover_modules" in sig.parameters
    assert '"site.slots.json"' in inspect.getsource(cmds)
