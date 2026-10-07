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

#define MAX_STEPS 96
#define FAR_CLIP  18.0
#define EPS       0.0012
#define PI        3.14159265359

mat2 rot(float a)
{
    float c = cos(a), s = sin(a);
    return mat2(c,-s,s,c);
}

float hash11(float p)
{
    return fract(sin(p * 127.1) * 43758.5453123);
}

vec2 opU(vec2 a, vec2 b)
{
    return (a.x < b.x) ? a : b;
}

float smin(float a, float b, float k)
{
    float h = clamp(0.5 + 0.5*(b-a)/k, 0.0, 1.0);
    return mix(b, a, h) - k*h*(1.0-h);
}

float sdSphere(vec3 p, float r)
{
    return length(p) - r;
}

float sdRoundBox(vec3 p, vec3 b, float r)
{
    vec3 q = abs(p)-b;
    return length(max(q,0.0)) + min(max(q.x,max(q.y,q.z)),0.0)-r;
}

float sdOctahedron(vec3 p, float s)
{
    p = abs(p);
    return (p.x + p.y + p.z - s) * 0.57735027;
}

float sdTorus(vec3 p, vec2 t)
{
    vec2 q = vec2(length(p.xz)-t.x, p.y);
    return length(q)-t.y;
}

float sdCappedCone(vec3 p, float h, float r1, float r2)
{
    vec2 q  = vec2(length(p.xz), p.y);
    vec2 k1 = vec2(r2,h);
    vec2 k2 = vec2(r2-r1,2.0*h);

    vec2 ca = vec2(q.x - min(q.x,(q.y<0.0)?r1:r2),
                   abs(q.y)-h);

    vec2 cb = q-k1 +
              k2*clamp(dot(k1-q,k2)/dot(k2,k2),0.0,1.0);

    float s = (cb.x<0.0 && ca.y<0.0) ? -1.0 : 1.0;
    return s*sqrt(min(dot(ca,ca),dot(cb,cb)));
}

vec3 toDirSpace(vec3 p, vec3 dir)
{
    dir = normalize(dir);

    vec3 helper = abs(dir.y) < 0.95
        ? vec3(0.0,1.0,0.0)
        : vec3(1.0,0.0,0.0);

    vec3 x = normalize(cross(helper,dir));
    vec3 z = cross(dir,x);

    return vec3(dot(p,x),dot(p,dir),dot(p,z));
}

vec2 mapScene(vec3 p)
{
    vec2 res = vec2(1e5, 0.0);

    float t = u_time * 0.90;

    p.xy *= rot(0.05*sin(t*0.23));
    p.yz *= rot(0.04*cos(t*0.19));

    vec3 hub = vec3(-0.10, -0.03, 0.0);

    // Central nexus.
    {
        vec3 q = p - hub;
        q.xy *= rot(-0.45);
        q.xz *= rot(0.25);

        float core = sdOctahedron(q, 0.42);
        float cage = sdRoundBox(q, vec3(0.20,0.12,0.12), 0.02);
        float d = min(core, cage);

        for(int i=0;i<5;i++)
        {
            float fi = float(i);

            vec3 off = vec3(
                cos(fi*1.4 + t*0.7),
                sin(fi*1.9 - t*0.5),
                sin(fi*2.3 + 0.7)
            ) * vec3(0.12, 0.10, 0.10);

            float sphere = sdSphere(
                q-off,
                0.055 + 0.01*hash11(fi*3.1)
            );

            d = smin(d, sphere, 0.05);
        }

        res = opU(res, vec2(d, 1.0));
    }

    // Large viewport-breaking spikes.
    for(int i=0;i<6;i++)
    {
        float fi = float(i);

        vec3 dir;
        float len;
        float rad;
        float flatten;

        if(i == 0)
        {
            dir = normalize(vec3(1.0,0.04,0.02));
            len = 4.9;
            rad = 0.18;
            flatten = 0.75;
        }
        else if(i == 1)
        {
            dir = normalize(vec3(-1.0,-0.26,0.05));
            len = 4.2;
            rad = 0.15;
            flatten = 0.80;
        }
        else if(i == 2)
        {
            dir = normalize(vec3(-0.08,1.0,0.06));
            len = 3.5;
            rad = 0.10;
            flatten = 0.65;
        }
        else if(i == 3)
        {
            dir = normalize(vec3(0.72,0.62,-0.05));
            len = 3.6;
            rad = 0.09;
            flatten = 0.70;
        }
        else if(i == 4)
        {
            dir = normalize(vec3(0.42,-0.88,0.22));
            len = 3.2;
            rad = 0.16;
            flatten = 0.82;
        }
        else
        {
            dir = normalize(vec3(-0.70,0.38,0.02));
            len = 2.7;
            rad = 0.07;
            flatten = 0.62;
        }

        dir.xy *= rot(0.08*sin(t*0.33 + fi*1.7));

        vec3 q = toDirSpace(p-hub,dir);
        float h = len*0.5;
        q.y -= h;

        float spike = sdCappedCone(q,h,rad,0.004);

        spike = max(
            spike,
            abs(q.z)-rad*flatten*0.50
        );

        res = opU(res,vec2(spike,2.0));
    }

    // Orbital loops.
    {
        vec3 q = p-(hub+vec3(0.04,0.02,0.0));
        q.xy *= rot(0.52 + 0.15*sin(t*0.32));
        q.yz *= rot(1.15);

        float d = sdTorus(q,vec2(0.78,0.022));
        res = opU(res,vec2(d,3.0));
    }

    {
        vec3 q = p-(hub+vec3(-0.03,-0.02,0.0));
        q.xz *= rot(-0.78);
        q.xy *= rot(0.95);

        float d = sdTorus(q,vec2(1.02,0.018));
        res = opU(res,vec2(d,3.0));
    }

    {
        vec3 q = p-hub;
        q.yz *= rot(0.42);
        q.xz *= rot(0.30 + 0.12*cos(t*0.28));

        float d = sdTorus(q,vec2(0.56,0.015));
        res = opU(res,vec2(d,3.0));
    }

    // Medium converging spikes.
    for(int i=0;i<15;i++)
    {
        float fi = float(i);

        float ang = fi/15.0*2.0*PI + 0.28*sin(t*0.45+fi);

        float z = mix(-0.35,0.35,hash11(fi*8.1+1.7));

        vec3 dir = normalize(vec3(
            cos(ang),
            sin(ang)*0.65+0.12,
            z
        ));

        float len = mix(0.65,1.8,hash11(fi*3.7+2.3));

        float w = mix(0.018,0.050,hash11(fi*6.2+4.1));

        vec3 q = toDirSpace(p-hub,dir);

        float h = len*0.5;
        q.y -= h;

        float spike = sdCappedCone(q,h,w,0.0018);

        if(mod(fi,3.0)<1.0)
            spike = max(spike,abs(q.z)-w*0.35);

        res = opU(res,vec2(spike,4.0));
    }

    // Thin needle accents.
    for(int i=0;i<8;i++)
    {
        float fi = float(i);
        float ang = fi/8.0*2.0*PI+0.1;

        vec3 dir = normalize(vec3(
            cos(ang),
            0.25*sin(ang*2.0)+0.45,
            sin(ang)
        ));

        vec3 q = toDirSpace(p-(hub+vec3(0.0,0.02,0.0)),dir);

        float h = 1.6 + 0.6*hash11(fi*7.0);

        q.y -= h;

        float needle = sdCappedCone(q,h,0.010,0.0008);

        res = opU(res,vec2(needle,5.0));
    }

    return res;
}

