// DeckAtlasCanvas — the WebGL renderer for the paper atlas. Three layers:
//
//   1. DensityFieldLayer — bottom. Two-pass GPU pipeline that accumulates
//      weighted colour and density into a float framebuffer, then tone-maps
//      to a per-pixel **mean** colour modulated by a log-density brightness
//      envelope. Replaces the old additive ScatterplotLayer "glow", which
//      clipped to white in dense regions and lost venue-colour information
//      exactly where it was most informative.
//   2. ScatterplotLayer over all visible points (the "cores") — constant
//      world size, normal blending, full opacity. The crisp small stars
//      that overlay the density field.
//   3. ScatterplotLayer over selected papers — yellow halos with stroke,
//      normal blending, fixed pixel size so they remain visible during
//      zoom-out. Drawn on top.
//
// Picking: the cores layer is pickable per-point. The density field and
// highlights are pickable:false so clicks fall through to the underlying
// paper.

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DeckGL } from "@deck.gl/react";
import { OrthographicView, COORDINATE_SYSTEM } from "@deck.gl/core";
import type { PickingInfo } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import type { AtlasPoint } from "../lib/streamAtlas";
import DensityFieldLayer from "./DensityFieldLayer";

export type DeckAtlasCanvasProps = {
  points: AtlasPoint[];
  bbox: [number, number, number, number] | null;
  hiddenSources: Set<string>;
  selectedIds: Set<string>;
  sourceToColor: (source: string | null) => [number, number, number, number];
  onHover: (paper: AtlasPoint | null, screen: { x: number; y: number } | null) => void;
  onClick: (paper: AtlasPoint) => void;
};

// Per-point alpha is held at full (255). Per-layer effective alpha
// comes from each layer's `opacity` uniform, so we never have to
// re-upload the 524k color buffer to change visual intensity.
const POINT_ALPHA = 255;

// Tunable knobs for the starfield renderer. The "core" (constant world
// size, solid, normal blend) sits on top of a "density field" (constant
// pixel size, two-pass float-FBO mean-colour accumulator). The cores
// give us crisp small stars at any zoom; the density field traces the
// matplotlib-style topology in dense regions without colour-clipping.
type Tuning = {
  coreRadius: number; // world units — actual paper "star" size
  coreMinPixels: number; // floor so cores stay clickable when sub-pixel
  coreMaxPixels: number; // cap so cores don't grow into giant blobs
  densityRadiusPixels: number; // constant screen-space disc radius for the density accumulator
  densityWeight: number; // per-dot weight in the accumulator (was the old "glowAlpha")
  brightnessCap: number; // log(1+cap) maps to full tone-mapped brightness
};

const TUNING_DEFAULTS: Tuning = {
  // Small world-space cores so they read as discrete stars when zoomed
  // in but recede to sub-pixel specks at default zoom (cumulative
  // stippling carries the topology along with the density field).
  coreRadius: 0.004,
  coreMinPixels: 0,
  coreMaxPixels: 12,
  // Density field tuned for legible venue-coloured topology without
  // dense regions white-clipping. The tight 2px radius keeps each
  // contribution local; weight=1 pumps full per-dot intensity into the
  // accumulator; brightness cap=3 means ~3 overlapping dots saturate
  // to peak brightness in the log curve.
  densityRadiusPixels: 2,
  densityWeight: 1,
  brightnessCap: 3,
};

// Bumped to v3 because the schema changed — the v2 keys (glowRadiusPixels,
// glowAlpha) no longer exist. Merging would leave junk fields in the
// tuning object and silently ignore the new keys.
const TUNING_STORAGE_KEY = "atlas:tuning:v3";

function loadTuning(): Tuning {
  if (typeof window === "undefined") return TUNING_DEFAULTS;
  try {
    const raw = window.localStorage.getItem(TUNING_STORAGE_KEY);
    if (!raw) return TUNING_DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Tuning>;
    // Merge over defaults so missing/old keys fall back gracefully.
    return { ...TUNING_DEFAULTS, ...parsed };
  } catch {
    return TUNING_DEFAULTS;
  }
}

