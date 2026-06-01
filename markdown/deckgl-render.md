# Plan: migrate atlas renderer from regl-scatterplot to deck.gl

## Motivation

`regl-scatterplot` got us to a working 524k-point atlas with pan, zoom,
hover, click-to-pin, source-coloured points, legend filter, semantic
search, and multi-select highlighting. But every feature beyond "circles
of one colour" has been a small fight with the lib's API surface, and the
state model fights back when we try to compose features. Concretely:

- **Point shape is hard-coded.** Circles or squares, set globally. No
  native per-point glyphs, no stars, no icons. We considered overlaying
  DOM stars; the math broke on `devicePixelRatio` and the alignment
  drift defeated the point. We settled for "yellow + 10× size" because
  that was the only knob the renderer exposed.
- **`pointColorActive` is silently ignored when `colorBy` is set.**
  Hours lost to a bug whose root cause was one branch in
  `regl-scatterplot.esm.js:6596`. We worked around it by encoding the
  highlight as a synthetic "highlight" colour category and recolouring
  the affected rows ourselves.
- **`pointSize` and `opacity` arrays are silently ignored when
  `sizeBy` / `opacityBy` aren't explicitly set.** Hours lost to a
  second instance of the same pattern: per-point arrays that look like
  they should work, but don't unless you also set the corresponding
  encoding flag. The defaults are `null`, the docs are ambiguous, and
  the lib doesn't warn.
- **`draw()` resets the filter.** Toggling a search highlight redraws,
  which clobbers the legend filter (hidden arxiv reappears). We patched
  by re-applying the filter from a ref after every draw.
- **`set({width, height})` re-fires on every container resize**, which
  is a real risk on a page whose sidebar grows when an abstract loads —
  and the resize also subtly clobbers state. We patched by re-applying
  the filter on resize too.
- **Concurrent `draw()` calls throw.** Selecting two papers in quick
  succession triggered "Ignoring draw call on the previous draw call
  has not yet finished." We added a `drawInflightRef` queue to
  serialise.
- **Bulk-only updates.** Every redraw uploads the whole point buffer.
  At 524k points that's ~100–300 ms per redraw, which forces us to
  batch state changes carefully to avoid stutter.

Each individual patch is small. The aggregate pattern is "we're using
the wrong renderer for what we want to express." A renderer where the
public API was designed around the kinds of composition we want
(per-point glyphs, multi-layer overlay, declarative state) would
replace those workarounds with a couple of layers and would let us add
new features (text labels, multi-channel selection, time-axis animation
during streaming load, lasso-select-into-search) instead of fighting
the existing ones.

[deck.gl](https://deck.gl) is the obvious target: WebGL2-based, MIT,
maintained by Uber Vis, scales to millions of points routinely (it's
what kepler.gl uses under the hood), and its layer model directly
matches what we already want to do.

## Why deck.gl specifically

The features we actually need, mapped to deck.gl primitives:

| Today | deck.gl |
|---|---|
| Cloud of coloured points by source | `ScatterplotLayer` |
| Hover → pointOver event + sidebar fetch | `pickable: true` + `onHover` callback |
| Click → pin to sidebar | `onClick` callback |
| Source colour palette | `getFillColor: (d) => palette[d.sourceIdx]` |
| Legend filter (hide arxiv etc.) | `getFilterValue` + `DataFilterExtension` |
| Search-highlight (currently colour swap + size bump) | **Separate `IconLayer`** with star sprite + glow icon over the selection |
| Pan / zoom | `OrthographicView` controller |
| Constant-size highlights on zoom-out | `sizeUnits: 'pixels'` per layer (independent of the cloud's `'common'` units) |
| ~~Yellow ring overlay positioning math~~ | Gone — deck.gl picks per-layer, projection-aware |
| ~~Concurrent draw queue~~ | Gone — deck.gl re-renders on prop change without intermediate state |

Plus features we'd unlock with one extra line each:

- **Text labels for selected papers** — `TextLayer` over the same
  coordinates. Constant-size by default.
- **Density heatmap that reads as topology** — `HeatmapLayer` (KDE) or
  `HexagonLayer` (hexbin) renders the cloud as a continuous density
  field, not 524k discrete circles. The matplotlib version of the
  same data is *strikingly* more legible: arxiv papers go into a
  log-scaled hexbin so dense clusters become dark "land masses" and
  sparse regions fade to white, producing an almost-3D topographic
  look that lets you see the shape of the corpus at a glance. The
  WebGL scatter loses all of that because every point is a discrete
  circle of fixed size — overlapping circles flatten to one tone, no
  gradient survives. With deck.gl we'd layer a `HexagonLayer` of the
  arxiv mass underneath a `ScatterplotLayer` of conference papers, in
  one compose call. Approximate matplotlib parity in the browser.
- **Lasso selection** → search list — there's a `NebulaLayer` (or we
  draw the polygon ourselves and test with `polygon-clipping`); either
  way it composes cleanly with the existing layers.
- **Time-based fade-in during streaming load** — `transitions` prop on
  the layer; just pass `transitions: { getPosition: 600 }` and points
  animate to their final coordinates as they arrive.

We don't have to ship any of those in v1, but the migration unblocks them.

## Trade-offs

What deck.gl is **not** strictly better at:

- **Bundle size.** `regl-scatterplot` is ~150 KB minified. `@deck.gl/core` + `@deck.gl/layers` + `@deck.gl/extensions` is ~500 KB minified, ~150 KB gzipped. Acceptable for a desktop research tool; we'd want to confirm.
- **Performance at our exact scale.** Both render 500k points fine.
  deck.gl's draw call cost is higher per layer (more layers = more
  overhead), so a single-layer "boring scatter" is marginally slower
  than `regl-scatterplot`. We'd want to verify pan/zoom stays at ≥30
  fps on the 524k corpus with a representative GPU.
