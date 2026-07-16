# ============================================================
#  smoke_lf.ps1 (v0.9.1) - Level Factory hardware smoke for the
#  gabagool_factory layout. Home: level_factory\tools\ - every
#  path derives from the repo location.
#
#  Stages: junction tool dir -> install -> fast pytest ->
#  real-tool smoke -> workspace init + tools.local.json ->
#  doctor -> verify-contracts + verify-manifest -> batch/brief ->
#  functional-lock -> approvals -> PRESENTATION (now includes
#  zoo_fixtures_build + lux_fixture_gate - the leg this run
#  proves on real Blender+Godot) -> fixture-gate evidence dump ->
#  presentation/regression approvals -> export + portability ->
#  status/validate.
#
#  Run:
#  powershell -ExecutionPolicy Bypass -File C:\Projects\gabagool_studios\gabagool_factory\level_factory\tools\smoke_lf.ps1
# ============================================================

$ErrorActionPreference = "Continue"
$LFRepo  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Factory = (Resolve-Path (Join-Path $LFRepo "..")).Path
$Blender = "C:\blender\blender.exe"
$Godot   = "C:\Godot\4.7\Godot_v4.7-stable_win64.exe"   # plain exe (not _console): LF captures output itself
$Stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$Run     = Join-Path $Factory ("_lf_smoke_" + $Stamp)
$WS      = Join-Path $Run "ws"
$Src     = Join-Path $Run "src"
New-Item -ItemType Directory -Path $Run, $Src, (Join-Path $Src "briefs") -Force | Out-Null
$Log     = Join-Path $Run "smoke.log"
Start-Transcript -Path (Join-Path $Run "transcript.log") | Out-Null

function W([string]$m) { Write-Host $m; Add-Content -Path $Log -Value $m }
function Section([string]$n) { W ""; W ("=" * 62); W ("== " + $n); W ("=" * 62) }
function LF { param([Parameter(ValueFromRemainingArguments=$true)]$rest)
    & python (Join-Path $LFRepo "apps\cli\main.py") -C $WS @rest 2>&1 | Tee-Object -FilePath (Join-Path $Run "cli.log") -Append
    W ("  -> exit " + $LASTEXITCODE)
    return $LASTEXITCODE
}

Section "0. PRE-FLIGHT"
W ("LF repo : " + $LFRepo)
W ("factory : " + $Factory)
foreach ($p in @($Blender, $Godot)) { if (Test-Path $p) { W ("ok      : " + $p) } else { W ("MISSING : " + $p); Stop-Transcript | Out-Null; exit 1 } }

# LF's tool keys vs factory folder names: only laser_tag differs (folder
# 'lasertag'). Real-tool smoke wants one dir keyed by LF names -> junctions.
Section "1. TOOL JUNCTIONS (_lf_tools, LF-keyed names)"
$ToolsDir = Join-Path $Factory "_lf_tools"
if (Test-Path $ToolsDir) { Remove-Item $ToolsDir -Recurse -Force }
New-Item -ItemType Directory -Path $ToolsDir -Force | Out-Null
$map = @{ "deli_counter"="deli_counter"; "dispatch"="dispatch"; "laser_tag"="lasertag";
          "lot"="lot"; "lux"="lux"; "patina"="patina"; "pixelcoat"="pixelcoat"; "zoo"="zoo" }
foreach ($k in $map.Keys) {
    $target = Join-Path $Factory $map[$k]
    if (-not (Test-Path $target)) { W ("MISSING tool repo: " + $target); Stop-Transcript | Out-Null; exit 1 }
    New-Item -ItemType Junction -Path (Join-Path $ToolsDir $k) -Target $target | Out-Null
    W ("  " + $k + " -> " + $map[$k])
}

Section "2. INSTALL (editable, dev extras)"
Push-Location $LFRepo
python -m pip install -e ".[dev]" -q 2>&1 | Select-Object -Last 3 | ForEach-Object { W ("  " + $_) }
W ("  -> exit " + $LASTEXITCODE)

Section "3. FAST SUITE (stubs)"
python -m pytest tests --ignore=tests\real_tools -q 2>&1 | Select-Object -Last 3 | ForEach-Object { W ("  " + $_) }
$fast = $LASTEXITCODE; W ("  -> exit " + $fast)

