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

#define MAX_STEPS 24
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

    vec3 hub = vec3(0.04, 0.02, 0.0);

    // Central nexus.
    {
        vec3 q = p - hub;
        q.xy *= rot(-0.45);
        q.xz *= rot(0.25);

        float core = sdOctahedron(q, 0.42);
        float cage = sdRoundBox(q, vec3(0.20,0.12,0.12), 0.02);
        float d = min(core, cage);

        for(int i=0;i<3;i++)
        {
            float fi = float(i);

            vec3 off = vec3(
                cos(fi*1.4),
                sin(fi*1.9),
                sin(fi*2.3 + 0.7)
            ) * vec3(0.08, 0.07, 0.07);

            float sphere = sdSphere(
                q-off,
                0.055 + 0.01*hash11(fi*3.1)
            );

            d = smin(d, sphere, 0.05);
        }

        res = opU(res, vec2(d, 1.0));
    }

    // Large viewport-breaking spikes.
    for(int i=0;i<4;i++)
    {
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
            rad = 0.17;
            flatten = 0.80;
        }
        else if(i == 2)
        {
            dir = normalize(vec3(-0.08,1.0,0.06));
            len = 3.5;
            rad = 0.14;
            flatten = 0.65;
        }
        else
        {
            dir = normalize(vec3(0.72,0.62,-0.05));
            len = 3.6;
            rad = 0.13;
            flatten = 0.70;
        }

        vec3 q = toDirSpace(p-hub,dir);
        float h = len*0.5;
        q.y -= h;

        float spike = sdCappedCone(q,h,rad,0.014);

        spike = max(
            spike,
            abs(q.z)-rad*flatten*0.50
        );

        res = opU(res,vec2(spike,2.0));
    }

    // Orbital loops.
    {
        vec3 q = p-(hub+vec3(0.04,0.02,0.0));
        q.xy *= rot(0.52);
        q.yz *= rot(1.15);

        float d = sdTorus(q,vec2(0.78,0.040));
        res = opU(res,vec2(d,3.0));
    }

    {
        vec3 q = p-(hub+vec3(-0.03,-0.02,0.0));
        q.xz *= rot(-0.78);
        q.xy *= rot(0.95);

        float d = sdTorus(q,vec2(1.02,0.038));
        res = opU(res,vec2(d,3.0));
    }

    // Medium converging spikes.
    for(int i=0;i<4;i++)
    {
        float fi = float(i);

        float ang = fi/4.0*2.0*PI;

        float z = mix(-0.35,0.35,hash11(fi*8.1+1.7));

        vec3 dir = normalize(vec3(
            cos(ang),
            sin(ang)*0.65+0.12,
            z
        ));

        float len = mix(0.80,1.55,hash11(fi*3.7+2.3));

        float w = mix(0.055,0.085,hash11(fi*6.2+4.1));

        vec3 q = toDirSpace(p-hub,dir);

        float h = len*0.5;
        q.y -= h;

        float spike = sdCappedCone(q,h,w,0.012);

        res = opU(res,vec2(spike,4.0));
    }

    return res;
}

vec3 calcNormal(vec3 p)
{
    vec2 e = vec2(EPS, -EPS);
    return normalize(
        e.xyy * mapScene(p+e.xyy).x +
        e.yyx * mapScene(p+e.yyx).x +
        e.yxy * mapScene(p+e.yxy).x +
        e.xxx * mapScene(p+e.xxx).x
    );
}

float lineGrid(vec2 p, float scale, float thickness)
{
    vec2 g = abs(fract(p*scale)-0.5);
    float d = min(g.x,g.y);
    float aa = max(1.2*fwidth(d), 0.0001);
    return 1.0-smoothstep(thickness-aa,thickness+aa,d);
}

float ring(vec2 p, vec2 c, float r, float w)
{
    float d = abs(length(p-c)-r);
    float aa = max(1.2*fwidth(d), 0.0001);
    return 1.0-smoothstep(w-aa,w+aa,d);
}

