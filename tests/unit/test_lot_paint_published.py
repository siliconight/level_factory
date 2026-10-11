"""The Lot adapter publishes the paint meshes beside the scene (0.177.2).

Cold run 9234: Lot 0.114.0 wrote `site_marks_<colour>.obj` beside `site.tscn`
and declared each as a Mesh ext_resource; `collect_outputs` published
.tscn/.json/.csv/.glb/.gd/.png and the export's closure gate refused the
package over two relative references resolving to nothing -- three stages
after the file was dropped, the same shape as cold run 9016's skins.
"""
from adapters.lot import LotAdapter


def test_the_lot_adapter_publishes_the_paint_meshes_beside_the_scene(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "site.tscn").write_text(
        '[gd_scene]\n[ext_resource type="Mesh" path="site_marks_090_090_088.obj" '
        'id="site_marks_090_090_088"]\n', encoding="utf-8")
    (work / "site_marks_090_090_088.obj").write_text("o site_marks_090_090_088\nv 0 0 0\n",
                                                     encoding="utf-8")
    (work / "site.markings.json").write_text("{}", encoding="utf-8")
    (work / "notes.txt").write_text("not published", encoding="utf-8")
    got = {p.relative_to(work).as_posix()
           for p in LotAdapter().collect_outputs({}, {"work_dir": str(work)})}
    assert got == {"site.tscn", "site_marks_090_090_088.obj", "site.markings.json"}
