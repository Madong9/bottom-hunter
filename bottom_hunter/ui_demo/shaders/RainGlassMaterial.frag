#version 440

// Crystal Clear Rain Glass — screen-space water droplets on transparent glass.
//
// The droplets are NOT 3D spheres / orbs / bubbles. They are flat,
// near-transparent lens patches on the glass surface that:
//   * densely fill the field with micro/small drops (70%+ under ~9px)
//   * refract the underlying UI (lens magnification / local UV displacement)
//   * show a thin specular edge + a very weak environment reflection
//   * never tint the body cyan or darken the scene
//
// Distribution (§5.1):
//   micro  1.5–4 px   (dense, static)          grid ~12px
//   small  4–9 px     (~18%)                   grid ~34px
//   medium 9–18 px    (few)                    grid ~110px
//   large  18–30 px   (rare, may slide)        grid ~320px
//   hard cap ~32px
//
// Inputs (ShaderEffect):
//   source         — the UI/scene underneath (background capture)
//   resolution     — item px size
//   u_time         — seconds (slow; droplets slide at 2–6 px/s max)
//   u_parallax     — vec2 px offset (mouse parallax, ≤4px)
//   u_quality      — 1.0 high / 0.75 balanced / 0.0 low (kills slide)
//   u_density      — 0..1 global density
//   u_exclude      — vec4(x, y, w, h) importance zone, density scaled down

layout(binding = 1) uniform sampler2D source;

layout(std140, binding = 0) uniform UboBlock {
    vec2 resolution;
    float u_time;
    vec2 u_parallax;
    float u_quality;
    float u_density;
    vec4 u_exclude;
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

// ---- importance / exclusion zone ------------------------------------------
// Inside the excluded rect (chart body / tables / prices) droplet density and
// slide are scaled down so critical financial data stays legible (§8).
float exclusionScale(vec2 p) {
    vec4 r = ubuf.u_exclude;
    if (r.z <= 0.0 || r.w <= 0.0) return 1.0;
    vec2 rel = (p - r.xy) / r.zw;
    if (rel.x >= 0.0 && rel.x <= 1.0 && rel.y >= 0.0 && rel.y <= 1.0) {
        // soft edge falloff
        float edge = min(rel.x, min(rel.y, min(1.0 - rel.x, 1.0 - rel.y)));
        float soft = smoothstep(0.0, 0.08, edge);
        return mix(0.18, 1.0, soft);
    }
    return 1.0;
}

void main() {
    vec2 fragPx = qt_TexCoord0 * ubuf.resolution;
    vec2 parallaxPx = ubuf.u_parallax * ubuf.u_quality;
    vec2 baseUv = qt_TexCoord0 + parallaxPx / ubuf.resolution;

    vec2 refractOffset = vec2(0.0);
    float highlight = 0.0;
    float innerLight = 0.0;

    float zone = exclusionScale(fragPx);
    float density = ubuf.u_density * zone;

    // 4 layers, micro→large. Each searches 3x3 neighbouring cells -> bounded.
    // Layer radii (px): micro ~1.5-4, small ~4-9, medium ~9-18, large ~18-30.
    const float GRID[4] = float[4](12.0, 34.0, 110.0, 320.0);
    const float R_MIN[4] = float[4](1.5, 4.0, 9.0, 18.0);
    const float R_MAX[4] = float[4](4.0, 9.0, 18.0, 30.0);
    const float DENS[4] = float[4](1.00, 0.18, 0.06, 0.015);

    for (int layer = 0; layer < 4; ++layer) {
        float cell = GRID[layer];
        float layerDensity = density * DENS[layer];
        float slideChance = layer < 2 ? 0.0 : (layer == 2 ? 0.05 : 0.10);

        vec2 cellPx = vec2(cell);
        vec2 cellIdx = floor(fragPx / cellPx);
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                vec2 idx = cellIdx + vec2(float(dx), float(dy));
                float cellHash = hash11(idx.x * 127.1 + idx.y * 311.7 + float(layer) * 57.31);
                if (cellHash > layerDensity) continue;

                vec2 rnd = hash21(cellHash * 913.7 + float(layer) * 57.31);
                vec2 centre = cellPx * (idx + vec2(0.5) + (rnd - 0.5) * 0.6);

                // slow slide for medium/large only (2-6 px/s)
                float slide = 0.0;
                float slideSeed = hash11(cellHash * 417.3);
                if (layer >= 2 && slideSeed < slideChance * ubuf.u_quality) {
                    float speed = 2.2 + hash11(cellHash * 71.3) * 3.5;
                    float travel = cell * 1.5;
                    float phase = fract(ubuf.u_time / (travel / speed) + hash11(cellHash * 19.7));
                    slide = phase * travel;
                }
                vec2 pos = centre + vec2(0.0, slide);

                float radius = mix(R_MIN[layer], R_MAX[layer], hash11(cellHash * 53.1));
                // gravity stretch: slight vertical elongation for larger drops
                float stretch = 1.0 + (layer >= 2 ? 0.10 + hash11(cellHash * 97.9) * 0.18 : 0.0);
                vec2 delta = fragPx - pos;
                delta.y /= stretch;
                float dist = length(delta);

                float influence = radius * 1.6;
                if (dist < influence) {
                    // lens profile: full effect inside, soft falloff at rim
                    float inside = 1.0 - smoothstep(radius * 0.5, radius, dist);
                    // derive pseudo-normal from radial direction (normal illusion)
                    vec2 dir = (dist > 0.001) ? delta / dist : vec2(0.0, 1.0);
                    // refraction: pull UV toward centre = magnification (transparent!)
                    float mag = inside * radius * 0.22;
                    refractOffset += -dir * mag * ubuf.u_quality;
                    // inner light: extremely weak, near-neutral (not cyan)
                    innerLight += inside * 0.10;

                    // thin specular ring near the edge + directional highlight
                    float ring = smoothstep(radius * 0.78, radius * 0.98, dist)
                               - smoothstep(radius * 0.98, radius, dist);
                    vec2 lightDir = normalize(vec2(0.55, -0.72));
                    highlight += ring * (0.5 + 0.5 * dot(dir, lightDir)) * 0.7;
                }
            }
        }
    }

    // ---- composite: transparent droplets over the underlying scene ---------
    vec2 refractedUv = baseUv + refractOffset / ubuf.resolution;
    refractedUv = clamp(refractedUv, vec2(0.002), vec2(0.998));
    vec3 color = texture(source, refractedUv).rgb;

    // near-transparent glass veil: neutral, very light (NOT dark/carbon)
    // 只做极轻的环境反射与轻微提亮，让玻璃“无色透明”。
    color = mix(color, color * 1.03 + vec3(0.015, 0.018, 0.020), 0.35);
    color += innerLight * vec3(0.95, 0.98, 1.0) * 0.18;   // faint inner light
    color += highlight * vec3(0.85, 0.92, 0.98);          // thin specular edge

    // subtle grain (anti-banding)
    float grain = hash11(fragPx.x * 12.9 + fragPx.y * 78.2) - 0.5;
    color += grain * 0.006;

    fragColor = vec4(color, 1.0);
}
