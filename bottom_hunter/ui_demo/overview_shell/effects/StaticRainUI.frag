#version 440

// CrystalGlassMaterialLab — layer 3: static, realistic small rain droplets.
// StaticRainUI — OVERVIEW SHELL VARIANT of the FROZEN material_lab
// StaticRain.frag. Droplet optics below are byte-identical to the accepted
// shader (do NOT tune count/size/clustering/lens/glint here); the ONLY
// addition is the importance/exclusion mask (u_mask): a low-resolution
// texture whose R channel multiplies droplet presence, protecting critical
// UI content (titles, values, buttons) with low rain density while card
// margins / panel edges / empty areas keep normal density.
//
// Droplets are screen-space water lenses stuck to the glass surface — NOT
// spheres / orbs / bubbles, NOT translucent alpha circles. Visual hierarchy:
//   #1 local refraction / lens distortion (convex hemisphere-normal lens)
//   #2 tiny directional specular glint (upper-left key light)
//   #3 subtle dark opposite edge (contact shadow)
//   #4 extremely weak body shading
// Never a uniform 360-degree ring.
//
// Refraction is size-dependent (LENS_PX): micro very weak, small clearly
// visible but subtle, medium strong enough to bend a building edge / window
// light, large strongest but still believable. Total UV displacement is
// clamped (no fisheye / bubble distortion). The distortion varies smoothly
// across the lens and approaches zero at the physical boundary.
//
// Shape: per-droplet aspect (height/width, ~0.88-1.26; medium slightly
// stretched vertically) + very restrained boundary wobble (amp <= 6.2%).
// Never a metaball / blob.
//
// Coverage: low-frequency wet/dry clustering (dry regions + sparse regions +
// small clusters), synced 1:1 with droplet_stats.cluster_mask. NOT uniform.
//
// Diameter quota (px, hard-capped, absolute max 30 never exceeded):
//   micro  1.5 - 4    (sparse-modulated, static)
//   small  4   - 8
//   medium 8   - 15
//   large  15  - 25
//
// Presence weights (DENS) are tuned and CPU-mirrored in droplet_stats.py:
//   micro ~431, small ~100, medium ~22, large ~3, total ~556 (target 500-600,
//   hard cap 800). Do NOT raise them — they were chosen to stay inside quota.
//
// Fully static stage: hash field is time-stable, no slide / trail /
// per-frame regeneration. (Gravity stretch / teardrop asymmetry are static
// silhouette features, not animation.)
//
// u_debug = 1 draws every candidate droplet (full-density field) as a
// colour-coded bounding ring + centre dot over the dimmed scene:
//   micro=green small=yellow medium=orange large=red  (diameter proof)
// All smoothstep calls use strictly increasing edges (edge0 < edge1).
//
// Inputs (ShaderEffect):
//   source      — the COMPOSITED UI scene (environment + glass panels +
//                 chrome/content), captured with hideSource = true
//   u_mask      — importance mask (pre-dilated in QML beyond text bounds:
//                 values +28px, text/chip +20px); R channel multiplies
//                 droplet presence (white = normal, dark = protected);
//                 sampled footprint-aware (centre + 4 offsets, min)
//   resolution  — output size in px (logical; lab runs at DPR 1)
//   u_quality   — 1.0 high / 0.75 balanced
//   u_density   — 0..1 global density
//   u_debug     — 0 normal / 1 bounding circles
//   u_time      — reserved (fixed; static stage)

layout(binding = 1) uniform sampler2D source;
layout(binding = 2) uniform sampler2D u_mask;

// Fragment-only ShaderEffect contract: the built-in vertex shader shares this
// buffer, so qt_Matrix (offset 0) and qt_Opacity (offset 64) MUST come first;
// custom uniforms follow. Block name must match the built-in one.
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 resolution;
    float u_quality;
    float u_density;
    float u_debug;
    float u_time;
};

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

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

// Diameter quota per layer: (grid cell px, dmin, dmax, presence weight).
// DENS is tuned + CPU-mirrored in droplet_stats.py (total ~556, cap 800).
const float GRID[4]  = float[4](9.0,  22.0, 60.0,  180.0);
const float D_MIN[4] = float[4](1.5,  4.0,  8.0,  15.0);
const float D_MAX[4] = float[4](4.0,  8.0,  15.0, 25.0);
const float DENS[4]  = float[4](0.0581, 0.0866, 0.1341, 0.1356);

// Size-dependent optics: max UV displacement (px) and glint amplitude per
// layer. micro = very weak · small = subtle · medium = bends edges ·
// large = strongest (total displacement clamped later; no fisheye).
const float LENS_PX[4] = float[4](0.9, 2.2, 5.0, 8.0);
const float GLINT_A[4] = float[4](0.85, 0.60, 0.50, 0.45);

