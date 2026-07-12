# Adapter SDK

A tool adapter isolates Level Factory from a tool's CLI and schema. Implement
`ToolAdapter` (or subclass `BaseAdapter`) with:

- `adapter_id`, `adapter_version`, `capabilities`
- `probe(installation) -> ToolProbe` — availability, version, commit, caps.
  Prefer `run_contract_probe([...])` to read a tool's machine-readable
  `contract` command (the Dispatch D12 pattern).
- `validate_configuration(job_spec, context) -> [problems]` — report, never fix.
- `fingerprint_inputs(job_spec, context) -> dict` — everything that changes the
  output (hash file *contents*, not paths).
- `plan_commands(job_spec, context) -> [PlannedCommand]` — argument arrays only.
- `collect_outputs(...)` and `normalize_validation(...)` — map tool findings to
  the shared severity/category model; mark HARD errors `blocking: True`.

The adapter version is part of every job fingerprint; bump it when command
syntax, output discovery, validation mapping, or fingerprint logic changes.