vec3 calcNormal(vec3 p)
{
    vec2 e = vec2(EPS,0.0);

    return normalize(vec3(
        mapScene(p+e.xyy).x-mapScene(p-e.xyy).x,
        mapScene(p+e.yxy).x-mapScene(p-e.yxy).x,
        mapScene(p+e.yyx).x-mapScene(p-e.yyx).x
    ));
}

float calcAO(vec3 p, vec3 n)
{
    float occ = 0.0;
    float sca = 1.0;

    for(int i=0;i<5;i++)
    {
        float h = 0.025 + 0.11*float(i);
        float d = mapScene(p+n*h).x;

        occ += (h-d)*sca;
        sca *= 0.68;
    }

    return clamp(1.0-occ*1.45,0.0,1.0);
}

float lineGrid(vec2 p, float scale, float thickness)
{
    vec2 g = abs(fract(p*scale)-0.5);
    float d = min(g.x,g.y);

    return 1.0-smoothstep(thickness,thickness+0.01,d);
}

float ring(vec2 p, vec2 c, float r, float w)
{
    return 1.0-smoothstep(w,w+0.002,abs(length(p-c)-r));
}

vec3 backdrop(vec2 uv)
{
    float t = u_time*0.50;

    vec3 col = mix(
        vec3(0.47,0.62,0.75),
        vec3(0.86,0.92,0.96),
        uv.y*0.55+0.5
    );

    col *= 1.0 - 0.24*dot(uv,uv);

    float diag = sin((uv.x+uv.y)*170.0)*0.5+0.5;
    col *= 0.98 + 0.03*diag;

    float g1 = lineGrid(uv+vec2(0.02,0.0),4.8,0.48);
    float g2 = lineGrid(uv,12.0,0.487);

    col += vec3(0.16,0.22,0.27)*g1*0.34;
    col += vec3(0.10,0.14,0.18)*g2*0.10;

    float r1 = ring(uv,vec2(0.34,-0.18),0.56,0.004);
    float r2 = ring(uv,vec2(0.34,-0.18),0.90,0.003);

    col += vec3(0.90,0.97,1.0)*(r1+r2)*0.42;

    for(int i=0;i<4;i++)
    {
        float y = 0.48 - float(i)*0.18;

        float a = ring(uv,vec2(0.56,y),0.026,0.004);
        float b = ring(uv,vec2(0.64,y),0.026,0.004);

        col += vec3(1.0)*a*0.68;
        col += vec3(1.0)*b*0.48;
    }

    float horizon = 1.0-smoothstep(0.002,0.006,abs(uv.y+0.02));
    col += vec3(0.95,0.99,1.0)*horizon*0.72;

    float scanY = -0.24 + 0.52*sin(t*0.65);
    float scan = exp(-70.0*abs(uv.y-scanY));
    col += vec3(0.12,0.18,0.26)*scan*0.11;

    float grain = hash11(
        floor(uv.x*900.0)
        + floor(uv.y*700.0)*57.0
        + floor(u_time*12.0)*0.001
    );
    col += (grain-0.5)*0.028;

    return col;
}

