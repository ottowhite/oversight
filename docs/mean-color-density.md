# Plan: per-pixel mean-color density field

## Motivation

The current atlas renders a "glow" layer with additive blending. In dense
regions where many papers from different conferences overlap, the per-fragment
sum of RGB values clips to white — so the venue-color information is **lost
exactly where it would be most informative** (the densest clusters of the
corpus).

We want:

- **Brightness** to encode density (matches the matplotlib hexbin reference)
- **Color** to encode the *mean* of contributing papers' source colors — so
  a NeurIPS-heavy cluster reads as bright orange, an ICLR-heavy cluster reads
  as bright teal, and a balanced ICLR+NeurIPS region reads as a true mix of
  the two colors rather than fuchsia-clipped-to-white.

These are **two independent signals** that current additive blending conflates
into one (and clips). To separate them we need to accumulate density and
weighted color separately in a float framebuffer, then divide in a second pass.

This is the standard approach used by `HeatmapLayer` in deck.gl itself — we
follow the same multi-pass GPU aggregation pattern, but with a different
tone-map fragment shader (mean-color instead of density→colorRamp).

## Architecture

Replace the current "glow" `ScatterplotLayer` with a new custom layer
**`DensityFieldLayer`**. The "core" `ScatterplotLayer` and the "highlights"
`ScatterplotLayer` stay unchanged. New layer order:

1. **`DensityFieldLayer`** — bottom. Multi-pass GPU aggregation, produces the
   density-driven topology with venue color preserved.
2. **`atlas-points-core`** ScatterplotLayer — middle. The crisp little
   star-cores per paper (unchanged).
3. **`highlights`** ScatterplotLayer — top. Yellow halos for search results
   (unchanged).

### `DensityFieldLayer` internals

Two GPU passes per frame:

**Pass 1: accumulate**

For each of N visible points, rasterize a quad in pixel-space (constant
on-screen radius). The fragment shader writes:

```
out = vec4(color.rgb * α * coverage, α * coverage)
```

with **additive blending** into a floating-point off-screen framebuffer.
After all dots, each pixel holds:

- `rgb` channels: `Σ(color_i × α_i × coverage_i)`
- `a` channel: `Σ(α_i × coverage_i)`

Where `coverage` is the smoothstep edge of the disc.

**Pass 2: tone-map**

A fullscreen quad pass. Fragment shader reads the float framebuffer and
outputs to the screen:

```
mean = accum.rgb / max(accum.a, EPSILON)
brightness = log(1.0 + accum.a) / log(1.0 + brightnessCap)   // tunable curve
final = vec4(mean, min(brightness, 1.0))
```

With normal alpha blending. The result: mean color (bounded by convex hull of
inputs, NEVER saturates to white) modulated by a tunable log-based brightness
envelope.

### Why this stops saturation

`mean = sum_rgb / sum_alpha` is the weighted mean of input colors. It's
mathematically bounded by the convex hull of contributing colors — pure
ICLR (teal) stays teal at max brightness instead of clipping to white;
mixed regions show actual color blends.

Brightness comes from `sum_alpha` mapped through `log(1 + x)` and clamped, so
density can go arbitrarily high without color clipping.

## Reference implementation

deck.gl's own `HeatmapLayer` is the canonical example of this pattern in the
codebase:

- Source: `node_modules/@deck.gl/aggregation-layers/dist/heatmap-layer/`
- It uses a float framebuffer, an accumulator pass, and a colorize pass
- It maps density → user-supplied `colorRange` gradient (a different tone-map
  than ours)
- The framebuffer plumbing, resize handling, and luma.gl model setup all
  translate directly. Study its `weights-pass-fragment.glsl` and
  `triangle-layer-fragment.glsl` for shader structure.

**Do not derive this from scratch.** Read HeatmapLayer first; lift its
framebuffer/multi-pass scaffolding; then plug in our two shaders.

## File layout

```
frontend/components/DeckAtlasCanvas.tsx        # integrate new layer + new sliders
frontend/components/DensityFieldLayer.ts       # new — custom layer class
frontend/components/density-field-shaders.ts   # new — vs/fs source strings
```

The shaders can live inline in `DensityFieldLayer.ts` if that's simpler;
splitting is a preference, not a requirement.

## `DensityFieldLayer` API

