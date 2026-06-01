// GLSL sources for the DensityFieldLayer.
//
// Pass 1 (accumulator): an instanced quad per dot, rasterised in
// screen-space. The fragment shader emits
//
//   vec4(color.rgb * α * coverage,  α * coverage)
//
// where 'coverage' is the disc's anti-aliased smoothstep edge. With
// additive blending into a float framebuffer this gives, per pixel:
//
//   rgb = Σ color_i · α_i · coverage_i
//   a   = Σ           α_i · coverage_i
//
// Pass 2 (tone-map): a fullscreen quad reads the float FBO. The mean
// colour is 'rgb / max(a, ε)'; the brightness comes from a log curve
// on 'a' clamped to [0,1]. Output is blended normally over the page
// background. The mean stays inside the convex hull of contributing
// colours, so dense ICLR (teal) regions stay teal at full brightness
// instead of white-clipping.
//
// The accumulator shares the deck.gl 'project32' module so we can
// project world coords with the same camera as the rest of the stack.

// ---------------------------------------------------------------------------
// Pass 1 — accumulator
// ---------------------------------------------------------------------------

export const ACCUM_VS = /* glsl */ `\
#version 300 es
#define SHADER_NAME density-field-accum-vs

// Quad corner positions (-1..1) — one of these four per vertex, instanced.
in vec3 positions;

// Per-instance attributes. 'instancePositions' is in world / common space;
// 'instanceFillColors' is unorm8 RGBA so it arrives in 0..1.
in vec3 instancePositions;
in vec3 instancePositions64Low;
in vec4 instanceFillColors;

out vec2 unitPosition;
out vec4 vFillColor;

void main(void) {
  // Pad the quad by 1 px so the smoothstep antialiasing has room to fade.
  float radiusPx = density.radiusPixels;
  float edgePadding = (radiusPx + 1.0) / max(radiusPx, 1.0);

  unitPosition = edgePadding * positions.xy;
  vFillColor = instanceFillColors;

  // World → clipspace via project32, then offset by the quad corner
  // in pixels (constant on-screen radius, like ScatterplotLayer's
  // radiusUnits:'pixels').
  vec3 offset = edgePadding * positions * project_pixel_size(radiusPx);
  gl_Position = project_position_to_clipspace(
    instancePositions, instancePositions64Low, offset
  );
}
`;

export const ACCUM_FS = /* glsl */ `\
#version 300 es
#define SHADER_NAME density-field-accum-fs
precision highp float;

in vec2 unitPosition;
in vec4 vFillColor;

out vec4 fragColor;

void main(void) {
  // Disc with anti-aliased edge. unitPosition is in [-1-padding, 1+padding];
  // the actual disc spans [-1, 1]. smoothstep gives a soft falloff so dense
  // dots blend cleanly without aliasing artifacts.
  float r = length(unitPosition);
  float coverage = 1.0 - smoothstep(1.0 - density.softness, 1.0, r);
  if (coverage <= 0.0) discard;

  // Per-dot contribution to the density accumulator.
  float w = vFillColor.a * coverage * density.weight;
  fragColor = vec4(vFillColor.rgb * w, w);
}
`;

// ---------------------------------------------------------------------------
// Pass 2 — tone-map
// ---------------------------------------------------------------------------

// The tone-map runs as a fullscreen quad. The vertex shader just emits the
// raw clip-space coords from a static quad geometry — no projection needed.
export const TONEMAP_VS = /* glsl */ `\
#version 300 es
#define SHADER_NAME density-field-tonemap-vs

in vec2 positions;
out vec2 vTexCoord;

void main(void) {
  vTexCoord = positions * 0.5 + 0.5;
  gl_Position = vec4(positions, 0.0, 1.0);
}
`;

export const TONEMAP_FS = /* glsl */ `\
#version 300 es
#define SHADER_NAME density-field-tonemap-fs
precision highp float;

uniform sampler2D accumTexture;

in vec2 vTexCoord;
out vec4 fragColor;

void main(void) {
  vec4 accum = texture(accumTexture, vTexCoord);
  float a = accum.a;
  if (a <= 0.0) {
    fragColor = vec4(0.0);
    return;
  }
  // Mean colour, mathematically bounded by the convex hull of inputs.
  vec3 mean = accum.rgb / a;

  // Brightness via a log curve, normalised against the user-tunable cap.
  // log(1+x)/log(1+cap) maps cap → 1.0 and small x → ~x/log(1+cap).
  float brightness = log(1.0 + a) / log(1.0 + density.brightnessCap);
  brightness = clamp(brightness, 0.0, 1.0);

  fragColor = vec4(mean * brightness, brightness);
}
`;
