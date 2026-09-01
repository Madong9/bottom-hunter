#version 440

// Overview shell — environment readability attenuation (NOT the rain shader;
// the rain material stays frozen). Last step of the environment layer:
//   base sky/city -> light streaks -> warm/cool highlights -> THIS
//
// EXCESS-ATTENUATION MODEL (v2, fixes the "black hole" artifact):
//   localBase = darkest wide-ring neighbourhood estimate (rings r=12 / r=34,
//               8 directions each) — the ambient environment level WITHOUT
//               the local light feature
//   excess    = max(source - localBase, 0) — the light feature itself
//   result    = localBase * (1 - 0.10*m) + excess * (1 - 0.90*m)
//
// Inside a readability zone a protected light reads as "this light never
// existed": its excess is removed while the ambient base (sky/city/grain)
// stays — only ~10% dimmed. The final pixel NEVER mixes toward pure black.
// Outside zones (m = 0): result == source, bit-for-bit.
// Soft by construction: attenuation is proportional to the feathered mask;
// no visible rectangles or halos. Runs BEFORE the glass panels and UI
// chrome are composited — it never touches text.
//
// Inputs (ShaderEffect):
//   source      — environment capture (base + streaks + highlights)
//   u_mask      — readabilityMask capture (white feathered zones)

layout(binding = 1) uniform sampler2D source;
layout(binding = 2) uniform sampler2D u_mask;

// Fragment-only ShaderEffect contract: built-in vertex shader shares this
// buffer; qt_Matrix (offset 0) and qt_Opacity (offset 64) MUST come first.
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 resolution;
};

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

// darkest wide-ring neighbourhood estimate: rings r=12 and r=34, 8 directions
// each. r=34 exceeds the largest local light feature radius (~30px), so at
// least one ring always samples the ambient environment.
vec3 localBase(vec2 uv) {
    vec2 px = 1.0 / resolution;
    vec3 mn = vec3(1.0);
    for (int i = 0; i < 8; ++i) {
        float a = 6.2831 * (float(i) + 0.5) / 8.0;
        vec2 d = vec2(cos(a), sin(a));
        mn = min(mn, texture(source, uv + d * 12.0 * px).rgb);
        mn = min(mn, texture(source, uv + d * 34.0 * px).rgb);
    }
    return mn;
}

void main() {
    vec2 uv = qt_TexCoord0;
    vec3 c = texture(source, uv).rgb;
    float m = texture(u_mask, uv).r;   // feathered protection 0..1

    vec3 base = localBase(uv);
    vec3 excess = max(c - base, vec3(0.0));

    // full mask: light feature -90%, ambient base -10% (5-12% range)
    vec3 result = base * (1.0 - 0.10 * m) + excess * (1.0 - 0.90 * m);

    fragColor = vec4(result * qt_Opacity, qt_Opacity);
}
