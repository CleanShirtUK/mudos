#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float blurRadius;
    float cornerRadius;
    vec2 sourceTextureSize;
};
layout(binding = 1) uniform sampler2D source;

void main()
{
    vec2 pixel = blurRadius / max(sourceTextureSize, vec2(1.0));
    vec4 color = texture(source, qt_TexCoord0) * 0.227027;
    float nearWeight = 0.158108;
    float farWeight = 0.035135;
    color += texture(source, qt_TexCoord0 + vec2(pixel.x * 1.384615, 0.0)) * nearWeight;
    color += texture(source, qt_TexCoord0 - vec2(pixel.x * 1.384615, 0.0)) * nearWeight;
    color += texture(source, qt_TexCoord0 + vec2(0.0, pixel.y * 1.384615)) * nearWeight;
    color += texture(source, qt_TexCoord0 - vec2(0.0, pixel.y * 1.384615)) * nearWeight;
    color += texture(source, qt_TexCoord0 + vec2(pixel.x * 3.230769, 0.0)) * farWeight;
    color += texture(source, qt_TexCoord0 - vec2(pixel.x * 3.230769, 0.0)) * farWeight;
    color += texture(source, qt_TexCoord0 + vec2(0.0, pixel.y * 3.230769)) * farWeight;
    color += texture(source, qt_TexCoord0 - vec2(0.0, pixel.y * 3.230769)) * farWeight;
    float radius = min(cornerRadius, min(sourceTextureSize.x, sourceTextureSize.y) * 0.5);
    vec2 p = qt_TexCoord0 * sourceTextureSize;
    vec2 size = sourceTextureSize;
    vec2 corner = vec2(0.0);
    if (p.x < radius && p.y < radius) corner = vec2(radius, radius);
    else if (p.x > size.x - radius && p.y < radius)
        corner = vec2(size.x - radius, radius);
    else if (p.x < radius && p.y > size.y - radius)
        corner = vec2(radius, size.y - radius);
    else if (p.x > size.x - radius && p.y > size.y - radius)
        corner = vec2(size.x - radius, size.y - radius);
    float mask = radius > 0.0 && corner.x > 0.0
        ? smoothstep(radius + 1.0, radius - 1.0, distance(p, corner)) : 1.0;
    fragColor = color * qt_Opacity * mask;
}
