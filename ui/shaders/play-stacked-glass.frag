#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_cardOrigin;
    vec2 u_cardSize;
    float u_cardRadius;
    float u_cardIor;
    float u_cardDepth;
    float u_cardRefractionPixels;
    float u_cardDispersionIor;
    float u_cardDiffusionPixels;
    float u_cardTransmission;
    float u_cardBevelWidth;
    float u_cardBulgeStrength;
    float u_cardEdgeLightStrength;
    vec2 u_cardEdgeLightDirection;
    vec2 u_playOrigin;
    vec2 u_canonicalSize;
    vec2 u_playSize;
    float u_playRadius;
    float u_playIor;
    float u_playDepth;
    float u_playRefractionPixels;
    float u_playRefractionBiasPx;
    float u_playMaterialBiasPx;
    float u_playDispersionIor;
    float u_playDiffusionPixels;
    float u_playTransmission;
    float u_playBulgeStrength;
    float u_playBevelWidth;
    float u_playEdgeLightStrength;
    float u_focusBrightness;
    int u_diagnostic;
};
layout(binding = 1) uniform sampler2D source;

float smooth5(float t) { return t*t*t*(t*(t*6.0-15.0)+10.0); }

float roundedDistance(vec2 p, vec2 size, float radius)
{
    vec2 h = size * 0.5;
    float r = min(radius, min(h.x, h.y));
    vec2 q = abs(p - h) - (h - vec2(r));
    return length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - r;
}

float bulgeHeight(vec2 uv, vec2 size, float radius, float bevel, float strength)
{
    float d = roundedDistance(uv * size, size, radius);
    float fade = bevel > 0.0
               ? smooth5(clamp((-d - bevel) / bevel, 0.0, 1.0))
               : smooth5(clamp(-d / max(min(size.x, size.y) * 0.5, 1.0), 0.0, 1.0));
    vec2 n = clamp(abs(uv - 0.5) * 2.0, vec2(0.0), vec2(1.0));
    float dome = cos(n.x * 1.57079633) * cos(n.y * 1.57079633);
    return strength * dome * fade;
}

float bevelHeight(vec2 uv, vec2 size, float radius, float bevel)
{
    float boundaryDistance = roundedDistance(uv * size, size, radius);
    float transitionWidth = max(bevel, 1.0);
    float t = clamp((transitionWidth + boundaryDistance) / transitionWidth, 0.0, 1.0);
    return smooth5(t);
}

vec2 cardSurfaceGradient(vec2 uv, vec2 size, float radius, float bevel, float strength)
{
    vec2 e = 1.0 / size;
    vec2 gradient = vec2(
        (bevelHeight(uv + vec2(e.x, 0), size, radius, bevel)
         + bulgeHeight(uv + vec2(e.x, 0), size, radius, bevel, strength))
        - (bevelHeight(uv - vec2(e.x, 0), size, radius, bevel)
         + bulgeHeight(uv - vec2(e.x, 0), size, radius, bevel, strength)),
        (bevelHeight(uv + vec2(0, e.y), size, radius, bevel)
         + bulgeHeight(uv + vec2(0, e.y), size, radius, bevel, strength))
        - (bevelHeight(uv - vec2(0, e.y), size, radius, bevel)
         + bulgeHeight(uv - vec2(0, e.y), size, radius, bevel, strength)))
        / (2.0 * e);
    return gradient;
}

vec2 gradient(vec2 uv, vec2 size, float radius, float bevel, float strength)
{
    vec2 e = 1.0 / size;
    return vec2(
        bulgeHeight(uv + vec2(e.x, 0), size, radius, bevel, strength)
            - bulgeHeight(uv - vec2(e.x, 0), size, radius, bevel, strength),
        bulgeHeight(uv + vec2(0, e.y), size, radius, bevel, strength)
            - bulgeHeight(uv - vec2(0, e.y), size, radius, bevel, strength)) / (2.0 * e);
}

vec4 filtered(vec2 uv, vec2 radiusUv)
{
    const float w[5] = float[5](0.0625, 0.25, 0.375, 0.25, 0.0625);
    vec4 result = vec4(0.0);
    for (int y = 0; y < 5; ++y)
        for (int x = 0; x < 5; ++x) {
            vec2 offset = vec2(float(x - 2), float(y - 2)) * radiusUv * 0.5;
            result += texture(source, clamp(uv + offset, vec2(0), vec2(1))) * w[x] * w[y];
        }
    return result;
}

