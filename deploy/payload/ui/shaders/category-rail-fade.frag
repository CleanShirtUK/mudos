#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(binding = 1) uniform sampler2D source;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float fadeWidth;
    vec2 viewportSize;
};

void main()
{
    fragColor = texture(source, qt_TexCoord0);
    float fadeStart = 1.0 - fadeWidth / max(viewportSize.x, 1.0);
    float edgeFade = 1.0 - smoothstep(fadeStart, 1.0, qt_TexCoord0.x);
    fragColor.a *= edgeFade * qt_Opacity;
}
