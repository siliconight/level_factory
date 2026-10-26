# The Gabagool Factory authoring project

Open this folder in Godot 4.7 and the Factory panel appears in the right-hand dock. It finds the factory by walking
up from here (`docs/AUTHORING_LOOP.md` at the factory root says what the panel does and how far it has got).

`project.godot` is committed in the format the Godot editor writes, so opening and closing the project leaves the
repository unchanged. Its first lines are the editor's own header; this file carries what used to head it.

`tests/` holds the panel's headless tests:

    godot --headless --path <this folder> --script res://tests/<test>.gd
