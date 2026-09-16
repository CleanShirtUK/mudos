#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
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
    vec4 u_textureSubRect;
};
layout(binding = 1) uniform sampler2D source;

float roundedRectangleDistance(vec2 uv, vec2 size, float radius)
{
    vec2 point = uv * size - size * 0.5;
    vec2 halfSize = size * 0.5;
    float safeRadius = min(radius, min(halfSize.x, halfSize.y));
    vec2 q = abs(point) - (halfSize - vec2(safeRadius));
    return length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - safeRadius;
}

float smootherstep(float t)
{
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

float sceneLuminance(vec3 color)
{
    return dot(color, vec3(0.2126, 0.7152, 0.0722));
}

float centralBulgeHeight(vec2 uv, vec2 size, float radius)
{
    float boundaryDistance = roundedRectangleDistance(uv, size, radius);
    float transitionWidth = max(u_bevelWidthPx, 1.0);
    vec2 point = uv * size - size * 0.5;
    vec2 halfSize = size * 0.5;
    vec2 normalized = clamp(abs(point) / halfSize, vec2(0.0), vec2(1.0));
    const float halfPi = 1.57079633;
    // Separable aspect-aware dome: no inscribed ellipse controls the footprint.
    float bulgeShape = cos(normalized.x * halfPi) * cos(normalized.y * halfPi);
    float bulgeFade = smootherstep(clamp(
        (-boundaryDistance - transitionWidth) / transitionWidth, 0.0, 1.0));
    return u_bulgeStrength * bulgeShape * bulgeFade;
}

float surfaceHeight(vec2 uv, vec2 size, float radius)
{
    float boundaryDistance = roundedRectangleDistance(uv, size, radius);
    float transitionWidth = max(u_bevelWidthPx, 1.0);
    float distanceIntoBevel = transitionWidth + boundaryDistance;
    float t = clamp(distanceIntoBevel / transitionWidth, 0.0, 1.0);
    float edgeBevelHeight = smootherstep(t);
    // Fade the broad, aspect-aware bulge out before the accepted edge bevel.
    return edgeBevelHeight + centralBulgeHeight(uv, size, radius);
}

vec2 surfaceGradient(vec2 uv, vec2 size, float radius)
{
    vec2 stepUv = 1.0 / size;
    vec2 gradient = vec2(
        surfaceHeight(uv + vec2(stepUv.x, 0.0), size, radius)
            - surfaceHeight(uv - vec2(stepUv.x, 0.0), size, radius),
        surfaceHeight(uv + vec2(0.0, stepUv.y), size, radius)
            - surfaceHeight(uv - vec2(0.0, stepUv.y), size, radius));
    return gradient / (2.0 * stepUv);
}

vec4 diffuseSample(vec2 centerUv, vec2 radiusUv)
{
    const float weights[5] = float[5](0.0625, 0.25, 0.375, 0.25, 0.0625);
    vec4 sampleSum = vec4(0.0);
    for (int y = 0; y < 5; ++y) {
        for (int x = 0; x < 5; ++x) {
            vec2 offset = vec2(float(x - 2), float(y - 2)) * radiusUv * 0.5;
            vec2 sampleUv = clamp(centerUv + offset, vec2(0.0), vec2(1.0));
            sampleSum += texture(source, sampleUv) * weights[x] * weights[y];
        }
    }
    return sampleSum;
}

void main()
{
    vec2 uv = qt_TexCoord0;
    vec2 scenePosition = u_sceneOrigin + uv * u_sceneSize;
    vec2 baseUv = scenePosition / u_canonicalSize;

    vec2 gradient = surfaceGradient(uv, u_sceneSize, u_cornerRadius);
    vec3 normal = normalize(vec3(gradient * u_depth, 1.0));
    vec3 incident = vec3(0.0, 0.0, -1.0);
    vec3 rayRed = refract(incident, normal,
                          1.0 / max(u_ior - u_dispersionIor, 1.001));
    vec3 rayGreen = refract(incident, normal, 1.0 / max(u_ior, 1.001));
    vec3 rayBlue = refract(incident, normal,
                           1.0 / max(u_ior + u_dispersionIor, 1.001));
    vec2 displacedUv = baseUv + rayGreen.xy * u_refractionPixels / u_canonicalSize;
    vec2 diffusionRadius = vec2(u_diffusionPixels) / u_canonicalSize;

    vec4 canonicalBackdrop = texture(source, baseUv) * qt_Opacity;
    if (u_dispersionIor > 0.0) {
        vec2 redUv = baseUv + rayRed.xy * u_refractionPixels / u_canonicalSize;
        vec2 blueUv = baseUv + rayBlue.xy * u_refractionPixels / u_canonicalSize;
        vec4 redSample = diffuseSample(redUv, diffusionRadius);
        vec4 greenSample = diffuseSample(displacedUv, diffusionRadius);
        vec4 blueSample = diffuseSample(blueUv, diffusionRadius);
        fragColor = vec4(redSample.r, greenSample.g, blueSample.b, greenSample.a) * qt_Opacity;
    } else {
        fragColor = diffuseSample(displacedUv, diffusionRadius) * qt_Opacity;
    }
    fragColor.rgb *= clamp(u_transmission, 0.0, 1.0);

    float boundaryDistance = roundedRectangleDistance(uv, u_sceneSize, u_cornerRadius);

    if (u_sceneLightStrength > 0.0) {
        vec2 lightFilterRadius = vec2(u_sceneLightPixels) / u_canonicalSize;
        vec3 sceneEnergy = diffuseSample(baseUv, lightFilterRadius).rgb;
        float normalResponse = clamp(0.25 + 0.75 * (1.0 - normal.z), 0.0, 1.0);
        float illumination = sceneLuminance(sceneEnergy) * normalResponse;
        fragColor.rgb += vec3(illumination * u_sceneLightStrength);
    }

    if (u_edgeLightStrength > 0.0) {
        float bevelCoordinate = clamp(
            (boundaryDistance + u_bevelWidthPx) / u_bevelWidthPx, 0.0, 1.0);
        float edgeBand = smootherstep(bevelCoordinate);
        float grazingResponse = pow(
            clamp(1.0 - normal.z, 0.0, 1.0), 0.5);
        vec2 point = (uv * u_sceneSize - u_sceneSize * 0.5) / (u_sceneSize * 0.5);
        vec2 lightDirection = normalize(u_edgeLightDirection);
        float horizontalProgress = smootherstep(clamp(
            0.5 + 0.5 * point.x * sign(lightDirection.x), 0.0, 1.0));
        float verticalProgress = smootherstep(clamp(
            0.5 - 0.5 * point.y * sign(-lightDirection.y), 0.0, 1.0));
        float perimeterEnvelope = horizontalProgress * verticalProgress;
        fragColor.rgb += vec3(
            edgeBand * perimeterEnvelope * grazingResponse * u_edgeLightStrength);
    }

    float antialiasWidth = max(fwidth(boundaryDistance), 0.5);
    float roundedMask = 1.0 - smoothstep(-antialiasWidth, antialiasWidth, boundaryDistance);
    if (u_transparentOutsideMask > 0.5)
        fragColor = vec4(fragColor.rgb * roundedMask, fragColor.a * roundedMask);
    else
        fragColor = mix(canonicalBackdrop, fragColor, roundedMask);
}