vec3 layerDebugColor(int layer) {
    if (layer == 0) return vec3(0.25, 0.95, 0.45);
    if (layer == 1) return vec3(0.99, 0.85, 0.15);
    if (layer == 2) return vec3(0.99, 0.55, 0.18);
    return vec3(0.98, 0.28, 0.30);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = p - i;
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash11(i.x * 127.1 + i.y * 311.7);
    float b = hash11((i.x + 1.0) * 127.1 + i.y * 311.7);
    float c = hash11(i.x * 127.1 + (i.y + 1.0) * 311.7);
    float d = hash11((i.x + 1.0) * 127.1 + (i.y + 1.0) * 311.7);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// Low-frequency wet/dry modulation at a droplet centre, 0..1. High contrast:
// dry regions + sparse regions + small clusters. Synced 1:1 with
// droplet_stats.cluster_mask.
float clusterMask(vec2 centre) {
    float n = 0.52 * vnoise(centre * 0.0038)
            + 0.30 * vnoise(centre * 0.0105 + vec2(37.2, 91.5))
            + 0.18 * vnoise(centre * 0.0240 + vec2(11.7, 45.3));
    float t = clamp((n - 0.28) / 0.44, 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}

// Per-droplet aspect (height/width). Synced with droplet_stats._aspect.
// medium may stretch slightly vertically; all stay near-round (no blobs).
float aspectOf(int layer, float seed) {
    if (layer == 0) return 0.92 + seed * 0.16;  // 0.92 - 1.08
    if (layer == 1) return 0.88 + seed * 0.24;  // 0.88 - 1.12
    if (layer == 2) return 0.94 + seed * 0.32;  // 0.94 - 1.26
    return 0.95 + seed * 0.20;                  // 0.95 - 1.15
}

void main() {
    vec2 fragPx = qt_TexCoord0 * resolution;
    vec2 baseUv = qt_TexCoord0;

    vec2 refractOffset = vec2(0.0);
    float highlight = 0.0;
    float caustic = 0.0;
    float rimShade = 0.0;
    float innerLift = 0.0;

    float density = u_density;
    bool debug = u_debug > 0.5;
    if (debug) density = 1.0; // full field = complete diameter proof

    vec2 lightDir = normalize(vec2(0.55, -0.72)); // upper-left key light

    vec3 debugRing = vec3(0.0);
    float debugRingA = 0.0;
    vec3 debugDot = vec3(0.0);
    float debugDotA = 0.0;

    for (int layer = 0; layer < 4; ++layer) {
        float cell = GRID[layer];
        float layerDens = density * DENS[layer];
        vec2 cellPx = vec2(cell);
        vec2 cellIdx = floor(fragPx / cellPx);

        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                vec2 idx = cellIdx + vec2(float(dx), float(dy));
                float h = hash11(idx.x * 127.1 + idx.y * 311.7 + float(layer) * 57.31);
                if (h > layerDens) continue; // fast reject (mask <= 1)

                vec2 rnd = hash21(h * 913.7 + float(layer) * 57.31);
                vec2 centre = cellPx * (idx + vec2(0.5) + (rnd - 0.5) * 0.5);

                // diameter in px (quota enforced; always < 30 absolute cap)
                float diameter = mix(D_MIN[layer], D_MAX[layer], hash11(h * 53.1));
                float radius = diameter * 0.5;

                // presence: hash gate x low-frequency wet/dry clustering
                // (dry regions / sparse regions / small clusters — synced
                // with droplet_stats.cluster_mask) x importance mask
                // (low-density protection over critical UI content).
                // Footprint-aware: the mask is pre-dilated in QML (values
                // +28px, text/chip +20px — beyond max droplet influence
                // ~14.4px), AND here we take the minimum factor over the
                // droplet footprint (centre + 4 cardinal offsets) so a
                // droplet whose body would touch protected content is
                // rejected even if its centre sits just outside.
                // PRESENCE only — the frozen optics are untouched.
                vec2 mPx = centre / resolution;
                vec2 mOff = (radius * 1.1) / resolution;
                float maskF = texture(u_mask, mPx).r;
                maskF = min(maskF, texture(u_mask, mPx + vec2( mOff.x, 0.0)).r);
                maskF = min(maskF, texture(u_mask, mPx + vec2(-mOff.x, 0.0)).r);
                maskF = min(maskF, texture(u_mask, mPx + vec2(0.0,  mOff.y)).r);
                maskF = min(maskF, texture(u_mask, mPx + vec2(0.0, -mOff.y)).r);
                if (h > layerDens * clusterMask(centre) * maskF) continue;

                // slight shape variation: per-droplet aspect (height/width)
                // + very restrained boundary wobble (no metaball/blob look)
                float aspect = aspectOf(layer, hash11(h * 191.3 + float(layer) * 13.7));
                float phase = hash11(h * 77.7) * 6.2831;

                vec2 delta = fragPx - centre;
                delta.y /= aspect;

                // static silhouette extras (draw only; counts/stats unchanged):
                if (layer == 2) {
                    // medium: mild vertical gravity stretch
                    delta.y *= 0.96;
                } else if (layer == 3) {
                    // large: teardrop-like asymmetry — round bottom, tapered top
                    delta.y *= mix(0.90, 1.12, smoothstep(-radius, radius, delta.y));
                }
                float dist = length(delta);

                if (debug) {
                    // bounding ring just outside the nominal droplet edge +
                    // centre dot. Every smoothstep strictly increasing.
                    float ring = smoothstep(radius + 1.0, radius + 1.8, dist)
                               * (1.0 - smoothstep(radius + 2.6, radius + 3.4, dist));
                    float dotA = 1.0 - smoothstep(1.1, 1.9, dist);
                    vec3 col = layerDebugColor(layer);
                    if (ring > debugRingA) { debugRingA = ring; debugRing = col; }
                    if (dotA > debugDotA)  { debugDotA = dotA;  debugDot = col; }
                    continue; // debug pass draws marks only
                }

                float angle = atan(delta.y, delta.x);
                float rEff = radius * (1.0
                    + 0.040 * cos(2.0 * angle + phase)
                    + 0.022 * cos(3.0 * angle + phase * 1.7));

                // lens influence ~ physical footprint
                float rad = dist / rEff;
                if (rad >= 1.15) continue;
                vec2 dir = (dist > 0.001) ? delta / dist : vec2(0.0, 1.0);

                // ---- #1 convex water-lens refraction ------------------------
                // Physically-inspired radial normal from a hemisphere profile:
                //   p = local / rEff (aspect/gravity already folded into
                //   delta), z = sqrt(1 - p.p), n = normalize(vec3(p, z)).
                // The normal drives the UV bend, so the distortion varies
                // smoothly across the lens and fades to zero at the boundary.
                vec2 p = delta / rEff;
                float rr = clamp(dot(p, p), 0.0, 1.0);
                float z = sqrt(1.0 - rr);
                vec3 n = normalize(vec3(p, z));
                float edgeFade = 1.0 - smoothstep(0.80, 1.0, rad);
                refractOffset += -n.xy * (LENS_PX[layer] * edgeFade * u_quality);
                innerLift += 1.0 - smoothstep(0.0, 1.0, rad);

                // ---- #2 tiny glint + very weak short arc --------------------
                // one small elongated glint on the key-light side (upper-left);
                // for micro it reads as a single bright pixel impression
                vec2 toGlint = lightDir * (rEff * 0.55) - delta;
                float sigma = max(0.55, rEff * 0.16);
                float t = dot(toGlint, lightDir) / (sigma * 1.9);
                float s = dot(toGlint, vec2(-lightDir.y, lightDir.x)) / (sigma * 0.8);
                highlight += exp(-2.5 * (t * t + s * s)) * GLINT_A[layer];
                float ring = smoothstep(rEff * 0.86, rEff * 0.99, dist)
                           * (1.0 - smoothstep(rEff * 0.99, rEff * 1.06, dist));
                float arcSpec = smoothstep(0.55, 0.92, dot(dir, lightDir));
                highlight += ring * arcSpec * 0.35;

                // ---- #3 subtle dark opposite edge (contact shadow) ----------
                rimShade += ring * smoothstep(0.35, 0.85, dot(dir, -lightDir));

                // ---- #6 internal caustic (medium/large only, dim) -----------
                if (layer >= 2) {
                    vec2 toCaus = -lightDir * (rEff * 0.58) - delta;
                    float cs = rEff * 0.30;
                    caustic += exp(-2.0 * dot(toCaus, toCaus) / (cs * cs)) * 0.5;
                }
            }
        }
    }

    // clamp total UV displacement (no fisheye / bubble distortion)
    float offMag = length(refractOffset);
    if (offMag > 10.0) refractOffset *= 10.0 / offMag;

    vec2 refractedUv = baseUv + refractOffset / resolution;
    refractedUv = clamp(refractedUv, vec2(0.002), vec2(0.998));
    vec3 color = texture(source, refractedUv).rgb;

    // hierarchy: #1 refraction (above) · #2 glint · #3 dark edge · #4 body
    color *= 1.0 + innerLift * 0.012;
    color += caustic * vec3(0.94, 0.97, 1.0) * 0.14;
    color -= rimShade * vec3(0.30, 0.33, 0.38) * 0.12;
    color += highlight * vec3(0.90, 0.95, 1.0) * 0.40;

    float grain = hash11(fragPx.x * 12.9 + fragPx.y * 78.2) - 0.5;
    color += grain * 0.005;

    if (debug) {
        color *= 0.30; // dim the scene so the diameter proof reads clearly
        color = mix(color, debugRing, debugRingA * 0.95);
        color = mix(color, debugDot, debugDotA * 0.95);
    }

    fragColor = vec4(color, 1.0);
}
