#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float blurRadius;
    vec2 sourceTextureSize;
    vec2 direction;
};
layout(binding = 1) uniform sampler2D source;

void main()
{
    // Binomial weights approximate a smooth Gaussian. The nine closely
    // spaced samples are separable; the caller performs H then V passes.
    vec2 stepUv = direction * blurRadius * 0.25
        / max(sourceTextureSize, vec2(1.0));
    const float weights[9] = float[9](1.0, 8.0, 28.0, 56.0, 70.0,
                                      56.0, 28.0, 8.0, 1.0);
    vec4 color = vec4(0.0);
    for (int i = 0; i < 9; ++i)
        color += texture(source, qt_TexCoord0 + float(i - 4) * stepUv)
            * weights[i] / 256.0;
    fragColor = color * qt_Opacity;
}