- **First-init cost.** deck.gl's layer state machine has a slightly
  higher mount time (~50–150 ms vs ~30 ms). Imperceptible in our
  context.
- **API surface.** deck.gl is bigger and there's more to learn. The
  upside is that the bigger surface is mostly *useful* — every knob
  corresponds to something we either already do or would plausibly want
  to do.

What I'd specifically want to validate before committing:

1. **`DataFilterExtension`** with a 524k-point dataset toggling a flag
   for the largest category (arxiv ≈ 80% of points). Today's
   `regl-scatterplot.filter()` does this in ~350 ms; we want deck.gl
   to be in the same ballpark or better.
2. **`IconLayer` for highlights** rendered over a `ScatterplotLayer`
   with hover/click going through to the correct layer. Need to confirm
   that picking returns the cloud point (so click pins the underlying
   paper) and not the icon (which is just decoration).
3. **OrthographicView pan/zoom** feels at parity with regl-scatterplot's
   built-in interaction (which is pretty good). I expect parity but
   want a side-by-side feel-check before committing.

## Architecture

Replace `frontend/pages/atlas.tsx`'s `regl-scatterplot` block with a
`<DeckGL>` component composing two `ScatterplotLayer`s plus one
`IconLayer`:

```
<DeckGL views={[new OrthographicView()]}
        initialViewState={...}  // computed from bbox like today
        controller={true}
        layers={[
          new ScatterplotLayer({
            id: 'cloud',
            data: points,
            getPosition: (d) => [d.x, d.y],
            getFillColor: (d) => palette[d.sourceIdx],
            getRadius: 3,
            radiusUnits: 'common',     // zooms with the view (matches today)
            radiusMinPixels: 1,         // never disappears at extreme zoom-out
            opacity: 0.55,
            pickable: true,
            extensions: [new DataFilterExtension({ filterSize: 1 })],
            getFilterValue: (d) => visibleSourceFlags[d.sourceIdx],
            filterRange: [1, 1],        // show rows where the flag is 1
            onHover: handleHover,
            onClick: handleClick,
          }),
          new IconLayer({
            id: 'highlights',
            data: selectedPoints,       // small array, recomputed from selectedIds
            iconAtlas: '/icons/star.png',
            iconMapping: { star: { x: 0, y: 0, width: 64, height: 64, anchorX: 32, anchorY: 32 } },
            getIcon: () => 'star',
            getPosition: (d) => [d.x, d.y],
            getColor: [255, 216, 74, 255],
            getSize: 28,
            sizeUnits: 'pixels',        // constant on zoom-out
            sizeMinPixels: 12,
            sizeMaxPixels: 48,
            pickable: false,            // hover/click reach the cloud underneath
          }),
        ]} />
```

Two-layer composition is the whole story. Everything that currently
lives in our `normalizedHighlighted` memo + `pointSize`/`opacity` arrays
+ `colorBy: 'valueA'` encoding + DOM overlay attempts is replaced by
"cloud layer + highlights layer."

### State that goes away

Concretely, the following can be deleted from `atlas.tsx` after
migration:

- `scatterRef`, `drawInflightRef` — no imperative renderer handle.
- `normalizePoints` — `OrthographicView` handles its own world-to-screen
  via `initialViewState`. We pass raw `(x, y)` and set
  `initialViewState.zoom` from the bbox so the cloud fits the viewport.