vec3 backdrop(vec2 uv)
{
    float t = u_time*0.50;

    vec3 col = mix(
        vec3(0.003,0.006,0.010),
        vec3(0.010,0.025,0.035),
        clamp(uv.y*0.55+0.5,0.0,1.0)
    );

    col *= 1.0 - 0.24*dot(uv,uv);

    float diagonalPhase = (uv.x+uv.y)*170.0;
    float diagonalFootprint = 0.5*170.0*fwidth(uv.x+uv.y);
    float diagonalFilter = sin(diagonalFootprint)/max(diagonalFootprint,0.0001);
    float diag = sin(diagonalPhase)*0.5*diagonalFilter+0.5;
    col *= 0.992 + 0.012*diag;

    float g1 = lineGrid(uv+vec2(0.02,0.0),4.8,0.009);
    float g2 = lineGrid(uv,12.0,0.005);

    col += vec3(0.010,0.045,0.055)*g1*0.22;
    col += vec3(0.006,0.022,0.030)*g2*0.12;

    float r1 = ring(uv,vec2(0.66,0.42),0.56,0.0025);
    float r2 = ring(uv,vec2(0.66,0.42),0.90,0.0018);

    col += vec3(0.04,0.19,0.23)*(r1+r2)*0.30;

    for(int i=0;i<4;i++)
    {
        float y = 0.48 - float(i)*0.18;

        float a = ring(uv,vec2(0.62,y),0.026,0.0025);
        float b = ring(uv,vec2(0.70,y),0.026,0.0025);

        col += vec3(0.12,0.48,0.58)*a*0.35;
        col += vec3(0.08,0.30,0.38)*b*0.22;
    }

    float horizonDistance = abs(uv.y-0.04);
    float horizonAA = max(fwidth(horizonDistance),0.0001);
    float horizon = 1.0-smoothstep(0.001-horizonAA,0.001+horizonAA,horizonDistance);
    col += vec3(0.035,0.16,0.20)*horizon*0.35;

    float scanY = -0.18 + 0.46*sin(t*0.65);
    float scanWidth = max(fwidth(uv.y),0.0015);
    float scan = exp(-2.5*abs(uv.y-scanY)/scanWidth);
    col += vec3(0.010,0.045,0.060)*scan*0.18;

    return col;
}

vec3 envMap(vec3 r)
{
    float y = r.y*0.5+0.5;

    vec3 col = mix(
        vec3(0.002,0.004,0.008),
        vec3(0.10,0.22,0.30),
        pow(y,0.80)
    );

    float band1 = exp(-55.0*abs(r.y-0.28));
    float band2 = exp(-100.0*abs(r.y+0.18));
    float band3 = exp(-120.0*abs(r.x*0.6+r.y*0.3-0.18));

    col += vec3(0.42,0.72,0.88)*band1*1.25;
    col += vec3(0.88,0.98,1.0)*band2*1.55;
    col += vec3(0.12,0.42,0.62)*band3*0.55;
    col += vec3(0.015,0.075,0.16)*pow(max(r.x,0.0),8.0);

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

    vec3 sweepCol = vec3(0.12,0.72,1.20)*sweep;

    vec3 col = base*(0.07+0.62*diff)
        + env*envAmt*(0.74+0.58*fres)
        + spec*vec3(1.45,1.55,1.70)*2.25
        + sweepCol*(0.12+0.38*fres);

    col += vec3(0.20,0.55,1.10)
        *pow(1.0-max(dot(n,V),0.0),7.0)*0.88;

    return col;
}

