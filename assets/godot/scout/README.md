# scout/ -- the screen a player scouts this level's buildings on

Shipped by Level Factory in every level package. The handheld it shows on is the game's own asset; this folder is
its **screen**: the level's buildings, listed, each turning as a 3D schematic with its floors lifted apart, the
score and the props worth knowing about lit -- in a backlit 1990s handheld's colours.

## The seam -- everything the gameplay layer calls

```gdscript
var scout := preload("res://scout/scout_window.gd").new()   # class LFScoutWindow
add_child(scout)

scout.open()                                   # build the screen and start drawing it
handheld_screen.texture = scout.get_screen_texture()       # show it on the game's handheld
# or, with no handheld yet: scout.open(true)   # shown centred over the game

scout.buildings()                              # the ids it lists, as buildings.json names them
scout.select("deli_a03")                       # show one
scout.turn(45.0)                               # degrees
scout.set_spread(0.0)                          # 0 floors stacked as built .. 1 lifted apart
scout.set_points("deli_a03", [                 # the gameplay layer's own points, instead of the model's
    {"label": "SCORE", "kind": "score", "at": Vector3(3.0, 3.6, 2.0), "storey": 1},
])
scout.close()                                  # stop drawing; costs nothing until opened again
scout.is_open()                                # whether it is drawing
```

Signals: `opened`, `closed`, `building_selected(id)`.

While open it reads its own input -- left/right the building, up/down the floors, a mouse drag turns it, cancel
closes it. Set `handle_input = false` to drive it from the game's own controls.

## What it reads

- `res://buildings.json` -- the level's buildings, where each stands, and its drawings (`package_root` to move it).
- `res://lot/<id>/drawings/scout.glb` -- each building's schematic: a mesh a storey, the storey's points of interest
  a mesh under it, `extras.points` naming each (score, safe, ATM, loot, camera). Kept as the file it is, loaded with
  `GLTFDocument` when the screen opens: no level imports it.

## What it costs

Nothing while closed -- no nodes, no drawing. Open: one 3D view of one building, a few draws a storey, and a 2D
screen of `screen_size` (960 x 640 by default).

## In a walk copy

The factory's walk copies call it on **F6** (debug builds only), as a stand-in for the gameplay layer -- the same
calls as above, nothing more.
