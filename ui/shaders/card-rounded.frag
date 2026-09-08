#version 440

layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D source;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float cornerRadius;
};

layout(location = 0) in vec2 qt_TexCoord0;

void main()
{
    vec2 q = abs(qt_TexCoord0 - vec2(0.5)) - vec2(0.5 - cornerRadius);
    float distance = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - cornerRadius;
    float alpha = 1.0 - smoothstep(0.0, 0.002, distance);
    fragColor = texture(source, qt_TexCoord0) * alpha * qt_Opacity;
}
