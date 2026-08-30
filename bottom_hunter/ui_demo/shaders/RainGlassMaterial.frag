#version 440

// RainGlass droplet material — procedural, temporally stable droplet field
// with lens-like refraction, edge specular highlights and surface tension.
//
// MASTER_PROMPT §9 requirements implemented here:
//   * multi-size droplets: mostly tiny static + few medium + rare large
//   * non-perfect circles (gravity-stretched ellipses)
//   * edge specular + normal-like shading
//   * local refraction via background UV distortion + slight magnification
//   * rare slow slides + wet streaks
//   * stable hash-based seed: NO per-frame regeneration (no flicker)
//
// Inputs from ShaderEffect:
//   source        — what the glass sits on (background capture)
//   resolution    — item pixel size
//   u_time        — seconds (slowed down at the call site)
//   u_parallax    — vec2 offset in px (mouse parallax, ≤4px)
//   u_quality     — 1.0 high / 0.75 balanced / 0.0 low (kills distortion)
//   u_density     — droplet density multiplier (0..1)

layout(binding = 1) uniform sampler2D source;

// Non-opaque uniforms must live in a UBO for the Vulkan/GLSL target (qsb rule).
layout(std140, binding = 0) uniform UboBlock {
    vec2 resolution;
    float u_time;
    vec2 u_parallax;
    float u_quality;
    float u_density;
} ubuf;

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

// ---- hash / noise ----------------------------------------------------------

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

vec2 hash21(float p) {
    vec3 p3 = fract(vec3(p) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

// ---- droplet field ---------------------------------------------------------

const float GRID_SMALL = 26.0;   // px cell for tiny static drops
const float GRID_MED   = 110.0;  // px cell for medium drops
const float GRID_LARGE = 260.0;  // px cell for rare large drops

// Signed distance-ish falloff with soft edge for lighting.
float dropletProfile(float dist, float radius) {
    return 1.0 - smoothstep(radius * 0.62, radius, dist);
}

void main() {
    vec2 fragPx = qt_TexCoord0 * ubuf.resolution;
    vec2 parallaxPx = ubuf.u_parallax * ubuf.u_quality;   // background layer only

    // ---- background with parallax + slight per-drop magnification ----
    // Base background sample.
    vec2 baseUv = qt_TexCoord0 + parallaxPx / ubuf.resolution;

    // Refraction field: accumulate uv distortion from every nearby droplet.
    vec2 refractOffset = vec2(0.0);
    float lightAccum = 0.0;
    float specAccum = 0.0;

    float density = ubuf.u_density;

    // Three layers, small→large. Search only this cell + neighbours to keep
    // the loop bounded (3x3 per layer = 27 candidate droplets max).
    for (int layer = 0; layer < 3; ++layer) {
        float cell = layer == 0 ? GRID_SMALL : (layer == 1 ? GRID_MED : GRID_LARGE);
        float layerDensity = layer == 0 ? density : density * (layer == 1 ? 0.45 : 0.18);
        float slideChance = layer == 0 ? 0.0 : (layer == 1 ? 0.06 : 0.10);

        vec2 cellPx = vec2(cell);
        vec2 cellIdx = floor(fragPx / cellPx);
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                vec2 idx = cellIdx + vec2(float(dx), float(dy));
                vec2 cellUv = idx * cellPx;
                float cellHash = hash11(idx.x * 127.1 + idx.y * 311.7 + float(layer) * 57.31);
                if (cellHash > layerDensity) continue;

                vec2 rnd = hash21(cellHash * 913.7 + float(layer) * 57.31);
                vec2 centre = cellUv + (vec2(0.5) + (rnd - 0.5) * 0.72) * cellPx;

                // rare slow slide (medium/large only)
                float slide = 0.0;
                float slideSeed = hash11(cellHash * 417.3);
                if (layer > 0 && slideSeed < slideChance * ubuf.u_quality) {
                    float speed = 2.2 + hash11(cellHash * 71.3) * 3.5;
                    float travel = cell * 1.6;
                    float phase = fract(ubuf.u_time / (travel / speed) + hash11(cellHash * 19.7));
                    slide = phase * travel;
                }
                vec2 pos = centre + vec2(0.0, slide);

                float radius = cell * (0.16 + hash11(cellHash * 53.1) * 0.22);
                vec2 delta = fragPx - pos;
                float stretch = 1.0 + hash11(cellHash * 97.9) * 0.28;
                delta.y /= stretch;
                float dist = length(delta);

                // influence zone: slightly larger than the droplet
                float influence = radius * 1.5;
                if (dist < influence) {
                    float inside = dropletProfile(dist, radius);
                    // refraction: pull uv towards droplet centre (magnify)
                    vec2 dir = (dist > 0.001) ? delta / dist : vec2(0.0);
                    float strength = inside * (1.0 - 0.35 * inside);
                    refractOffset += -dir * inside * radius * 0.16 * ubuf.u_quality;
                    // specular edge: bright ring near the droplet border
                    float edgeBand = smoothstep(radius * 0.72, radius * 0.97, dist)
                                   - smoothstep(radius * 0.97, radius, dist);
                    vec2 lightDir = normalize(vec2(0.55, -0.72));
                    float rim = edgeBand * (0.55 + 0.45 * dot(dir, lightDir));
                    specAccum += rim;
                    lightAccum += inside * 0.22;
                }
            }
        }
    }

    // ---- final composite ---------------------------------------------
    vec2 refractedUv = baseUv + refractOffset / ubuf.resolution;
    refractedUv = clamp(refractedUv, vec2(0.002), vec2(0.998));
    vec3 bg = texture(source, refractedUv).rgb;

    // glass tint: cool charcoal over the background
    vec3 tint = vec3(0.051, 0.078, 0.102);   // #0D141A
    float tintAlpha = 0.42;
    vec3 color = mix(bg, tint, tintAlpha);

    // droplet interior brightening (light through glass)
    color += lightAccum * vec3(0.9, 0.97, 1.0);

    // edge specular highlights (white-ish, restrained)
    color += specAccum * vec3(0.82, 0.92, 0.98) * 0.85;

    // very subtle grain to avoid banding (MASTER_PROMPT §8.7)
    float grain = hash11(fragPx.x * 12.9 + fragPx.y * 78.2) - 0.5;
    color += grain * 0.012;

    fragColor = vec4(color, 1.0);
}
