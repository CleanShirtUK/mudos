#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_resolution;
    vec2 u_origin;
    vec2 u_canvas;
    float u_time;
    float u_brightness;
    float u_visibility;
    vec3 u_primary;
    vec3 u_secondary;
    vec3 u_surface;
    vec3 u_error;
};

float hash21(vec2 p)
{
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float cloudField(vec2 p)
{
    float a = sin(p.x * 5.2 + sin(p.y * 3.1) * 1.4);
    float b = sin(p.x * 9.3 - p.y * 4.4 + 1.8);
    float c = sin(p.x * 15.0 + p.y * 7.0);
    return a * 0.48 + b * 0.32 + c * 0.20;
}

void main()
{
    vec2 uv = qt_TexCoord0;
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 p = (uv - 0.5) * vec2(aspect, 1.0);
    float time = u_time * 0.018;

    vec3 skyTop = vec3(0.31, 0.72, 0.94);
    vec3 skyNear = vec3(0.77, 0.93, 1.0);
    float horizon = smoothstep(0.0, 0.86, uv.y);
    vec3 color = mix(skyTop, skyNear, horizon);

    vec2 cloudUv = vec2(uv.x + time * 0.35, uv.y * 2.8 + 0.15 * sin(uv.x * 4.0));
    float cloud = cloudField(cloudUv);
    float cloudMask = smoothstep(0.18, 0.85, cloud) * (1.0 - smoothstep(0.48, 0.92, uv.y));
    float cloudLight = 0.5 + 0.5 * sin(uv.x * 3.1 + uv.y * 5.0 + time * 0.3);
    color = mix(color, vec3(0.92, 0.98, 1.0), cloudMask * (0.32 + 0.28 * cloudLight));

    vec2 sunPos = vec2(0.77, 0.30);
    float sunDistance = length((uv - sunPos) * vec2(aspect, 1.0));
    float glow = exp(-sunDistance * 3.8);
    float sunDisk = exp(-sunDistance * 38.0);
    color += vec3(0.32, 0.22, 0.08) * glow * 0.20;
    color = mix(color, vec3(1.0, 0.99, 0.91), sunDisk * 0.55);

    float meadowLine = 0.70 + 0.035 * sin(uv.x * 6.0 + time * 0.2)
        + 0.012 * sin(uv.x * 15.0 - time * 0.1);
    float meadow = smoothstep(meadowLine - 0.018, meadowLine + 0.018, uv.y);
    vec3 grassLight = vec3(0.57, 0.83, 0.32);
    vec3 grassDeep = vec3(0.20, 0.56, 0.24);
    float grassVariation = 0.5 + 0.5 * sin(uv.x * 7.0 + uv.y * 9.0 + time * 0.25);
    vec3 grass = mix(grassLight, grassDeep, smoothstep(0.0, 0.8, uv.y - meadowLine) * 0.65);
    grass += vec3(0.025, 0.06, 0.01) * grassVariation;
    color = mix(color, grass, meadow);

    float waterLine = 0.82 + 0.008 * sin(uv.x * 11.0 + time * 0.5);
    float water = smoothstep(waterLine - 0.008, waterLine + 0.008, uv.y);
    float ripple = 0.5 + 0.5 * sin(uv.x * 34.0 + uv.y * 7.0 - time * 1.4);
    vec3 waterColor = mix(vec3(0.16, 0.69, 0.84), vec3(0.50, 0.88, 0.91), ripple * 0.23);
    color = mix(color, waterColor, water);

    // Sparse, slowly rising glass bubbles; the field is deterministic and cheap.
    vec2 bubbleCell = floor(uv * vec2(13.0, 8.0));
    vec2 cellId = bubbleCell + vec2(0.0, floor(time * 0.16));
    vec2 rnd = vec2(hash21(cellId + 2.1), hash21(cellId + 9.7));
    vec2 local = fract(uv * vec2(13.0, 8.0));
    float rise = fract(time * 0.16 + rnd.y);
    vec2 bubbleCenter = vec2(0.22 + rnd.x * 0.56, 1.0 - rise);
    vec2 cellScale = vec2(13.0, 8.0);
    vec2 bubbleDelta = (uv - bubbleCenter) * cellScale;
    float bubbleRadius = 0.055 + rnd.x * 0.035;
    float bubbleEdge = abs(length(bubbleDelta) - bubbleRadius);
    float bubble = exp(-bubbleEdge * 210.0) * step(0.78, hash21(cellId + 18.4));
    float bubbleGlint = exp(-length(bubbleDelta - vec2(-0.016, -0.018)) * 90.0) * bubble;
    color += vec3(0.70, 0.93, 1.0) * bubble * 0.24;
    color += vec3(1.0) * bubbleGlint * 0.48;

    // Very soft bokeh near the sky/horizon, with no sharp decorative circles.
    vec2 bokehCell = floor(uv * vec2(18.0, 11.0));
    vec2 bokehRnd = vec2(hash21(bokehCell + 44.0), hash21(bokehCell + 71.0));
    vec2 bokehCenter = (bokehCell + 0.22 + 0.56 * bokehRnd) / vec2(18.0, 11.0);
    float bokeh = exp(-length((uv - bokehCenter) * vec2(aspect, 1.0)) * 50.0)
        * step(0.91, hash21(bokehCell + 3.0)) * (1.0 - meadow);
    color += vec3(0.76, 0.93, 1.0) * bokeh * 0.08;

    color *= clamp(u_brightness, 0.0, 1.0);
    fragColor = vec4(color, clamp(u_visibility, 0.0, 1.0)) * qt_Opacity;
}
