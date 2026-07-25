extends CharacterBody3D
## Self-contained first-person walk controller for previewing a Level Factory
## themed building. NO addons, NO project input actions (it polls keys directly),
## so it drops into the walk preview as-is. Includes basic STAIR-STEPPING so you
## can climb the greybox stairs instead of getting stuck on the first riser.
##
## Controls: WASD move, mouse look, Space jump, Shift sprint, Esc toggle mouse.

@export var speed: float = 4.5
@export var sprint_speed: float = 8.0
@export var jump_velocity: float = 5.0
@export var mouse_sensitivity: float = 0.0025
@export var max_step_height: float = 0.5  # auto-climb steps up to this tall
@export var climb_speed: float = 6.0      # ladder climb rate (m/s at optimum)

@onready var _camera: Camera3D = $Camera3D

# The ladder currently latched (an Area3D in group "ladder_area3d" -- the
# climb contract DC bakes into every composed package, see DC's
# docs/LADDER_CLIMB_CONTRACT.md). Null when not climbing.
var _ladder: Area3D = null


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	# Snap to stairs on the way DOWN so we don't launch off each step edge.
	floor_snap_length = maxf(floor_snap_length, max_step_height)
	floor_max_angle = deg_to_rad(60)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		_camera.rotate_x(-event.relative.y * mouse_sensitivity)
		_camera.rotation.x = clampf(_camera.rotation.x, -1.4, 1.4)
	elif event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = (
			Input.MOUSE_MODE_VISIBLE
			if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
			else Input.MOUSE_MODE_CAPTURED
		)


func _physics_process(delta: float) -> void:
	# Ladders replace ALL other movement while latched (no gravity, no
	# walk/air code) -- like water or noclip, it's its own movement mode.
	if _handle_ladder_physics(delta):
		return
	if not is_on_floor():
		velocity += get_gravity() * delta
	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = jump_velocity

	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W):
		dir -= transform.basis.z
	if Input.is_key_pressed(KEY_S):
		dir += transform.basis.z
	if Input.is_key_pressed(KEY_A):
		dir -= transform.basis.x
	if Input.is_key_pressed(KEY_D):
		dir += transform.basis.x
	dir.y = 0.0
	dir = dir.normalized()

	var spd := sprint_speed if Input.is_key_pressed(KEY_SHIFT) else speed
	velocity.x = dir.x * spd
	velocity.z = dir.z * spd

	var grounded := is_on_floor()
	var pos_before := global_position
	move_and_slide()
	# If we were on the ground and a low step stopped us, lift over it — but only
	# by the movement this frame was DENIED, never a fixed jump (a fixed forward
	# hop stacked on the normal move each frame is what made the player rocket
	# ~4x near a stair). A real wall still blocks.
	if grounded and velocity.y <= 0.1:
		_step_up(pos_before, delta)


