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

float angularBands(float angle, float phase)
{
    float a = sin(angle * 7.0 + phase) * 0.45
            + sin(angle * 13.0 - phase * 0.63) * 0.22
            + sin(angle * 23.0 + phase * 0.31) * 0.12;
    return a;
}

void main()
{
    vec2 uv = qt_TexCoord0;
    vec2 p = (uv - 0.5) * vec2(u_resolution.x / max(u_resolution.y, 1.0), 1.0);
    // The base shell clock advances roughly one shader-time unit per second.
    // Keep the image anchored but give the low-amplitude deformation and light
    // travel enough phase movement to register during a short Home-screen glance.
    float time = u_time * 0.16;

    // Asymmetric blast core, deliberately offset into the right half to retain
    // quiet negative space behind the Home title and left rail.
    vec2 blast = p - vec2(0.16, 0.015);
    float radius = length(blast);
    float angle = atan(blast.y, blast.x);
    float rays = pow(max(0.0, 0.5 + 0.5 * sin(angle * 31.0
        + 2.2 * sin(angle * 7.0) + time * 0.3)), 18.0);
    float radialPulse = exp(-radius * 4.0) * (0.55 + 0.45 * sin(radius * 30.0 - time));
    float explosion = (rays * 0.5 + radialPulse * 0.22)
                    * exp(-radius * 2.8);

    // A low-cost domain-warped polar field forms fractured, twisted ribbons.
    // Fixed iteration count keeps the canonical wallpaper predictable on BC-250.
    vec2 q = p - vec2(0.20, -0.005);
    float r = length(q);
    float a = atan(q.y, q.x);
    float warp = angularBands(a, time) * 0.08;
    float twist = a + 1.65 * r + warp + 0.025 * sin(time + r * 8.0);
    float ridgeA = 0.265 + 0.075 * sin(twist * 3.0 + 0.6 * sin(a * 5.0));
    float ridgeB = 0.155 + 0.045 * sin(twist * 5.0 - a * 2.0 + 1.2);
    float ridgeC = 0.355 + 0.038 * sin(twist * 7.0 + a * 3.0);
    float dA = abs(r - ridgeA - 0.025 * sin(a * 9.0 + r * 20.0 + time * 0.15));
    float dB = abs(r - ridgeB - 0.018 * sin(a * 11.0 - r * 17.0));
    float dC = abs(r - ridgeC - 0.014 * sin(a * 15.0 + r * 11.0));
    float ribbonA = exp(-dA * 105.0) * (1.0 - smoothstep(0.12, 0.52, r));
    float ribbonB = exp(-dB * 125.0) * (1.0 - smoothstep(0.09, 0.40, r));
    float ribbonC = exp(-dC * 140.0) * (1.0 - smoothstep(0.18, 0.49, r));
    float structure = max(ribbonA, max(ribbonB * 0.82, ribbonC * 0.72));

    // Alternating dark/mid/silver bands provide a sharp polished-metal response.
    float band = 0.5 + 0.5 * cos((dA + 0.012 * sin(a * 6.0 + time * 0.9)
        + 0.006 * sin(a * 3.0 - time * 0.7)) * 480.0);
    float specular = smoothstep(0.78, 0.99, band) * structure;
    float steel = structure * (0.18 + 0.42 * band);
    float blueRef = structure * (0.16 + 0.25
        * (0.5 + 0.5 * sin(a * 9.0 + r * 50.0 - time * 0.8)));
    float energySweep = pow(max(0.0, 0.5 + 0.5
        * sin(angle * 3.0 + time * 0.75 - radius * 24.0)), 9.0)
        * exp(-radius * 2.2);

    // Fine radial construction lines and a nearly invisible technical grid.
    float gridX = 1.0 - smoothstep(0.0, 0.010, abs(fract((uv.x + 0.5) * 22.0) - 0.5));
    float gridY = 1.0 - smoothstep(0.0, 0.010, abs(fract((uv.y + 0.5) * 14.0) - 0.5));
    float grid = (gridX + gridY) * (0.018 + 0.018 * explosion)
               * smoothstep(0.25, 0.85, uv.x);
    float spokes = pow(max(0.0, 0.5 + 0.5 * cos(angle * 44.0)), 48.0)
                 * exp(-radius * 2.4) * 0.12;

    vec3 voidColor = vec3(0.020, 0.020, 0.028);
    float vignette = 1.0 - smoothstep(0.16, 1.12, length((uv - vec2(0.48, 0.52))
        * vec2(u_resolution.x / max(u_resolution.y, 1.0), 1.0)));
    vec3 color = voidColor * (0.38 + 0.62 * vignette);
    color += u_surface * (0.10 + 0.16 * explosion);
    color += u_secondary * (explosion * 0.27 + spokes * 0.55);
    color += u_primary * (explosion * 0.14 + blueRef * 0.50
        + energySweep * 0.18 + grid * 0.30);
    color += vec3(0.20, 0.22, 0.27) * steel;
    color += vec3(0.78, 0.80, 0.86) * specular;
    color += vec3(0.62, 0.66, 0.73) * (structure * 0.20);

    // Sparse signal glints: mostly blue, with rare red/green instrument ticks.
    vec2 cell = floor(uv * vec2(92.0, 52.0));
    float signal = step(0.997, hash21(cell));
    float signalBand = step(0.82, fract(uv.y * 8.0 + uv.x * 3.0));
    color += u_error * signal * signalBand * 0.22;
    color += vec3(0.0, 0.55, 0.18) * step(0.999, hash21(cell + 19.7)) * 0.16;

    float grain = (hash21(gl_FragCoord.xy + floor(u_time * 1.7)) - 0.5) * 0.012;
    color = max(vec3(0.0), color + grain);
    color *= clamp(u_brightness, 0.0, 1.0);
    fragColor = vec4(color, clamp(u_visibility, 0.0, 1.0)) * qt_Opacity;
}