bool intersectSceneBounds(vec3 ro, vec3 rd, out float tNear, out float tFar)
{
    const vec3 center = vec3(0.04,1.17,0.0);
    const vec3 halfExtent = vec3(5.25,2.78,1.50);
    vec3 a = (center-halfExtent-ro)/rd;
    vec3 b = (center+halfExtent-ro)/rd;
    vec3 lo = min(a,b);
    vec3 hi = max(a,b);
    tNear = max(max(lo.x,lo.y),max(lo.z,0.0));
    tFar = min(min(hi.x,hi.y),hi.z);
    return tFar >= tNear && tFar > 0.0;
}

vec3 renderSceneRay(vec3 ro, vec3 rd, vec3 bg, out bool edgeCandidate)
{
    float tNear;
    float tFar;
    float travel = 0.0;
    float mat = 0.0;
    float closestDistance = 1e5;
    bool hit = false;
    edgeCandidate = false;

    if(intersectSceneBounds(ro,rd,tNear,tFar))
    {
        travel = tNear;
        float marchLimit = min(tFar,FAR_CLIP);
        for(int i=0;i<MAX_STEPS;i++)
        {
            vec3 p = ro + rd*travel;
            vec2 h = mapScene(p);
            closestDistance = min(closestDistance,h.x);

            if(h.x < EPS)
            {
                hit = true;
                mat = h.y;
                break;
            }

            travel += max(h.x*0.92,EPS*0.5);

            if(travel > marchLimit)
                break;
        }

        float pixelFootprint = max(
            EPS,
            travel*2.0/(1.90*max(u_resolution.y,1.0))
        );

        if(!hit && closestDistance < pixelFootprint*3.0)
            edgeCandidate = true;
    }

    if(!hit)
        return bg;

    vec3 p = ro + rd*travel;
    vec3 n = calcNormal(p);
    if(abs(dot(n,rd)) < 0.55)
        edgeCandidate = true;

    vec3 metal = shade(p,rd,n,mat) * 0.88;
    float haze = smoothstep(5.0,11.0,travel);
    return mix(metal,bg,haze*0.08);
}

void main()
{
    vec2 shaderUv = vec2(qt_TexCoord0.x, 1.0 - qt_TexCoord0.y);

    vec2 fragCoord = shaderUv * u_resolution;

    vec2 uv = (2.0*fragCoord-u_resolution.xy)
        / max(u_resolution.y,1.0);

    vec3 bg = backdrop(uv);

    vec3 ro = vec3(0.10,0.02,4.8);
    vec3 ta = vec3(-1.55,-1.20,0.0);

    ro.xy += vec2(sin(u_time*0.34),cos(u_time*0.26))*0.035;

    vec3 ww = normalize(ta-ro);
    vec3 uu = normalize(cross(ww,vec3(0.0,1.0,0.0)));
    vec3 vv = cross(uu,ww);

    vec3 rd = normalize(ww*1.90 + uv.x*uu + uv.y*vv);

    bool edgeCandidate;
    vec3 color = renderSceneRay(ro,rd,bg,edgeCandidate);

    if(edgeCandidate)
    {
        float quarterPixel = 0.5/max(u_resolution.y,1.0);
        vec2 sampleOffsets[2] = vec2[2](
            vec2(-quarterPixel,-quarterPixel),
            vec2(quarterPixel,quarterPixel)
        );
        vec3 colorSum = color;
        for(int i=0;i<2;i++)
        {
            vec2 sampleUv = uv + sampleOffsets[i];
            vec3 sampleRd = normalize(
                ww*1.90 + sampleUv.x*uu + sampleUv.y*vv
            );
            bool sampleEdgeCandidate;
            colorSum += renderSceneRay(ro,sampleRd,bg,sampleEdgeCandidate);
        }
        color = colorSum/3.0;
    }

    color = max(color,vec3(0.0));
    color = pow(color,vec3(0.92));
    color *= vec3(0.92,0.98,1.08);
    color *= 1.12;
    color = clamp(color,0.0,1.0);
    color *= clamp(u_brightness,0.0,1.0);

    fragColor = vec4(color,clamp(u_visibility,0.0,1.0))*qt_Opacity;
}