## Source-style ladder movement (CS:S-like), against the climb contract DC
## bakes into composed packages: an Area3D in group "ladder_area3d" whose
## +Z axis points at the APPROACH side, with a TopOfLadder child at the
## step-off height. Everything is judged RELATIVE TO THE LADDER via its
## transform inverse -- the player's wish direction (keys, made relative to
## the camera) is mapped into ladder space, and:
##   climb  = (wish_up + wish_into_ladder) / sqrt(2)
## so looking 45 degrees up the ladder while pressing W is the fastest climb
## (the Source optimum), looking level away climbs down, looking down feeds
## descent, and strafing INTO the ladder stacks with forward for the classic
## ladder-boost. Strafe (wish.x) slides you sideways along the rungs.
## Space jumps you off the face; walking off the bottom or over the top
## releases cleanly; brushing past a ladder never latches unless you press
## toward it near its plane.
func _handle_ladder_physics(_delta: float) -> bool:
	var was: Area3D = _ladder
	if _ladder != null and not _ladder.overlaps_body(self):
		_ladder = null
	if _ladder == null:
		for l in get_tree().get_nodes_in_group("ladder_area3d"):
			if l is Area3D and l.overlaps_body(self):
				_ladder = l
				break
	if _ladder == null:
		return false

	var lt: Transform3D = _ladder.global_transform
	var linv: Transform3D = lt.affine_inverse()
	var rel_pos: Vector3 = linv * global_position

	var fwd: float = (1.0 if Input.is_key_pressed(KEY_W) else 0.0) \
			- (1.0 if Input.is_key_pressed(KEY_S) else 0.0)
	var side: float = (1.0 if Input.is_key_pressed(KEY_D) else 0.0) \
			- (1.0 if Input.is_key_pressed(KEY_A) else 0.0)
	var wish: Vector3 = linv.basis \
			* (_camera.global_transform.basis * Vector3(side, 0.0, -fwd))
	if wish.length() > 1.0:
		wish = wish.normalized()

	# -Z is INTO the ladder; up and into weigh equally (45-degree optimum).
	var climb: float = (wish.y - wish.z) / sqrt(2.0)
	var strafe: float = wish.x

	var top_y: float = float(_ladder.get_meta("climb_height", 3.0)) - 0.2
	var top_marker: Node3D = _ladder.get_node_or_null("TopOfLadder")
	if top_marker != null:
		top_y = top_marker.position.y

	if was == null:
		# First frame inside the volume: only latch on deliberately -- and
		# ONLY from the approach side (+Z). From behind, a ladder is just a
		# solid object: its own static collision applies and pressing
		# "toward" it must never pull the player through onto the climb
		# plane.
		if rel_pos.z < -0.05:
			_ladder = null
			return false
		if rel_pos.y > top_y:
			# Mounting from the top: let the player walk away over the edge.
			if wish.z > 0.3:
				_ladder = null
				return false
		elif -wish.z < 0.4 or absf(rel_pos.z) > 0.6:
			# From the side/air: must press INTO the ladder near its plane,
			# else walking past a ladder would glue you to it.
			_ladder = null
			return false

	# Bottom exit: on the floor near the base, still climbing down.
	if is_on_floor() and climb < 0.0 and rel_pos.y < 0.4:
		_ladder = null
		return false

	# Top exit: once the body has climbed high enough that its feet clear
	# the upper floor, pressing AWAY steps off onto it instead of reading
	# as climb-down. (Without this, +Z wish always means descend and the
	# ladder can never be exited at the top.)
	var climb_h: float = float(_ladder.get_meta("climb_height", 3.0))
	if rel_pos.y > climb_h + 0.85 and wish.z > 0.2:
		var lb: Basis = lt.basis
		_ladder = null
		velocity = lb * Vector3(strafe * climb_speed, 0.5, 2.5)
		move_and_slide()
		return true

	# Jump off the face.
	if Input.is_action_just_pressed("ui_accept"):
		velocity = lt.basis.z * jump_velocity * 1.5
		velocity.y = maxf(velocity.y, jump_velocity * 0.5)
		_ladder = null
		return false

	# Snap to the climb plane (a forearm off the face) and move ladder-space.
	rel_pos.z = 0.5
	global_position = lt * rel_pos
	velocity = lt.basis * Vector3(strafe * climb_speed, climb * climb_speed, 0.0)
	move_and_slide()
	return true


func _step_up(pos_before: Vector3, delta: float) -> void:
	if not is_on_wall():
		return
	var horiz := Vector3(velocity.x, 0.0, velocity.z)
	if horiz.length() < 0.05:
		return
	# Only complete the blocked REMAINDER of this frame's intended move, so total
	# horizontal displacement stays exactly one frame's worth (no speed boost).
	var wanted := horiz * delta
	var moved := global_position - pos_before
	moved.y = 0.0
	var remaining := wanted - moved
	remaining.y = 0.0
	if remaining.length() < 0.001:
		return  # we weren't actually blocked
	var raised := global_transform
	raised.origin += Vector3.UP * max_step_height
	# Lifted by a step height, is the remaining path clear? If still blocked it's
	# a real wall (or a step too tall) -> don't climb.
	if test_move(raised, remaining):
		return
	raised.origin += remaining
	# Settle down onto the step surface; only snap if there IS ground within
	# reach, so we never teleport out over a ledge.
	var landing := KinematicCollision3D.new()
	if test_move(raised, Vector3.DOWN * (max_step_height + 0.05), landing):
		global_position = raised.origin + landing.get_travel()