vec3 envMap(vec3 r)
{
    float y = r.y*0.5+0.5;

    vec3 col = mix(
        vec3(0.008,0.015,0.040),
        vec3(0.72,0.86,0.98),
        pow(y,0.65)
    );

    float band1 = exp(-55.0*abs(r.y-0.28));
    float band2 = exp(-100.0*abs(r.y+0.18));
    float band3 = exp(-120.0*abs(r.x*0.6+r.y*0.3-0.18));

    col += vec3(0.78,0.92,1.0)*band1*1.45;
    col += vec3(1.0)*band2*1.75;
    col += vec3(0.38,0.70,1.0)*band3*0.68;
    col += vec3(0.05,0.18,0.45)*pow(max(r.x,0.0),8.0);

    return col;
}

vec3 shade(vec3 p, vec3 rd, vec3 n, float mat)
{
    vec3 V = -rd;
    vec3 R = reflect(rd,n);

    vec3 lightDir = normalize(vec3(-0.45,0.74,0.50));
    vec3 halfDir = normalize(lightDir+V);

    float diff = max(dot(n,lightDir),0.0);
    float spec = pow(max(dot(n,halfDir),0.0),110.0);
    float fres = pow(1.0-max(dot(n,V),0.0),5.0);

    vec3 env = envMap(R);

    vec3 base;
    float envAmt;

    if(mat < 1.5)
    {
        base = vec3(0.04,0.08,0.17);
        envAmt = 1.20;
    }
    else if(mat < 2.5)
    {
        base = vec3(0.03,0.09,0.19);
        envAmt = 1.34;
    }
    else if(mat < 3.5)
    {
        base = vec3(0.02,0.06,0.15);
        envAmt = 1.15;
    }
    else if(mat < 4.5)
    {
        base = vec3(0.015,0.045,0.12);
        envAmt = 1.05;
    }
    else
    {
        base = vec3(0.006,0.010,0.020);
        envAmt = 0.62;
    }

    float sweep = 0.5 + 0.5*sin(
        u_time*2.2 + p.x*2.4 - p.y*1.8 + p.z*2.0
    );
    sweep = pow(sweep,8.0);

    vec3 sweepCol = vec3(0.18,0.65,1.25)*sweep;

    vec3 col = base*(0.07+0.62*diff)
        + env*envAmt*(0.74+0.58*fres)
        + spec*vec3(1.45,1.55,1.70)*2.25
        + sweepCol*(0.12+0.38*fres);

    col += vec3(0.20,0.55,1.10)
        *pow(1.0-max(dot(n,V),0.0),7.0)*0.88;

    return col;
}

void main()
{
    vec2 shaderUv = vec2(qt_TexCoord0.x, 1.0 - qt_TexCoord0.y);

    vec2 fragCoord = shaderUv * u_resolution;

    vec2 uv = (2.0*fragCoord-u_resolution.xy)
        / max(u_resolution.y,1.0);

    vec3 bg = backdrop(uv);

    vec3 ro = vec3(0.10,0.02,4.8);
    vec3 ta = vec3(-0.10,-0.02,0.0);

    ro.xy += vec2(sin(u_time*0.34),cos(u_time*0.26))*0.035;

    vec3 ww = normalize(ta-ro);
    vec3 uu = normalize(cross(ww,vec3(0.0,1.0,0.0)));
    vec3 vv = cross(uu,ww);

    vec3 rd = normalize(ww*1.90 + uv.x*uu + uv.y*vv);

    float travel = 0.0;
    float mat = 0.0;
    bool hit = false;

    for(int i=0;i<MAX_STEPS;i++)
    {
        vec3 p = ro + rd*travel;
        vec2 h = mapScene(p);

        if(h.x < EPS)
        {
            hit = true;
            mat = h.y;
            break;
        }

        travel += h.x*0.76;

        if(travel > FAR_CLIP)
            break;
    }

    vec3 color = bg;

    if(hit)
    {
        vec3 p = ro + rd*travel;
        vec3 n = calcNormal(p);
        float ao = calcAO(p,n);
        vec3 metal = shade(p,rd,n,mat);

        metal *= mix(0.54,1.0,ao);

        float haze = smoothstep(5.0,11.0,travel);

        color = mix(metal,bg,haze*0.14);
    }

    color = max(color,vec3(0.0));
    color = pow(color,vec3(0.92));
    color *= vec3(0.92,0.98,1.08);
    color = (color-0.5)*1.22+0.5;
    color = clamp(color,0.0,1.0);
    color *= clamp(u_brightness,0.0,1.0);

    fragColor = vec4(color,clamp(u_visibility,0.0,1.0))*qt_Opacity;
}
