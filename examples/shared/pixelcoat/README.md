# Shared Pixelcoat recipes

Batch-level surface packs. The `pixelcoat_build` stage compiles these recipes
into `pixelcoat-pack/1` packs (`<id>.pack.json` + albedo/normal/roughness
[+emissive/height]) that Zoo consumes via `--skins`. Packs are shared across all
missions in a batch, so the same brick/neon surfaces stay consistent.

Copy this tree to `<workspace>/shared/pixelcoat/recipes/` (the operator default).
