#version 440

// Overview shell — environment readability attenuation (NOT the rain shader;
// the rain material stays frozen). Last step of the environment layer:
//   base sky/city -> light streaks -> warm/cool highlights -> THIS
// Attenuates high-brightness environment features behind critical financial
// content, driven by a feathered readabilityMask (R channel = protection
// strength 0..1):
//   bright highlights (moon/halo/glows):  up to 90% reduction
//   thin vertical streaks / glows:        strongly reduced
//   base city/background:                 only ~10% dim at full mask
// Soft by construction: attenuation is proportional to the feathered mask,
// so no visible rectangles or halos. Runs BEFORE the glass panels and UI
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

void main() {
    vec3 c = texture(source, qt_TexCoord0).rgb;
    float m = texture(u_mask, qt_TexCoord0).r;   // feathered protection 0..1

    float luma = dot(c, vec3(0.2126, 0.7152, 0.0722));
    // highlight component: 0 on the dark city base, ->1 on bright features
    float bright = smoothstep(0.06, 0.25, luma);

    // full mask: bright highlights -90%, base city -10% (5-12% range)
    float atten = m * (0.10 + 0.80 * bright);
    fragColor = vec4(c * (1.0 - atten), 1.0);
}
