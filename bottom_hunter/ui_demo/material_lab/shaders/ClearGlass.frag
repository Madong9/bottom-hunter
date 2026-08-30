#version 440

// CrystalGlassMaterialLab — layer 2: CLEAR, colorless optical glass pane.
//
// What the pane adds over the environment (all subtle, nothing dark/smoked):
//   * very subtle backdrop blur (~0.75 px; city stays crisp — NOT soft-focus)
//   * extremely weak large-scale refraction (no wobble, no showy distortion)
//   * near-white neutral film (tint #FFFFFF, alpha ~0.018) — NOT dark glass
//   * slight saturation lift (1.05 - 1.10)
//   * fine edge highlight: thin bright line + soft inner bevel
//   * faint top-left ambient reflection
//   * very subtle grain (anti-banding)
// Output is opaque: it replaces the captured environment visually.
// All smoothstep calls use strictly increasing edges (edge0 < edge1).
//
// Inputs (ShaderEffect):
//   source      — the environment background capture
//   resolution  — output size in px (logical; lab runs at DPR 1)
//   u_blur      — backdrop blur step, px (~0.75)
//   u_refract   — large-scale UV wobble amplitude, px (~0.35)
//   u_tint      — near-white film alpha (~0.018)
//   u_sat       — saturation multiplier (~1.06)

layout(binding = 1) uniform sampler2D source;

// Fragment-only ShaderEffect contract: the built-in vertex shader shares this
// buffer, so qt_Matrix (offset 0) and qt_Opacity (offset 64) MUST come first;
// custom uniforms follow. Block name must match the built-in one.
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 resolution;
    float u_blur;
    float u_refract;
    float u_tint;
    float u_sat;
};

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

void main() {
    vec2 fragPx = qt_TexCoord0 * resolution;
    vec2 px = 1.0 / resolution;

    // --- very weak large-scale refraction (low-frequency, static) ------------
    vec2 uv = qt_TexCoord0;
    uv += vec2(
        sin(uv.y * 6.1 + 1.7) * cos(uv.x * 4.3 + 0.4),
        cos(uv.x * 5.3 + 2.1) * sin(uv.y * 3.7 + 1.1)
    ) * (u_refract * px);

    // --- subtle backdrop blur: 3x3 Gaussian (weights sum to 1.0) -------------
    // [0.025 0.100 0.025]  step = u_blur px
    // [0.100 0.400 0.100]
    // [0.025 0.100 0.025]
    float r = u_blur;
    vec3 col = vec3(0.0);
    col += texture(source, uv + vec2(-r, -r) * px).rgb * 0.025;
    col += texture(source, uv + vec2( 0., -r) * px).rgb * 0.100;
    col += texture(source, uv + vec2( r, -r) * px).rgb * 0.025;
    col += texture(source, uv + vec2(-r,  0.) * px).rgb * 0.100;
    col += texture(source, uv).rgb                       * 0.400;
    col += texture(source, uv + vec2( r,  0.) * px).rgb * 0.100;
    col += texture(source, uv + vec2(-r,  r) * px).rgb * 0.025;
    col += texture(source, uv + vec2( 0.,  r) * px).rgb * 0.100;
    col += texture(source, uv + vec2( r,  r) * px).rgb * 0.025;

    // --- saturation lift (luminance-preserving) -------------------------------
    float luma = dot(col, vec3(0.2126, 0.7152, 0.0722));
    col = mix(vec3(luma), col, u_sat);

    // --- near-white film: colorless, NEVER dark/smoked ------------------------
    col = mix(col, vec3(0.94, 0.97, 1.0), u_tint);

    // --- faint top-left ambient reflection ------------------------------------
    float ambient = 1.0 - smoothstep(0.25, 1.0, qt_TexCoord0.x * 0.6 + qt_TexCoord0.y * 0.8);
    col += ambient * vec3(0.014, 0.017, 0.020);

    // --- edge highlight: thin bright line + soft inner bevel -------------------
    float bx = min(fragPx.x, resolution.x - fragPx.x);
    float by = min(fragPx.y, resolution.y - fragPx.y);
    float b = min(bx, by);
    float edgeLine = 1.0 - smoothstep(0.5, 1.5, b);
    float bevel = (1.0 - smoothstep(0.0, 8.0, b)) * (1.0 - edgeLine);
    col += edgeLine * vec3(0.85, 0.92, 1.0) * 0.16;
    col += bevel * vec3(0.80, 0.88, 0.98) * 0.05;

    // --- grain (anti-banding) ---------------------------------------------------
    float grain = hash11(fragPx.x * 12.9 + fragPx.y * 78.2 + 7.7) - 0.5;
    col += grain * 0.004;

    fragColor = vec4(col, 1.0);
}
