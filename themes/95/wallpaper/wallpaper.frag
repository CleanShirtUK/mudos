#version 440

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_resolution;
    float u_brightness;
    float u_visibility;
};

void main()
{
    vec3 teal = vec3(0.0, 128.0 / 255.0, 128.0 / 255.0);
    fragColor = vec4(teal * clamp(u_brightness, 0.0, 1.0),
                     clamp(u_visibility, 0.0, 1.0)) * qt_Opacity;
}