- `categoryByIndex`, `highlightCategory`, `normalizedHighlighted` —
  colour is a callback (`getFillColor`), highlight is a separate layer.
- `sourceIndices` (the precompute) — `DataFilterExtension` handles
  per-row filtering on the GPU; we just toggle a flag array.
- The ResizeObserver imperative width/height calls — deck.gl handles
  resize via its `_animate` / `_pickable` lifecycle. We pass `width`
  and `height` props (or use the `<DeckGL>` "fill parent" mode).
- The `view` event subscriber — there isn't one needed; selection
  positions are computed by the IconLayer via `getPosition`, projected
  by the same view as the cloud.
- The `drawInflightRef` serialisation queue — deck.gl's render is
  declarative; you change props, it diffs and re-renders. No imperative
  draws to serialise.

That's roughly **350–400 lines of atlas.tsx** that disappear or become
much simpler.

### State that stays

- `points`, `paperCache`, `sidebarPaperId`, `pinnedPaperId`,
  `hoverPaperId` — purely React state.
- `searchInput`, `searchResults`, `searchLoading`, `selectedIds` — same.
- `hiddenSources` — same.
- Sidebar component — unaffected; we're only swapping the canvas.
- The `/api/atlas` endpoint — unaffected. (Pairs well with the
  streaming plan in `docs/streaming-points.md` — both can land
  independently, but together they cut perceived load from ~9 s to
  ~500 ms.)

### Hover, pick, and click

deck.gl picks via a separate "pickable" framebuffer that the
ScatterplotLayer auto-manages. `onHover` and `onClick` get an `info`
object with `info.object` (the source data row) and `info.index`. So:

```ts
const handleHover = useCallback((info: PickingInfo) => {
  if (info.object) {
    setHoverPaperId(info.object.paper_id);
    void fetchPaperDetail(info.object.paper_id);
  } else {
    setHoverPaperId(null);
  }
}, [fetchPaperDetail]);

const handleClick = useCallback((info: PickingInfo) => {
  if (info.object) setPinnedPaperId(info.object.paper_id);
}, []);
```

This replaces today's `onOver` / `onSelect` regl subscribers with
prop-driven callbacks. Slightly more idiomatic-React.

### Hover tooltip

We currently render a tooltip via the AtlasSidebar's title row. With
deck.gl we can keep doing that — `info` already carries the hovered
row, and the sidebar render is unaffected. Optionally use `<DeckGL>`'s
built-in `getTooltip` for a small floating cursor tooltip; we don't
need it for v1.

### Legend filter

`DataFilterExtension` with `filterSize: 1` and a per-row scalar (0 or
1) is the standard pattern. We precompute a `visibleSourceFlags: Map<sourceIdx, 0|1>`
from `hiddenSources` and have `getFilterValue` look it up per row.
That's a closure capture; deck.gl re-uploads when the accessor
identity changes, so we wrap in `useCallback` keyed on `hiddenSources`.

The 524k flag array fits in 4 MB on the GPU. Toggle latency should be
"upload the flag buffer + diff," which is dramatically faster than
today's "rebuild visibleIndices in JS + call regl.filter."

### Highlights via IconLayer

The highlights `data` array is `selectedIndices.map(i => points[i])` —
small (usually <20 entries), so re-uploading on every selection toggle
is free. The icon atlas is a single PNG (a yellow star with a soft
glow, ~64×64 px, served from `/public/icons/star.png`). `sizeUnits:
'pixels'` keeps the star at a constant screen size as the user zooms
out, which is exactly what we struggled to express with regl-scatterplot
and `pointScaleMode`.

`pickable: false` on the IconLayer means hover/click pass through to
the cloud underneath — so clicking a highlight still pins the
underlying paper.

## Migration plan

Three phases. Each phase is independently mergeable; nothing is
committed against `main` until the whole thing works in a feature
branch.

### Phase 0 — Spike on a branch (1–2 hours)

Branch off `paper-atlas` to a new branch `paper-atlas-deckgl`. Add
`@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/extensions`, and
`@deck.gl/react` to `frontend/package.json`. Stand up a minimal
`<DeckGL>` rendering the 524k-point cloud with default colour, no
filtering, no highlights, no search. Goal: confirm pan/zoom feels
right and fps ≥ 30 on the dev box. Throw it away after.

### Phase 1 — Cloud layer at parity (1 day)

Replace the `regl-scatterplot` block in `atlas.tsx` with a single
`ScatterplotLayer`. Wire:

- `getPosition` from `(x, y)`
- `getFillColor` from the source palette (port `buildSourceColorIndex`
  unchanged — we already need the source→colour map for the legend)
