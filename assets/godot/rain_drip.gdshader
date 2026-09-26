shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, specular_schlick_ggx;

uniform sampler2D drops : source_color, filter_linear_mipmap, repeat_enable;
uniform float drip_speed : hint_range(0.0, 1.0) = 0.08;
uniform float drip_scale : hint_range(0.5, 16.0) = 4.0;
uniform float amount : hint_range(0.0, 1.0) = 0.9;

const float PROUD_M = 0.002;

varying vec3 world_n;

void vertex() {
	world_n = (MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz;
	VERTEX += NORMAL * PROUD_M;
}

void fragment() {
	vec4 drop = texture(drops, UV * drip_scale);

	// EACH DROP ON ITS OWN CLOCK. `fract(b - t)` decays from the drop's own
	// random value to zero and snaps back, which reads as a drop landing,
	// soaking in, and another landing after it. Multiplied by B again so a
	// texel with no drop stays at zero rather than pulsing the whole wall.
	float run = fract(drop.b - TIME * drip_speed) * drop.b;
	// the small drops do not move at all -- surface tension holds them.
	float wet = clamp(max(run, drop.a), 0.0, 1.0) * amount;

	// RAIN DOES NOT FALL ON A SOFFIT, and it does not run down one either.
	// A vertical face takes the most; a ceiling takes none.
	float up = dot(normalize(world_n), vec3(0.0, 1.0, 0.0));
	wet *= smoothstep(-0.35, 0.15, up);

	// Z is reconstructed, not stored: a drop's normal is near-vertical
	// almost everywhere and the error does not survive a normal map.
	NORMAL_MAP = vec3(drop.r, drop.g, 1.0);
	NORMAL_MAP_DEPTH = wet * 2.0;

	ALBEDO = vec3(0.0);
	ALPHA = wet * 0.30;
	ROUGHNESS = mix(0.55, 0.06, wet);
	SPECULAR = mix(0.5, 1.0, wet);
	METALLIC = 0.0;
}
