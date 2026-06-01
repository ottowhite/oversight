// DensityFieldLayer — a custom deck.gl Layer that renders a per-pixel
// mean-color density field.
//
// Multi-pass GPU pipeline, modelled on `HeatmapLayer`'s framebuffer
// scaffolding (see `node_modules/@deck.gl/aggregation-layers/dist/
// heatmap-layer/` for reference). The two passes are:
//
//   1. ACCUMULATOR — for each visible point, draw an instanced disc-quad
//      in pixel-space with additive blending into a float framebuffer.
//      The fragment writes `vec4(color.rgb * αw, αw)` where `αw` is the
//      smooth coverage of the disc edge scaled by the per-dot weight.
//      After all dots, each pixel of the FBO holds:
//        rgb = Σ color_i · α_i · coverage_i
//        a   = Σ            α_i · coverage_i
//
//   2. TONE-MAP — a fullscreen quad reads the float FBO and produces the
//      final pixel:
//        mean       = rgb / max(a, ε)
//        brightness = log(1 + a) / log(1 + brightnessCap)
//        out        = vec4(mean · brightness, brightness)
//      with normal alpha blending over the page background. Brightness is
//      bounded by `brightnessCap`, so dense regions don't white-clip while
//      the mean color stays inside the convex hull of contributing dots.
//
// The accumulator FBO is sized to the device-pixel viewport so the tone-map
// quad samples 1:1 — anything else introduces blur or misalignment.

import { Layer, project32 } from "@deck.gl/core";
import type {
  LayerContext,
  UpdateParameters,
  DefaultProps,
  LayerProps,
} from "@deck.gl/core";
import { Model, Geometry } from "@luma.gl/engine";
import type { Framebuffer, Texture } from "@luma.gl/core";

import {
  ACCUM_VS,
  ACCUM_FS,
  TONEMAP_VS,
  TONEMAP_FS,
} from "./density-field-shaders";

// Uniform block for the accumulator pass. Shared between vs+fs; the
// `density` namespace is referenced by both shaders.
const densityUniforms = {
  name: "density",
  vs: `\
layout(std140) uniform densityUniforms {
  float radiusPixels;
  float weight;
  float brightnessCap;
  float softness;
} density;
`,
  fs: `\
layout(std140) uniform densityUniforms {
  float radiusPixels;
  float weight;
  float brightnessCap;
  float softness;
} density;
`,
  uniformTypes: {
    radiusPixels: "f32",
    weight: "f32",
    brightnessCap: "f32",
    softness: "f32",
  },
} as const;

// Per-dot accessor for fill color, matching deck.gl conventions.
type ColorAccessor<D> = (d: D) => [number, number, number, number];

export type DensityFieldLayerProps<D = unknown> = LayerProps & {
  data: D[];
  getPosition: (d: D) => [number, number];
  getFillColor: ColorAccessor<D>;
  // Per-dot footprint in screen pixels. Constant so density is a
  // screen-space signal: dense world clusters → many overlapping
  // screen-radii → bright pixel.
  radiusPixels?: number;
  // Per-dot weight in the density accumulator. Lower = log curve compresses
  // density less aggressively; higher = clusters saturate brightness sooner.
  weight?: number;
  // log(1 + brightnessCap) maps to full brightness in the tone map.
  brightnessCap?: number;
};

const defaultProps: DefaultProps<DensityFieldLayerProps> = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getPosition: { type: "accessor", value: ((d: any) => d.position) as any },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getFillColor: { type: "accessor", value: [255, 255, 255, 255] as any },
  radiusPixels: { type: "number", min: 0.5, max: 200, value: 6 },
  weight: { type: "number", min: 0, max: 10, value: 0.1 },
  brightnessCap: { type: "number", min: 0.1, max: 200, value: 5 },
};

// Fullscreen quad geometry for the tone-map pass.
const FULLSCREEN_QUAD_POSITIONS = new Float32Array([
  -1, -1,
   1, -1,
  -1,  1,
   1,  1,
]);

// Quad-corner offsets (-1..1) for the per-instance disc quads.
const INSTANCE_QUAD_POSITIONS = new Float32Array([
  -1, -1, 0,
   1, -1, 0,
  -1,  1, 0,
   1,  1, 0,
]);

interface DensityState {
  accumModel: Model | null;
  tonemapModel: Model | null;
  // `models` is the array deck.gl introspects via Layer.getModels(). Putting
  // both Models here is what makes deck.gl's `_drawLayer` push shader-module
  // uniforms (in particular the `project` module's viewport matrix) into
  // BOTH models every frame, so `project_position_to_clipspace` in the
  // accumulator vertex shader actually has a viewport to project with.
  // Without this, our custom render pass would draw garbage clipspace coords
  // — see the long debug trail in commit history if you want the details.
  models: Model[];
  fbo: Framebuffer | null;
  fboTexture: Texture | null;
  fboWidth: number;
  fboHeight: number;
  fboFormat: "rgba32float" | "rgba16float" | "rgba8unorm";
}

