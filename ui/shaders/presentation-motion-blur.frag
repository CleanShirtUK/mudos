#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 blurVector;
    vec2 sourceTextureSize;
};
layout(binding = 1) uniform sampler2D source;

void main()
{
    // Seven symmetric samples around a point shifted half a blur distance
    // behind the moving surface. This retains a compact symmetric kernel while
    // making the signed velocity visually directional.
    vec2 stepUv = blurVector / max(sourceTextureSize, vec2(1.0));
    vec2 blurCenter = qt_TexCoord0 - stepUv * 0.5;
    vec4 color = texture(source, blurCenter) * 0.30;
    color += texture(source, blurCenter - stepUv * 0.333333) * 0.18;
    color += texture(source, blurCenter + stepUv * 0.333333) * 0.18;
    color += texture(source, blurCenter - stepUv * 0.666667) * 0.12;
    color += texture(source, blurCenter + stepUv * 0.666667) * 0.12;
    color += texture(source, blurCenter - stepUv) * 0.05;
    color += texture(source, blurCenter + stepUv) * 0.05;
    fragColor = color * qt_Opacity;
}
