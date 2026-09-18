#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float blurRadius;
    vec2 sourceTextureSize;
};
layout(binding = 1) uniform sampler2D source;

void main()
{
    const float weights[5] = float[5](0.06136, 0.24477, 0.38774,
                                      0.24477, 0.06136);
    vec2 stepUv = vec2(0.0, blurRadius / max(sourceTextureSize.y, 1.0));
    vec4 color = vec4(0.0);
    for (int y = 0; y < 5; ++y)
        color += texture(source, qt_TexCoord0 + stepUv * float(y - 2)) * weights[y];
    fragColor = color * qt_Opacity;
}