export default class DensityFieldLayer<D = unknown> extends Layer<DensityFieldLayerProps<D>> {
  static layerName = "DensityFieldLayer";
  static defaultProps = defaultProps;

  declare state: DensityState & { [key: string]: unknown };

  getShaders(shaders?: Record<string, unknown>): Record<string, unknown> {
    return super.getShaders({
      ...shaders,
      modules: [project32, densityUniforms],
    });
  }

  initializeState(context: LayerContext): void {
    this.state = {
      accumModel: null,
      tonemapModel: null,
      models: [],
      fbo: null,
      fboTexture: null,
      fboWidth: 0,
      fboHeight: 0,
      fboFormat: "rgba32float",
    };

    // Per-instance attributes feed the accumulator pass. `instancePositions`
    // is a 64-bit world coord (same as ScatterplotLayer) so the projection
    // module can do its fp32-low correction. `instanceFillColors` is
    // unorm8 RGBA → shader sees 0..1 floats.
    this.getAttributeManager()!.addInstanced({
      instancePositions: {
        size: 3,
        type: "float64",
        fp64: this.use64bitPositions(),
        accessor: "getPosition",
        transition: false,
      },
      instanceFillColors: {
        size: 4,
        type: "unorm8",
        accessor: "getFillColor",
        defaultValue: [0, 0, 0, 255],
        transition: false,
      },
    });

    // Pick float framebuffer format based on device capabilities. WebGL2
    // requires `EXT_color_buffer_float` (exposed in luma.gl as
    // `float32-renderable-webgl`) for rgba32float render targets. Fall back
    // to rgba16float (half-float) if not available — still gives us the
    // separation between density and color that uint8 can't.
    const features = context.device.features;
    let fboFormat: DensityState["fboFormat"] = "rgba8unorm";
    if (features.has("float32-renderable-webgl") && features.has("texture-blend-float-webgl")) {
      fboFormat = "rgba32float";
    } else if (features.has("float16-renderable-webgl")) {
      fboFormat = "rgba16float";
    }
    this.state.fboFormat = fboFormat;

    this._buildModels();
    this._ensureFramebuffer();
  }

  shouldUpdateState(params: UpdateParameters<this>): boolean {
    return params.changeFlags.somethingChanged;
  }

  updateState(params: UpdateParameters<this>): void {
    super.updateState(params);
    if (params.changeFlags.extensionsChanged) {
      this.state.accumModel?.destroy();
      this.state.tonemapModel?.destroy();
      this._buildModels();
      this.getAttributeManager()!.invalidateAll();
    }
  }

  finalizeState(context: LayerContext): void {
    this.state.accumModel?.destroy();
    this.state.tonemapModel?.destroy();
    this.state.fbo?.destroy();
    this.state.fboTexture?.destroy();
    super.finalizeState(context);
  }

