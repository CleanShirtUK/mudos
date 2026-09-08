#version 440

layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D source;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float cornerRadius;
    vec2 artworkSize;
    float borderAlpha;
    int diagnosticMode;
};

layout(location = 0) in vec2 qt_TexCoord0;

void main()
{
    vec2 q = abs(qt_TexCoord0 - vec2(0.5)) - vec2(0.5 - cornerRadius);
    float distance = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - cornerRadius;
    float antialiasWidth = max(fwidth(distance), 0.0005);
    float alpha = 1.0 - smoothstep(-antialiasWidth, antialiasWidth, distance);
    if (diagnosticMode == 1) {
        fragColor = vec4(vec3(alpha), alpha) * qt_Opacity;
        return;
    }
    vec4 artwork = texture(source, qt_TexCoord0) * alpha;
    float pixelWidth = 1.0 / min(artworkSize.x, artworkSize.y);
    float border = smoothstep(-pixelWidth, 0.0, distance)
                 * (1.0 - smoothstep(0.0, antialiasWidth, distance));
    artwork.rgb += vec3(border * borderAlpha);
    artwork.a = max(artwork.a, border * borderAlpha);
    fragColor = artwork * qt_Opacity;
}
