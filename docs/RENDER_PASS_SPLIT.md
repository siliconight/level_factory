# Roadmap: split Lux out of `--art` into a `--render` pass

**Raised 2026-08-05.** Not implemented; captured so it does not get lost.

## The problem

`--art` currently bundles four different things, and one of them is much
heavier and much more opinionated than the other three:

| stage | what it does | reversible? |
|---|---|---|
| Zoo | swaps DC's slots for themed modules at the same transform, adds props + dressing | yes, per-slot |
| Pixelcoat | skins surfaces | yes, per-material |
| Patina | cohesion pass over the skin | yes |
| **Lux** | **the runtime look — lights, exposure, post** | **bakes a look into the deliverable** |

Wanting themed geometry and materials does not imply wanting a locked-in
lighting and post treatment. Today you cannot have the first three without
the fourth, so every art pass ships a pile of render decisions the consumer
may not want and cannot easily undo.

## The proposal

Add `--render` as an independent flag, and take Lux out of `--art`:

```
run <mission>                       -> graybox               DC greybox + collision, assembled by Lot (+ Laser Tag nav QA)
run <mission> --art                 -> graybox + art         Zoo swaps + props/dressing, Pixelcoat, Patina
run <mission> --art --render        -> graybox + art + look  ... plus Lux
run <mission> --gameplay            -> graybox + gameplay    Dispatch objective/nav/spawn suggestions (advisory)
run <mission> --art --gameplay      -> full stack            art pass + Dispatch over the art scene
run <mission> --art --render --gameplay -> everything
```

Same principle the existing flags already follow: the layers are independent
and the model stays a shell the gameplay team fills. `--render` is simply the
layer that decides how it is *lit*, which is a separate decision from what it
is *made of*.

## Notes for whoever picks this up

- **`--render` without `--art` should be legal.** Lighting a greybox is a
  real thing to want — it is how you check readability before committing to
  materials.
- **`--target` aliases must keep working.** `presentation` currently means
  art+gameplay; it should become art+render+gameplay so existing callers get
  what they got before. `functional-lock` = graybox and
  `dispatch-handoff` = +gameplay are unaffected.
- **`lux_fixture_gate` is not Lux.** It gates fixture placement and is
  arguably part of the art layer (it validates that fixtures exist where the
  building says they should), whereas `lux_apply` is the look. Splitting the
  flag means deciding which side that gate falls on. Worth checking whether
  anything downstream of `--art` reads Lux output before assuming it can be
  skipped cleanly.
- **The composer fingerprint already handles this.** `presentation_compose`
  invalidates on its source set, so adding or removing a layer will not serve
  a stale compose.
