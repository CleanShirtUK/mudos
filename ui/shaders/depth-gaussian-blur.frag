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
    // A compact 5x5 separable Gaussian footprint. Sampling a dense grid
    // avoids the visible ghost copies produced by widely separated taps.
    vec2 stepUv = blurRadius * 0.5 / max(sourceTextureSize, vec2(1.0));
    const float weights[5] = float[5](0.06136, 0.24477, 0.38774,
                                      0.24477, 0.06136);
    vec4 color = vec4(0.0);
    for (int y = 0; y < 5; ++y) {
        for (int x = 0; x < 5; ++x) {
            vec2 offset = vec2(float(x - 2), float(y - 2)) * stepUv;
            color += texture(source, qt_TexCoord0 + offset)
                * weights[x] * weights[y];
        }
    }
    fragColor = color * qt_Opacity;
}