```ts
type DensityFieldLayerProps<D> = {
  id: string;
  data: D[];
  getPosition: (d: D) => [number, number];
  getFillColor: AccessorFunction<D, [number, number, number, number]>;
  // Per-dot footprint in screen pixels. Constant so density is a screen-space
  // signal: dense world clusters → many overlapping screen-radii → bright pixel.
  radiusPixels: number;
  // Per-dot weight in the density accumulator. Lower = log curve compresses
  // density less aggressively; higher = clusters saturate brightness sooner.
  weight: number;
  // log(1 + brightnessCap) maps to full brightness in the tone map. Cap=1
  // means a single dot at peak coverage is full brightness; cap=20 means
  // ~20 overlapping dots reach full brightness.
  brightnessCap: number;
  // Standard deck.gl Layer props
  coordinateSystem?: number;
  updateTriggers?: Record<string, unknown>;
};
```

`getFillColor` follows deck.gl's normal accessor pattern and must be
referentially stable to avoid 524k-color re-uploads on every render
(see the existing load-bearing comment in `DeckAtlasCanvas.tsx`).

## Tuning panel changes

Bump `TUNING_STORAGE_KEY` from `"atlas:tuning:v2"` to `"atlas:tuning:v3"`.

New Tuning shape:

```ts
type Tuning = {
  coreRadius: number;          // unchanged
  coreMinPixels: number;       // unchanged
  coreMaxPixels: number;       // unchanged
  densityRadiusPixels: number; // replaces glowRadiusPixels
  densityWeight: number;       // replaces glowAlpha — was 0.02, default ~0.1
  brightnessCap: number;       // new — default ~5.0
};

const TUNING_DEFAULTS: Tuning = {
  coreRadius: 0.003,
  coreMinPixels: 0,
  coreMaxPixels: 12,
  densityRadiusPixels: 6,
  densityWeight: 0.1,
  brightnessCap: 5,
};
```

Update the panel's sliders:

- **Core (the star)**: Radius (world), Min pixels, Max pixels — unchanged
- **Density field** (new section name): Radius (px), Weight, Brightness cap

Slider ranges:

- `densityRadiusPixels`: 2 – 32, step 0.5
- `densityWeight`: 0.01 – 1.0, step 0.01
- `brightnessCap`: 1 – 50, step 0.5

## Integration with existing systems

- **Picking**: `DensityFieldLayer` is `pickable: false`. The cores layer
  underneath (which already exists) handles all picks.
- **Filtering**: same `visiblePoints` array feeds both the density layer and
  the cores. Legend toggles continue to work via data filtering.
- **Streaming**: layer's `data` prop binds to the same growing array. As
  batches arrive, deck.gl re-uploads the per-vertex attributes. The density
  field will progressively fill in over the stream's lifetime.
- **Resize**: the float framebuffer in `DensityFieldLayer` must track the
  viewport. Handle in `shouldUpdateState` / `updateState` — resize the FBO
  when `viewport.width × pixelRatio` or `height` change.

## Implementation steps

1. **Read `HeatmapLayer` source** in `node_modules/@deck.gl/aggregation-layers/`
   to internalize the multi-pass scaffolding pattern. Don't skip this.
2. **Create `frontend/components/DensityFieldLayer.ts`**:
   - Subclass `Layer<DensityFieldLayerProps>`
   - In `initializeState`: create the float FBO, the accumulator `Model`, the
     tone-map `Model`. Vertex layout matches one `[x, y]` per dot + one
     `[r, g, b, a]` per dot, instanced quads (4 verts per dot).
   - In `updateState`: when data changes, re-upload attribute buffers. When
     viewport changes, resize the FBO.
   - In `draw`: pass 1 → FBO with additive blend; pass 2 → screen with
     normal blend.
   - Pass through `radiusPixels`, `weight`, `brightnessCap` as uniforms.
3. **Author the two GLSL shaders** (sketches above):
   - Accumulator: per-fragment compute `coverage` from `smoothstep`,
     output `vec4(color * α * coverage, α * coverage)`.
   - Tone-map: read FBO, compute `mean = rgb / max(a, ε)`, compute
     `brightness = log(1 + a) / log(1 + cap)`, output `vec4(mean, min(b, 1))`.
4. **Wire into `DeckAtlasCanvas.tsx`**:
   - Import `DensityFieldLayer`
   - Remove the existing glow ScatterplotLayer
   - Add a `DensityFieldLayer` in its place (bottom of the layer stack)
   - Drop the old glow tuning fields (`glowRadiusPixels`, `glowAlpha`)
   - Add the new density tuning fields (`densityRadiusPixels`, `densityWeight`,
     `brightnessCap`)
   - Update the panel's slider rendering accordingly
   - Bump `TUNING_STORAGE_KEY` to `"atlas:tuning:v3"`