vec4 sampleCardMaterial(vec2 scenePosition)
{
    vec2 cardUv = scenePosition / u_cardSize;
    vec2 baseUv = (u_cardOrigin + scenePosition) / u_canonicalSize;
    vec2 g = cardSurfaceGradient(cardUv, u_cardSize, u_cardRadius,
                                  u_cardBevelWidth, u_cardBulgeStrength);
    vec3 normal = normalize(vec3(g * u_cardDepth, 1.0));
    vec3 incident = vec3(0, 0, -1);
    vec3 rr = refract(incident, normal, 1.0 / max(u_cardIor - u_cardDispersionIor, 1.001));
    vec3 rg = refract(incident, normal, 1.0 / max(u_cardIor, 1.001));
    vec3 rb = refract(incident, normal, 1.0 / max(u_cardIor + u_cardDispersionIor, 1.001));
    vec2 radiusUv = vec2(u_cardDiffusionPixels) / u_canonicalSize;
    vec4 red = filtered(baseUv + rr.xy * u_cardRefractionPixels / u_canonicalSize, radiusUv);
    vec4 green = filtered(baseUv + rg.xy * u_cardRefractionPixels / u_canonicalSize, radiusUv);
    vec4 blue = filtered(baseUv + rb.xy * u_cardRefractionPixels / u_canonicalSize, radiusUv);
    vec4 result = vec4(red.r, green.g, blue.b, green.a);
    result.rgb *= u_cardTransmission;
    float d = roundedDistance(scenePosition, u_cardSize, u_cardRadius);
    float band = smooth5(clamp((d + u_cardBevelWidth) / u_cardBevelWidth, 0.0, 1.0));
    float grazing = pow(clamp(1.0 - normal.z, 0.0, 1.0), 0.5);
    vec2 p = (scenePosition - u_cardSize * 0.5) / (u_cardSize * 0.5);
    vec2 ld = normalize(u_cardEdgeLightDirection);
    float envelope = smooth5(clamp(0.5 + 0.5*p.x*sign(ld.x), 0.0, 1.0))
                   * smooth5(clamp(0.5 - 0.5*p.y*sign(-ld.y), 0.0, 1.0));
    result.rgb += vec3(band * grazing * envelope * u_cardEdgeLightStrength);
    float mask = 1.0 - smoothstep(-1.0, 1.0, d);
    return mix(texture(source, clamp(baseUv, vec2(0), vec2(1))), result, mask);
}

vec4 playFiltered(vec2 scenePosition, vec2 radiusPx)
{
    const float w[5] = float[5](0.0625, 0.25, 0.375, 0.25, 0.0625);
    vec4 result = vec4(0.0);
    for (int y = 0; y < 5; ++y)
        for (int x = 0; x < 5; ++x)
            result += sampleCardMaterial(scenePosition + vec2(float(x-2), float(y-2)) * radiusPx * 0.5)
                    * w[x] * w[y];
    return result;
}

void main()
{
    vec2 playUv = qt_TexCoord0;
    vec2 scenePosition = u_playOrigin + playUv * u_playSize;
    float boundaryDistance = roundedDistance(playUv * u_playSize, u_playSize, u_playRadius);
    float antialiasWidth = max(fwidth(boundaryDistance), 0.5);
    float playMask = 1.0 - smoothstep(-antialiasWidth, antialiasWidth, boundaryDistance);
    if (u_diagnostic == 1) {
        fragColor = vec4(vec3(playMask), 1.0) * qt_Opacity;
        return;
    }
    if (u_diagnostic == 2) {
        fragColor = vec4(vec3(1.0, 0.05, 0.8) * playMask, playMask) * qt_Opacity;
        return;
    }
    if (u_diagnostic == 3) {
        fragColor = sampleCardMaterial(scenePosition) * qt_Opacity;
        return;
    }
    // Keep the Play refraction normal local to the rounded perimeter. The old
    // zero-bevel bulge fallback produced a broad interior height field.
    const float playOpticalEdgeWidth = 8.0;
    vec2 playGradient = cardSurfaceGradient(
        playUv, u_playSize, u_playRadius, playOpticalEdgeWidth, 0.0);
    float edgeBiasBand = 1.0 - smoothstep(0.0, playOpticalEdgeWidth,
                                           abs(boundaryDistance));
    vec2 playRefractionBias = vec2(-1.0, -1.0)
        * u_playRefractionBiasPx * edgeBiasBand;
    vec2 playMaterialBias = vec2(-1.0, -1.0) * u_playMaterialBiasPx;
    vec3 n = normalize(vec3(playGradient * u_playDepth, 1.0));
    vec3 i = vec3(0,0,-1);
    vec3 rR = refract(i,n,1.0/max(u_playIor-u_playDispersionIor,1.001));
    vec3 rG = refract(i,n,1.0/max(u_playIor,1.001));
    vec3 rB = refract(i,n,1.0/max(u_playIor+u_playDispersionIor,1.001));
    vec2 playRadius = vec2(u_playDiffusionPixels) / min(u_playSize.x, u_playSize.y);
    vec4 red = playFiltered(scenePosition + playMaterialBias + playRefractionBias
                            + rR.xy*u_playRefractionPixels, playRadius);
    vec4 green = playFiltered(scenePosition + playMaterialBias + playRefractionBias
                              + rG.xy*u_playRefractionPixels, playRadius);
    vec4 blue = playFiltered(scenePosition + playMaterialBias + playRefractionBias
                             + rB.xy*u_playRefractionPixels, playRadius);
    vec4 result = vec4(red.r, green.g, blue.b, green.a);
    result.rgb *= u_playTransmission;
    float bevelBand = u_playBevelWidth > 0.0
        ? 1.0 - smoothstep(-1.0, 1.0,
            abs(boundaryDistance) - u_playBevelWidth) : 0.0;
    vec2 lightDirection = normalize(u_cardEdgeLightDirection);
    float directional = clamp(dot(normalize(vec3(lightDirection, 0)),
        vec3(n.xy, 0)), 0.0, 1.0);
    result.rgb += vec3(bevelBand * directional * u_playEdgeLightStrength);
    result.rgb *= u_focusBrightness;
    // The focal card underneath owns every pixel outside the Play footprint.
    fragColor = vec4(result.rgb * playMask, playMask) * qt_Opacity;
}
