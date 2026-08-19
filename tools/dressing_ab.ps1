# Does the MultiMesh buffer layout match the verified node transforms?
#
# The one assumption in packages/exporting/dressing_scene.py that could not be
# checked without Godot. This checks it NUMERICALLY, in a real window:
# --headless is WRONG for the A/B step and the script no longer uses it there.
# MultiMesh.get_instance_transform(i) decodes the buffer through the engine's
# own accessor, so comparing it against the node scene's Transform3D tests
# exactly that convention and nothing else.
#
# Placeholder BoxMeshes stand in for the real assets on purpose. How a .glb
# becomes an addressable Mesh resource is a SEPARATE unknown; tangling it into
# this run would give one experiment that answers neither question.
#
#   pwsh -ExecutionPolicy Bypass -File dressing_ab.ps1

$ErrorActionPreference = "Stop"
$F   = "C:\Projects\gabagool_studios\gabagool_factory"
$Man = "$F\_dress\dressing.json"          # written by the chain re-run
$Stage = "$F\_dress\ab_project"

$Godot = $env:GODOT
if (-not $Godot) {
  $Godot = (Get-Command godot -ErrorAction SilentlyContinue).Source
}
if (-not $Godot) {
  $c = Get-ChildItem "C:\godot","C:\Program Files\Godot" -Filter "Godot*.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { $Godot = $c.FullName }
}
if (-not $Godot) { Write-Error "Godot not found. Set `$env:GODOT to the exe."; exit 1 }
Write-Host "Godot: $Godot"

if (-not (Test-Path $Man)) {
  Write-Error "no manifest at $Man -- run the chain first (step 4 writes it)."
  exit 1
}

New-Item -ItemType Directory -Force -Path "$Stage\dressing" | Out-Null
Copy-Item "$PSScriptRoot\dressing_ab.gd","$PSScriptRoot\make_placeholder_meshes.gd" -Destination $Stage -Force

# The same project.godot lot/walktest.py:ensure_project writes -- not my own
# guess at one. Deliberately no `config/features`: pinning a Godot version
# here would make this harness disagree with whatever Godot the rest of the
# pipeline runs, and yours is 4.7.
#
# One Set-Content, which already appends the trailing newline. The first
# draft used -NoNewline plus an Add-Content to append one, and Add-Content
# bound its positional arguments differently than I assumed.
@'
config_version=5

[application]

config/name="dressing_ab"
'@ | Set-Content -Encoding utf8 "$Stage\project.godot"

# Placeholder meshes first, so the scenes below have something to reference.
& $Godot --headless --path $Stage --script "res://make_placeholder_meshes.gd"
if ($LASTEXITCODE -ne 0) { Write-Error "placeholder mesh generation failed"; exit 1 }

@'
{"pebble": "res://dressing/pebble.tres", "rubble_frag": "res://dressing/rubble_frag.tres",
 "weed_tuft": "res://dressing/weed_tuft.tres", "litter_scrap": "res://dressing/litter_scrap.tres"}
'@ | Set-Content -Encoding utf8 "$Stage\paths.json"

# The same manifest, written both ways.
Push-Location "$F\level_factory"
python -m packages.exporting.dressing_scene $Man --mesh-paths "$Stage\paths.json" `
    --out "$Stage\dressing_mm.tscn" --root-name dressing
python -m packages.exporting.dressing_scene $Man --mesh-paths "$Stage\paths.json" `
    --mode nodes --out "$Stage\dressing_nodes.tscn" --root-name dressing
Pop-Location

# Import pass, so the .tres resources resolve before the scenes load.
& $Godot --headless --path $Stage --import

# The A/B runs WITHOUT --headless, and that is the whole point of this line.
# MultiMesh instance transforms live in the RenderingServer, not on the
# resource, and --headless uses RendererDummy, which stores none of them --
# every transform reads back as identity and the comparison indicts correct
# code. A window will flash; the script quits immediately.
Write-Host "`n=== A/B (windowed: --headless would read the dummy renderer) ==="
& $Godot --path $Stage --script "res://dressing_ab.gd"
$rc = $LASTEXITCODE
Write-Host "`nexit $rc  (0 = layout right, 1 = layout wrong, 3 = the test did not run)"
exit $rc
