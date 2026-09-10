#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_captureSize;
    vec2 u_surfaceSize;
    vec2 u_visibleOrigin;
    vec2 u_captureOrigin;
    float u_padding;
    float u_time;
    float u_iorRed;
    float u_iorGreen;
    float u_iorBlue;
    float u_depth;
    float u_refractionPixels;
    float u_dispersionPixels;
    float u_blurRadiusPixels;
    float u_transmission;
    float u_attenuation;
    float u_edgeReflection;
    float u_specularStrength;
    float u_bevelWidthPixels;
    float u_focus;
    float u_cornerRadius;
    int u_diagnostic;
    vec4 u_tint;
};
layout(binding = 1) uniform sampler2D source;

float roundedDistance(vec2 uv, vec2 size, float radius)
{
    vec2 q = abs(uv * size - size * 0.5) - (size * 0.5 - vec2(radius));
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

vec2 roundedNormal(vec2 uv, vec2 size, float radius)
{
    float stepPixels = 1.0;
    vec2 stepUv = stepPixels / size;
    vec2 gradient = vec2(
        roundedDistance(uv + vec2(stepUv.x, 0.0), size, radius)
            - roundedDistance(uv - vec2(stepUv.x, 0.0), size, radius),
        roundedDistance(uv + vec2(0.0, stepUv.y), size, radius)
            - roundedDistance(uv - vec2(0.0, stepUv.y), size, radius));
    return length(gradient) > 0.0001 ? normalize(gradient) : vec2(0.0);
}

vec4 sampleDiffused(vec2 uv, vec2 pixelStep)
{
    vec2 x = vec2(pixelStep.x, 0.0);
    vec2 y = vec2(0.0, pixelStep.y);
    return (texture(source, uv) * 4.0
        + texture(source, uv + x) * 2.0
        + texture(source, uv - x) * 2.0
        + texture(source, uv + y) * 2.0
        + texture(source, uv - y) * 2.0) / 12.0;
}

vec2 refractedUv(vec2 baseUv, vec2 normal, float ior, float field, float directionSign)
{
    vec3 ray = refract(vec3(0.0, 0.0, -1.0),
                       normalize(vec3(normal * u_depth * field, 1.0)), 1.0 / max(ior, 1.001));
    vec2 direction = length(ray.xy) > 0.0001 ? normalize(ray.xy) : vec2(0.0);
    vec2 displacement = direction * u_refractionPixels * field * directionSign / u_captureSize;
    return baseUv + displacement;
}

void main()
{
    vec2 uv = qt_TexCoord0;
    float distance = roundedDistance(uv, u_surfaceSize, u_cornerRadius);
    float mask = 1.0 - smoothstep(0.0, 1.5, distance);
    float inside = max(0.0, -distance);
    float bevel = 1.0 - smoothstep(0.0, max(0.1, u_bevelWidthPixels), inside);
    float field = mix(0.08, 1.0, bevel);
    vec2 normal = roundedNormal(uv, u_surfaceSize, u_cornerRadius);
    vec2 baseUv = (u_visibleOrigin - u_captureOrigin + uv * u_surfaceSize) / u_captureSize;

    if (u_diagnostic == 6) {
        fragColor = texture(source, baseUv);
        return;
    }

    vec2 redUv = refractedUv(baseUv, normal, u_iorRed, field, 1.0);
    vec2 greenUv = refractedUv(baseUv, normal, u_iorGreen, field, 1.0);
    vec2 blueUv = refractedUv(baseUv, normal, u_iorBlue, field, 1.0);
    vec2 dispersion = normal * u_dispersionPixels * field / u_captureSize;
    redUv += dispersion;
    blueUv -= dispersion;

    if (u_diagnostic == 1)
        fragColor = vec4(vec3(clamp(-distance / 48.0 + 0.5, 0.0, 1.0)), 1.0);
    else if (u_diagnostic == 2)
        fragColor = vec4(normal * 0.5 + 0.5, 0.0, 1.0);
    else if (u_diagnostic == 3)
        fragColor = vec4(vec3(field), 1.0);
    else if (u_diagnostic == 4)
        fragColor = vec4(baseUv, 0.0, 1.0);
    else if (u_diagnostic == 5)
        fragColor = vec4(greenUv, 0.0, 1.0);
    else {
        vec4 red = sampleDiffused(redUv, vec2(u_blurRadiusPixels) / u_captureSize);
        vec4 green = sampleDiffused(greenUv, vec2(u_blurRadiusPixels) / u_captureSize);
        vec4 blue = sampleDiffused(blueUv, vec2(u_blurRadiusPixels) / u_captureSize);
        vec3 color = vec3(red.r, green.g, blue.b) * u_attenuation;
        color = mix(color, u_tint.rgb, u_tint.a);

        float fresnel = pow(clamp(length(normal) * field, 0.0, 1.0), 3.0);
        float edge = bevel * (u_edgeReflection + u_focus * 0.02);
        color += vec3(0.35, 0.42, 0.72) * edge;
        color += vec3(0.72, 0.82, 1.0) * fresnel * u_specularStrength;
        fragColor = vec4(color, u_transmission + u_focus * 0.04) * qt_Opacity * mask;
    }
}
