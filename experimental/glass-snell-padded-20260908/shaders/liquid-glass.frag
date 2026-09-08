#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_origin;
    vec2 u_captureSize;
    vec2 u_size;
    float u_padding;
    float u_time;
    float u_refraction;
    float u_chromatic;
    float u_ior;
    float u_snellMagnitudePixels;
    float u_dispersionPixels;
    float u_diffusion;
    float u_focus;
    float u_cornerRadius;
    float u_attenuation;
    float u_edgeHighlight;
    vec4 u_tint;
};
layout(binding = 1) uniform sampler2D source;

float roundedDistance(vec2 uv, vec2 size, float radius)
{
    vec2 p = uv * size;
    vec2 q = abs(p - size * 0.5) - (size * 0.5 - vec2(radius));
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

void main()
{
    vec2 uv = qt_TexCoord0;
    vec2 size = max(u_size, vec2(1.0));
    float distance = roundedDistance(uv, size, u_cornerRadius);
    float mask = 1.0 - smoothstep(0.0, 1.5, distance);
    float insideDistance = max(0.0, -distance);
    float interiorField = smoothstep(0.0, 96.0, insideDistance);
    float edgeField = smoothstep(0.0, 6.0, insideDistance)
                    * (1.0 - smoothstep(6.0, 96.0, insideDistance));
    // Keep a shallow lens through the body, but fade the optical volume at its boundary.
    float lens = 0.08 * interiorField + 0.92 * edgeField;
    float gradientStep = 1.0 / max(size.x, size.y);
    vec2 normal = vec2(
        roundedDistance(uv + vec2(gradientStep, 0.0), size, u_cornerRadius)
            - roundedDistance(uv - vec2(gradientStep, 0.0), size, u_cornerRadius),
        roundedDistance(uv + vec2(0.0, gradientStep), size, u_cornerRadius)
            - roundedDistance(uv - vec2(0.0, gradientStep), size, u_cornerRadius));
    normal = length(normal) > 0.0001 ? normalize(normal) : vec2(0.0);
    vec2 baseUv = (u_padding + uv * u_size) / u_captureSize;
    vec3 glassNormal = normalize(vec3(normal * (0.35 + 0.65 * lens), 1.0));
    vec3 viewRay = vec3(0.0, 0.0, -1.0);
    vec3 refractedRay = refract(viewRay, glassNormal, 1.0 / max(u_ior, 1.001));
    vec2 refractedDirection = length(refractedRay.xy) > 0.0001
        ? normalize(refractedRay.xy) : vec2(0.0);
    float wave = 0.72 + 0.28 * sin(baseUv.x * 15.0 + baseUv.y * 9.0 + u_time * 0.35);
    float magnitudePixels = u_snellMagnitudePixels * u_refraction * lens * wave;
    vec2 displacement = refractedDirection * magnitudePixels / max(u_captureSize, vec2(1.0));
    vec2 refractedUv = clamp(baseUv + displacement, vec2(0.002), vec2(0.998));
    float dispersionMagnitude = u_dispersionPixels * u_chromatic * lens;
    vec2 dispersion = refractedDirection * dispersionMagnitude / max(u_captureSize, vec2(1.0));
    vec2 redUv = clamp(refractedUv + dispersion, vec2(0.002), vec2(0.998));
    vec2 blueUv = clamp(refractedUv - dispersion, vec2(0.002), vec2(0.998));

    vec4 red = texture(source, redUv);
    vec4 center = texture(source, refractedUv);
    vec4 blue = texture(source, blueUv);
    vec4 diffuse = (
        texture(source, clamp(refractedUv + vec2(u_diffusion, 0.0), vec2(0.002), vec2(0.998)))
        + texture(source, clamp(refractedUv - vec2(u_diffusion, 0.0), vec2(0.002), vec2(0.998)))
        + texture(source, clamp(refractedUv + vec2(0.0, u_diffusion), vec2(0.002), vec2(0.998)))
        + texture(source, clamp(refractedUv - vec2(0.0, u_diffusion), vec2(0.002), vec2(0.998)))) * 0.25;

    vec3 chromatic = vec3(red.r, center.g, blue.b);
    vec3 color = mix(chromatic, diffuse.rgb, 0.24);
    color *= u_attenuation;
    color = mix(color, u_tint.rgb, u_tint.a);
    color += vec3(0.34, 0.40, 0.72) * pow(lens, 2.0) * u_edgeHighlight * (1.0 + u_focus);

    fragColor = vec4(color, 0.78 + u_focus * 0.08) * qt_Opacity * mask;
}
