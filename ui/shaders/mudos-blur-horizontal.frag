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
    vec2 stepUv = vec2(blurRadius / max(sourceTextureSize.x, 1.0), 0.0);
    vec4 color = vec4(0.0);
    for (int x = 0; x < 5; ++x)
        color += texture(source, qt_TexCoord0 + stepUv * float(x - 2)) * weights[x];
    fragColor = color * qt_Opacity;
}