// Neutral mid-gray for arxiv. Visible on #000 bg, recedes behind
// venue-color dots wherever they coincide.
const ARXIV_RGB: [number, number, number] = [180, 180, 180];

const FALLBACK_RGBA: [number, number, number, number] = [156, 163, 175, 255];
const HIGHLIGHT_FILL: [number, number, number, number] = [255, 216, 74, 255];
const HIGHLIGHT_STROKE: [number, number, number, number] = [0, 0, 0, 255];

export default function DeckAtlasCanvas({
  points,
  bbox,
  hiddenSources,
  selectedIds,
  sourceToColor,
  onHover,
  onClick,
}: DeckAtlasCanvasProps) {
  // Filter out hidden sources before they reach the GPU. With a single
  // layer the legend toggle is just data filtering — no per-layer
  // visibility flags to juggle.
  const visiblePoints = useMemo(() => {
    if (hiddenSources.size === 0) return points;
    return points.filter((p) => !hiddenSources.has(p.source ?? "unknown"));
  }, [points, hiddenSources]);

  const selectedPoints = useMemo(() => {
    if (selectedIds.size === 0) return [] as AtlasPoint[];
    return points.filter((p) => selectedIds.has(p.paper_id));
  }, [points, selectedIds]);

  // Camera: centre on the bbox midpoint, pick a zoom that fits the long
  // axis into ~800 viewport pixels (rough — the user pans/zooms from here).
  // OrthographicView's zoom interprets 1 world unit = 2^zoom pixels.
  // initialViewState is keyed by view id when `views` is an array.
  const initialZoom = useMemo(() => {
    if (!bbox) return 4;
    const [xmin, ymin, xmax, ymax] = bbox;
    const span = Math.max(xmax - xmin, ymax - ymin) || 1;
    return Math.log2(800 / span);
  }, [bbox]);

  const initialViewState = useMemo(() => {
    if (!bbox) {
      return { ortho: { target: [0, 0, 0] as [number, number, number], zoom: initialZoom } };
    }
    const [xmin, ymin, xmax, ymax] = bbox;
    const cx = (xmin + xmax) / 2;
    const cy = (ymin + ymax) / 2;
    return {
      ortho: { target: [cx, cy, 0] as [number, number, number], zoom: initialZoom },
    };
  }, [bbox, initialZoom]);

  // Tuning state — drives the layer config below. Loaded once from
  // localStorage on mount (this component is dynamic-imported with
  // ssr:false, so window access is always safe at init time).
  const [tuning, setTuning] = useState<Tuning>(loadTuning);
  const [tuningOpen, setTuningOpen] = useState<boolean>(false);
  // Persist every change. Cheap — JSON.stringify on the small tuning
  // object is sub-microsecond and only fires when the user moves a
  // slider.
  useEffect(() => {
    try {
      window.localStorage.setItem(TUNING_STORAGE_KEY, JSON.stringify(tuning));
    } catch {
      /* private mode / quota — ignore */
    }
  }, [tuning]);
  const resetTuning = useCallback(() => setTuning(TUNING_DEFAULTS), []);

  // Layer callbacks return `false` rather than `void` because deck.gl 9's
  // typed overload requires a boolean to indicate "event handled"; false
  // lets the event keep propagating.
  const handleHover = useCallback(
    (info: PickingInfo): boolean => {
      const obj = info.object as AtlasPoint | undefined;
      if (obj) onHover(obj, { x: info.x, y: info.y });
      else onHover(null, null);
      return false;
    },
    [onHover],
  );

  const handleClick = useCallback(
    (info: PickingInfo): boolean => {
      const obj = info.object as AtlasPoint | undefined;
      if (obj) {
        onClick(obj);
      }
      return false;
    },
    [onClick],
  );

  // LOAD-BEARING: this callback's reference MUST stay stable across
  // renders that only change zoom. If it didn't, deck.gl's updateTriggers
  // would re-evaluate the accessor and re-upload all 524k colors on
  // every wheel tick (~100ms stall per frame, page freezes during zoom).
  // useCallback([sourceToColor]) gives us that stability — don't inline.
  const getFillColor = useCallback(
    (d: AtlasPoint): [number, number, number, number] => {
      if (d.source === "arxiv") {
        return [ARXIV_RGB[0], ARXIV_RGB[1], ARXIV_RGB[2], POINT_ALPHA];
      }
      const [r, g, b] = sourceToColor(d.source);
      return [r, g, b, POINT_ALPHA];
    },
    [sourceToColor],
  );

  const layers = useMemo(() => {
    const out: Layer[] = [];
    if (visiblePoints.length > 0) {
      // Density field — drawn FIRST so the cores sit on top. Two-pass
      // GPU pipeline (see DensityFieldLayer.ts): accumulate weighted
      // colour and density into a float FBO, tone-map to mean colour ×
      // log-density brightness. Replaces the old additive ScatterplotLayer
      // glow, which colour-clipped to white in dense regions.
      out.push(
        new DensityFieldLayer<AtlasPoint>({
          id: "atlas-points-density",
          data: visiblePoints,
          coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          getPosition: (d) => [d.x, d.y],
          getFillColor,
          radiusPixels: tuning.densityRadiusPixels,
          weight: tuning.densityWeight,
          brightnessCap: tuning.brightnessCap,
          pickable: false,
          updateTriggers: { getFillColor },
        }),
      );
      // Core layer — the actual "star" for each paper. Constant world
      // size so cores grow into clickable discs as you zoom in. Full
      // opacity, normal alpha blending (deck.gl default) so overlapping
      // cores draw cleanly on top of each other rather than summing.
      out.push(
        new ScatterplotLayer<AtlasPoint>({
          id: "atlas-points-core",
          data: visiblePoints,
          coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          getPosition: (d) => [d.x, d.y],
          getFillColor,
          getRadius: tuning.coreRadius,
          radiusUnits: "common",
          radiusMinPixels: tuning.coreMinPixels,
          radiusMaxPixels: tuning.coreMaxPixels,
          opacity: 1,
          pickable: true,
          onHover: handleHover,
          onClick: handleClick,
          updateTriggers: { getFillColor },
        }),
      );
    }
    if (selectedPoints.length > 0) {
      out.push(
        new ScatterplotLayer<AtlasPoint>({
          id: "highlights",
          data: selectedPoints,
          coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
          getPosition: (d) => [d.x, d.y],
          getFillColor: HIGHLIGHT_FILL,
          getLineColor: HIGHLIGHT_STROKE,
          getRadius: 10,
          radiusUnits: "pixels",
          stroked: true,
          getLineWidth: 2,
          lineWidthUnits: "pixels",
          // Normal blending for highlights — we want crisp halos, not
          // additive glow stacking on top of itself.
          pickable: false,
        }),
      );
    }
    return out;
  }, [
    visiblePoints,
    selectedPoints,
    getFillColor,
    handleHover,
    handleClick,
    tuning.coreRadius,
    tuning.coreMinPixels,
    tuning.coreMaxPixels,
    tuning.densityRadiusPixels,
    tuning.densityWeight,
    tuning.brightnessCap,
  ]);

  return (
    <>
      <DeckGL
        views={[new OrthographicView({ id: "ortho" })]}
        initialViewState={initialViewState}
        controller={true}
        layers={layers}
        style={{
          position: "absolute",
          top: "0",
          left: "0",
          right: "0",
          bottom: "0",
        }}
      />
      <TuningPanel
        tuning={tuning}
        onChange={setTuning}
        onReset={resetTuning}
        open={tuningOpen}
        onToggle={() => setTuningOpen((v) => !v)}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Tuning popup — bottom-left of the canvas, gear button to toggle.
// All sliders live-update so dragging gives immediate visual feedback.
// ---------------------------------------------------------------------------

function TuningPanel({
  tuning,
  onChange,
  onReset,
  open,
  onToggle,
}: {
  tuning: Tuning;
  onChange: (next: Tuning) => void;
  onReset: () => void;
  open: boolean;
  onToggle: () => void;
}) {
  const update = useCallback(
    <K extends keyof Tuning>(key: K, value: Tuning[K]) => {
      onChange({ ...tuning, [key]: value });
    },
    [tuning, onChange],
  );
  return (
    <>
      {open && (
        <div className="absolute bottom-12 left-3 z-30 w-72 max-h-[70vh] overflow-y-auto card bg-base-200/90 backdrop-blur border border-base-300/60 p-3 text-xs select-none shadow-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] uppercase tracking-wider font-medium text-base-content/60">
              Tuning
            </span>
            <button
              type="button"
              onClick={onToggle}
              title="Close"
              className="text-base-content/40 hover:text-base-content"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-3.5 w-3.5"
              >
                <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" />
              </svg>
            </button>
          </div>
          <TuningSection title="Core (the star)">
            <SliderRow
              label="Radius (world)"
              value={tuning.coreRadius}
              min={0.001}
              max={0.05}
              step={0.0005}
              format={(v) => v.toFixed(4)}
              onChange={(v) => update("coreRadius", v)}
            />
            <SliderRow
              label="Min pixels"
              value={tuning.coreMinPixels}
              min={0}
              max={4}
              step={1}
              format={(v) => v.toString()}
              onChange={(v) => update("coreMinPixels", v)}
            />
            <SliderRow
              label="Max pixels"
              value={tuning.coreMaxPixels}
              min={4}
              max={50}
              step={1}
              format={(v) => v.toString()}
              onChange={(v) => update("coreMaxPixels", v)}
            />
          </TuningSection>
          <TuningSection title="Density field">
            <SliderRow
              label="Radius (px)"
              value={tuning.densityRadiusPixels}
              min={2}
              max={32}
              step={0.5}
              format={(v) => v.toFixed(1)}
              onChange={(v) => update("densityRadiusPixels", v)}
            />
            <SliderRow
              label="Weight"
              value={tuning.densityWeight}
              min={0.01}
              max={1.0}
              step={0.01}
              format={(v) => v.toFixed(2)}
              onChange={(v) => update("densityWeight", v)}
            />
            <SliderRow
              label="Brightness cap"
              value={tuning.brightnessCap}
              min={1}
              max={50}
              step={0.5}
              format={(v) => v.toFixed(1)}
              onChange={(v) => update("brightnessCap", v)}
            />
          </TuningSection>
          <button
            type="button"
            onClick={onReset}
            className="mt-2 btn btn-ghost btn-xs w-full text-base-content/60 hover:text-base-content"
          >
            Reset defaults
          </button>
        </div>
      )}
      <button
        type="button"
        onClick={onToggle}
        title="Tune renderer"
        className="absolute bottom-3 left-3 z-30 btn btn-ghost btn-sm normal-case text-base-content/60 hover:text-base-content gap-1"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-3.5 w-3.5"
        >
          <path
            fillRule="evenodd"
            d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z"
            clipRule="evenodd"
          />
        </svg>
        Tune
      </button>
    </>
  );
}

function TuningSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="mb-3">
      <div className="text-[10px] uppercase tracking-wider text-base-content/40 mb-1">
        {title}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 text-[11px] text-base-content/70 shrink-0">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="flex-1 accent-accent"
      />
      <span className="w-12 text-right text-[10px] tabular-nums text-base-content/50">
        {format(value)}
      </span>
    </div>
  );
}

// Helper kept here (rather than in lib/) since it only matters for the
// canvas component's source palette.
export function hexToRgba(hex: string): [number, number, number, number] {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return [r, g, b, 255];
}

export { FALLBACK_RGBA };
