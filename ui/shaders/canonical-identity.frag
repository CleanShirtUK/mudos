#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_sceneOrigin;
    vec2 u_sceneSize;
    vec2 u_canonicalSize;
};
layout(binding = 1) uniform sampler2D source;

void main()
{
    vec2 scenePosition = u_sceneOrigin + qt_TexCoord0 * u_sceneSize;
    vec2 canonicalUv = scenePosition / u_canonicalSize;
    fragColor = texture(source, canonicalUv) * qt_Opacity;
}