- `radiusUnits: 'common'`, `radiusMinPixels: 1`, `radiusMaxPixels: 12`
  to match the visual feel today
- `opacity: 0.55`
- `pickable: true` + `onHover`/`onClick` from the existing handlers
- `DataFilterExtension` + `getFilterValue` for the legend filter

Sidebar, search, pin behaviour all keep working — they don't depend
on the renderer at all. Delete `normalizePoints`, `categoryByIndex`,
`normalizedHighlighted`, `sourceIndices`, `drawInflightRef`,
`visibleIndicesRef`, `hiddenSourcesRef`, the ResizeObserver block,
and the `scatter.draw / filter / select` effect entries.

Visual diff with the current page should be very small at this stage.

### Phase 2 — Highlights via IconLayer (half a day)

Add the `IconLayer` for selected papers. Author the star sprite
(`frontend/public/icons/star.png` — a 64×64 yellow star with a soft
amber halo; can be generated with a tiny SVG conversion or by hand).

Wire `data: selectedPoints` (= `Array.from(selectedIds).map(...)`
memoized), `getColor: [255, 216, 74, 255]`, `sizeUnits: 'pixels'`,
`sizeMinPixels: 18`, `sizeMaxPixels: 32`. Set `pickable: false`.

Delete every workaround that lived in the regl-scatterplot path:
the colour-category-swap encoding, the per-category `pointSize` /
`opacity` arrays with their `sizeBy` / `opacityBy` flags, the
`drawInflightRef` queue, and the "re-apply filter after draw"
patches in the ResizeObserver and the selection effect.

### Phase 3 — Tidy and verify (half a day)

- Replay the existing manual verification through CDP: load atlas,
  hide arxiv (default), search "garbage collection," check three
  results, confirm yellow stars at the right places, pan + zoom +
  hover + click + pin all work.
- Side-by-side fps measurement vs the regl-scatterplot version.
  Target: at least parity at the 524k full corpus during a pan
  drag.
- Update `docs/similarity-graph-plan.md` if anything cross-cuts (it
  shouldn't — graph view uses a different lib entirely).
- Delete `regl-scatterplot`, `regl`, `pub-sub-es` from
  `frontend/package.json` once nothing imports them.
- Rebase the branch and merge.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Bundle size jumps ~350 KB minified | Confirm acceptable for a research tool. If not, code-split — `<DeckGL>` and layers can be lazy-loaded the same way `regl-scatterplot` is today. |
| Pan/zoom feel regresses | Validate in Phase 0 before committing. deck.gl's controller is tunable (drag/scroll responsiveness, inertia). |
| `DataFilterExtension` slower than expected | Profile in Phase 1. Worst case: precompute per-source point arrays (like today's `sourceIndices`) and rebuild the layer's `data` prop on toggle — same complexity as today, no extension needed. |
| Picking returns icon, not underlying cloud point | Set `pickable: false` on `IconLayer` (already in the plan). If we need icon-pickable for some future hover-the-star UX, layer the IconLayer *below* an invisible matching ScatterplotLayer for hit-testing. |
| `IconLayer` requires a static atlas; no per-icon dynamic colour | Render the star as white in the atlas and use `getColor` to tint. Standard pattern. |
| Streaming-load animation breaks | deck.gl re-renders on `data` prop change automatically — incremental data binding works out of the box. Migrate the streaming work (see `docs/streaming-points.md`) on top of the deck.gl branch rather than the regl-scatterplot one. |

## Estimated total effort

~2.5 engineer-days end-to-end, including the spike. Most of the work
is *deleting* code rather than adding it — the regl-scatterplot path
has accreted enough patches that the deck.gl version is a smaller
component than the current one even before counting features we'd
add on top.

## Open questions / next-session work

- **Streaming + deck.gl interaction.** Worth thinking about whether
  to land the streaming change before, after, or merged with this
  migration. Doing streaming first means we migrate twice as much
  code; doing this first means streaming inherits a simpler renderer
  but pays the regl path's load cost until both ship. Likely best:
  streaming first (backend-only change is independently valuable), then
  this.
- **Mobile / touch interaction.** deck.gl supports pinch-zoom natively
  on `OrthographicView`. Worth a quick check on a phone after Phase 1
  to confirm.
- **HiDPI display scaling.** deck.gl handles `devicePixelRatio`
  internally — we don't have to. One of the latent bugs the migration
  resolves.
- **Reduced motion.** If we add the streaming-load fade-in transition,
  respect `prefers-reduced-motion` and disable it.
- **Future**: lasso-select, text labels on hover, density heatmap at
  low zoom. All become single-layer additions on the deck.gl stack.