5. **Verify** (see below).

## Verification (REQUIRED before declaring done)

This work is GPU rendering, so it MUST be visually verified — type-check passing
is insufficient.

1. `npx tsc --noEmit` from `frontend/` should print no errors.
2. Frontend dev server is already running at `http://localhost:3002` (Docker
   container with hot reload). After file edits, the container picks up changes
   automatically. If the container needs a restart, run
   `sudo -n docker restart oversight-oversight-atlas-oversight-frontend-1`.
3. Use the **Playwright MCP** (`browser_navigate`, `browser_take_screenshot`,
   `browser_wait_for`, `browser_click`, `browser_evaluate`) to:
   1. Navigate to `http://localhost:3002/atlas`
   2. Wait 12 seconds for the stream to land and the density layer to render
   3. Take a screenshot (e.g. `atlas-density-default.png`)
   4. **Read the screenshot back via the Read tool** to confirm visually that:
      - The corpus topology shape is visible (the "land mass" outline)
      - Color is preserved in dense regions (NOT clipped to pure white) — you
        should see venue-colored regions (teal, orange, etc.) where the matplotlib
        reference shows colored speckles
      - The bottom-left **Tune** button is present
      - Cores are visible as crisp small dots overlaying the density field
   5. Click the Tune button and screenshot again — confirm the new sliders
      (`Radius (px)`, `Weight`, `Brightness cap`) are visible in the "Density
      field" section
   6. Move one of the new sliders via `browser_evaluate` (dispatch input
      events on the range input) and screenshot — confirm the visual changes
      respond live
4. **Do NOT mark the task complete until those screenshots verify the layer
   is actually rendering correctly.** A black canvas, an all-white canvas,
   or unchanged additive output are all "broken" — you have to read the PNG
   bytes back and confirm the topology + color separation are visible.
5. If something doesn't work, debug via:
   - `sudo -n docker logs --tail 100 oversight-oversight-atlas-oversight-frontend-1`
   - `mcp__playwright__browser_console_messages` for WebGL errors
   - Report what failed, what you tried, and where you got stuck rather than
     declaring done.

## Risks and gotchas

- **luma.gl version**: deck.gl 9.3 ships luma.gl 9.x. The `Model`,
  `Framebuffer`, `Texture` APIs differ from 8.x. Reference current
  HeatmapLayer source for the right idioms — older online examples likely
  predate luma.gl 9.
- **`EXT_color_buffer_float` capability**: required for full-float FBO
  attachments in WebGL2. >99% of desktop browsers support it. `rgba16float`
  (half-float) is a safe fallback if checks fail.
- **DevicePixelRatio**: the FBO must size at `width * dpr × height * dpr` to
  match the canvas's backing buffer, or the tone-map sampling will be blurry
  / misaligned.
- **Resize debouncing**: rebuilding the FBO on every ResizeObserver tick is
  fine for the user but can be costly. Reasonable to debounce, but for v1 we
  can ignore.
- **First-paint flicker**: when `points` is empty (stream not yet started),
  the accumulator outputs all zeros and the tone-map's `mean = 0 / ε` becomes
  near-black. Acceptable — it's the same as the current loading state.
- **getFillColor stability**: same load-bearing concern as today. The
  accessor MUST be `useCallback`-stable across renders. The existing comment
  in `DeckAtlasCanvas.tsx` documents this; preserve it.

## Effort estimate

- Read HeatmapLayer source: 1 hour
- DensityFieldLayer skeleton + shaders: 1.5 hours
- First successful render: ~1 hour of WebGL debugging (uniform locations,
  FBO format, attribute layout, etc.)
- Panel integration + slider plumbing: 30 minutes
- Screenshot verification + tuning slider iteration: 30 minutes

Realistic total: **3–4 hours**.

## What this does NOT change

- The streaming NDJSON pipeline is untouched.
- The legend filter (`hiddenSources`) still works the same way — data
  filtering before the layer sees it.
- Picking still flows through the cores layer; density field is
  `pickable: false`.
- Highlights (yellow halos for search-selected papers) are unchanged.
- The control panel UX (button at bottom-left, popup above) stays identical;
  only the slider contents change.