  draw(opts: { renderPass: unknown; uniforms?: unknown }): void {
    const { device } = this.context;
    const numInstances = this.getNumInstances();
    if (numInstances === 0) return;

    this._ensureFramebuffer();
    const { accumModel, tonemapModel, fbo, fboTexture, fboWidth, fboHeight } = this.state;
    if (!accumModel || !tonemapModel || !fbo || !fboTexture) return;

    const radiusPixels = this.props.radiusPixels ?? 6;
    const weight = this.props.weight ?? 0.1;
    const brightnessCap = this.props.brightnessCap ?? 5;

    // Pass 1: accumulator → float FBO. We open a dedicated render pass
    // bound to the FBO, clear it to zero, then draw the instanced discs
    // with additive blending. luma.gl 9's `beginRenderPass` is the right
    // primitive here — calling model.draw with the deck.gl-supplied
    // renderPass would write to the screen.
    accumModel.setInstanceCount(numInstances);
    accumModel.shaderInputs.setProps({
      density: {
        radiusPixels,
        weight,
        brightnessCap,
        softness: Math.min(1.0, 2.0 / Math.max(radiusPixels, 1)),
      },
    });
    const accumPass = device.beginRenderPass({
      framebuffer: fbo,
      clearColor: [0, 0, 0, 0],
      parameters: { viewport: [0, 0, fboWidth, fboHeight] },
    });
    try {
      accumModel.draw(accumPass);
    } finally {
      accumPass.end();
    }

    // Pass 2: tone-map → the deck.gl-managed render pass. We use the
    // existing render pass so the result composites correctly with other
    // layers in the same frame.
    tonemapModel.shaderInputs.setProps({
      density: {
        radiusPixels,
        weight,
        brightnessCap,
        softness: 0,
      },
    });
    tonemapModel.setBindings({ accumTexture: fboTexture });
    tonemapModel.draw(this.context.renderPass);
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  private _buildModels(): void {
    const { device } = this.context;
    const attributeManager = this.getAttributeManager()!;

    // ACCUMULATOR
    const accumShaders = this.getShaders({ vs: ACCUM_VS, fs: ACCUM_FS });
    const accumModel = new Model(device, {
      ...accumShaders,
      id: `${this.props.id}-accum`,
      bufferLayout: attributeManager.getBufferLayouts(),
      geometry: new Geometry({
        topology: "triangle-strip",
        attributes: {
          positions: { size: 3, value: INSTANCE_QUAD_POSITIONS },
        },
      }),
      isInstanced: true,
      parameters: {
        depthWriteEnabled: false,
        depthCompare: "always",
        cullMode: "none",
        // Additive blend into the FBO. The src/dst factors here are the
        // same as the old glow layer, but the float framebuffer doesn't
        // clip to 1.0 so density and color stay separable.
        blend: true,
        blendColorOperation: "add",
        blendColorSrcFactor: "one",
        blendColorDstFactor: "one",
        blendAlphaOperation: "add",
        blendAlphaSrcFactor: "one",
        blendAlphaDstFactor: "one",
      },
    });

    // TONE-MAP
    const tonemapShaders = super.getShaders({
      vs: TONEMAP_VS,
      fs: TONEMAP_FS,
      modules: [densityUniforms],
    });
    const tonemapModel = new Model(device, {
      ...tonemapShaders,
      id: `${this.props.id}-tonemap`,
      bufferLayout: [{ name: "positions", format: "float32x2" }],
      geometry: new Geometry({
        topology: "triangle-strip",
        attributes: {
          positions: { size: 2, value: FULLSCREEN_QUAD_POSITIONS },
        },
      }),
      vertexCount: 4,
      parameters: {
        depthWriteEnabled: false,
        depthCompare: "always",
        cullMode: "none",
        blend: true,
        blendColorOperation: "add",
        blendColorSrcFactor: "src-alpha",
        blendColorDstFactor: "one-minus-src-alpha",
        blendAlphaOperation: "add",
        blendAlphaSrcFactor: "one",
        blendAlphaDstFactor: "one-minus-src-alpha",
      },
    });
    // The tonemap doesn't use the per-instance position / colour buffers —
    // tell deck.gl's _setModelAttributes to skip them so we don't get
    // warning spam and bad pipeline state every time data changes.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (tonemapModel as any).userData = {
      excludeAttributes: {
        instancePositions: true,
        instancePositions64Low: true,
        instanceFillColors: true,
      },
    };

    this.state.accumModel = accumModel;
    this.state.tonemapModel = tonemapModel;
    // Exposing both via state.models is what wires deck.gl's per-frame
    // setShaderModuleProps into our custom models. Order matters: accum
    // first so attribute updates and project-module props flow into the
    // pass that actually needs them.
    this.state.models = [accumModel, tonemapModel];
  }

  // Resize / (re)create the float framebuffer to match the device-pixel
  // viewport. The tone-map quad assumes 1:1 sampling so any size mismatch
  // shows up as blur. Called on every draw — `Framebuffer.resize` is a
  // no-op when the size is unchanged.
  private _ensureFramebuffer(): void {
    const { device } = this.context;
    const canvas = device.canvasContext;
    if (!canvas) return;
    const width = Math.max(1, canvas.drawingBufferWidth);
    const height = Math.max(1, canvas.drawingBufferHeight);
    if (this.state.fbo && this.state.fboWidth === width && this.state.fboHeight === height) {
      return;
    }
    this.state.fboTexture?.destroy();
    this.state.fbo?.destroy();
    const texture = device.createTexture({
      format: this.state.fboFormat,
      width,
      height,
      mipLevels: 1,
      sampler: {
        minFilter: "nearest",
        magFilter: "nearest",
        addressModeU: "clamp-to-edge",
        addressModeV: "clamp-to-edge",
      },
    });
    const fbo = device.createFramebuffer({
      width,
      height,
      colorAttachments: [texture],
    });
    this.state.fbo = fbo;
    this.state.fboTexture = texture;
    this.state.fboWidth = width;
    this.state.fboHeight = height;
  }
}
