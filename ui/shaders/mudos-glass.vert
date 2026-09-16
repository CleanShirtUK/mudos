#version 440
layout(location = 0) in vec2 vertex;
layout(location = 1) in vec2 texcoord;
layout(location = 0) out vec2 qt_TexCoord0;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_sceneOrigin;
    vec2 u_sceneSize;
    vec2 u_canonicalSize;
    float u_ior;
    float u_depth;
    float u_refractionPixels;
    float u_cornerRadius;
    float u_dispersionIor;
    float u_diffusionPixels;
    float u_transmission;
    float u_bevelWidthPx;
    float u_bulgeStrength;
    float u_sceneLightStrength;
    float u_sceneLightPixels;
    float u_edgeLightStrength;
    vec2 u_edgeLightDirection;
    float u_transparentOutsideMask;
    int u_diagnostic;
    vec4 u_textureSubRect;
};
void main()
{
    qt_TexCoord0 = u_textureSubRect.xy + texcoord * u_textureSubRect.zw;
    gl_Position = qt_Matrix * vec4(vertex, 0.0, 1.0);
}