Section "4. REAL-TOOL SMOKE (LF_TOOLS_DIR)"
$env:LF_TOOLS_DIR = $ToolsDir
python -m pytest tests\real_tools -q 2>&1 | Select-Object -Last 3 | ForEach-Object { W ("  " + $_) }
$smoke = $LASTEXITCODE; W ("  -> exit " + $smoke)
Pop-Location
if ($fast -ne 0 -or $smoke -ne 0) { W "STOP: suites red - fix before the pipeline run."; Stop-Transcript | Out-Null; exit 1 }

Section "5. WORKSPACE INIT + tools.local.json"
& python (Join-Path $LFRepo "apps\cli\main.py") init $WS --name "Smoke" --project-id smoke 2>&1 | ForEach-Object { W ("  " + $_) }
$repos = @{}
foreach ($k in $map.Keys) { $repos[$k] = (Join-Path $Factory $map[$k]) }
@{ python_executable = (Get-Command python).Source
   blender_executable = $Blender
   godot_executable   = $Godot
   repositories       = $repos } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $WS "tools.local.json")
W "  tools.local.json written"

Section "6. DOCTOR + CONTRACTS + MANIFEST"
LF doctor | Out-Null
LF verify-contracts | Out-Null
LF verify-manifest --factory $Factory | Out-Null

Section "7. BATCH + BRIEF"
@{ schema="level_factory.batch.v0.1"; batch_id="smoke_b1"; name="Smoke"
   seed_base=1997; theme_family="delco_1997"; missions=@("m1") } | ConvertTo-Json | Set-Content (Join-Path $Src "batch.json")
@{ schema="level_factory.mission_brief.v0.1"; mission_id="m1"; display_name="Smoke M1"
   archetype="urban_bank"; building_count=1; site_shape="street_block"
   route_shape="push_then_backtrack"; candidate_count=3
   target_minutes=@(25,35); theme="delco_1997"; time_of_day="afternoon" } | ConvertTo-Json | Set-Content (Join-Path $Src "briefs\m1.json")
LF batch create (Join-Path $Src "batch.json") | Out-Null

Section "8. FUNCTIONAL LOCK (DC x3 real Blender -> Lot -> LaserTag)"
LF run m1 --target functional-lock | Out-Null
LF approve m1 brief_approved | Out-Null
LF approve m1 candidate_selected --candidate m1.candidate.seed_1997 | Out-Null
LF approve m1 functional_shell_locked | Out-Null

Section "9. PRESENTATION (incl. zoo_fixtures_build + lux_fixture_gate - THE unverified leg)"
LF run m1 --art | Out-Null

Section "10. FIXTURE PIPELINE EVIDENCE"
$fxIdx = Get-ChildItem (Join-Path $WS ".level_factory\jobs\m1.zoo_fixtures_build") -Recurse -Filter "*_fixtures.built.json" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($fxIdx) {
    $j = Get-Content $fxIdx.FullName -Raw | ConvertFrom-Json
    W ("  zoo fixtures : built=" + $j.fixtures_built + "  emitter_markers=" + $j.emitter_markers + "  (tool " + $j.tool_version + ")")
} else { W "  zoo fixtures : NO INDEX FOUND - stage failed, see status below" }
$gate = Get-ChildItem (Join-Path $WS ".level_factory\jobs\m1.lux_fixture_gate") -Recurse -Filter "fixture_gate.report.json" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($gate) {
    W "  gate report  :"
    Get-Content $gate.FullName | ForEach-Object { W ("    " + $_) }
    Copy-Item $gate.FullName -Destination $Run
} else { W "  gate report  : NOT FOUND - stage failed, see status below" }

Section "11. APPROVALS + EXPORT + PORTABILITY"
LF approve m1 presentation_approved | Out-Null
LF approve m1 regression_approved | Out-Null
LF export m1 --mode portable-godot --format folder | Out-Null
LF portability-test m1 | Out-Null

Section "12. STATUS + VALIDATE"
LF status m1 | Out-Null
LF validate m1 | Out-Null

W ""
W ("Artifacts + logs: " + $Run)
W "Zip this folder and upload it back to Claude for the verdict."
Stop-Transcript | Out-Null
