import math, random, re, sys
random.seed(11)
def bez(p0,p1,p2,t):
    x=(1-t)**2*p0[0]+2*(1-t)*t*p1[0]+t*t*p2[0]; y=(1-t)**2*p0[1]+2*(1-t)*t*p1[1]+t*t*p2[1]
    dx=2*(1-t)*(p1[0]-p0[0])+2*t*(p2[0]-p1[0]); dy=2*(1-t)*(p1[1]-p0[1])+2*t*(p2[1]-p1[1])
    return x,y,dx,dy
def f(v): return ('%.1f'%v).rstrip('0').rstrip('.')
def taper(p0,p1,p2,w0,w1,n=18):
    L=[];R=[]
    for i in range(n+1):
        t=i/n; x,y,dx,dy=bez(p0,p1,p2,t); m=math.hypot(dx,dy); nx,ny=-dy/m,dx/m
        w=(w0+(w1-w0)*t**0.8)/2
        L.append((x+nx*w,y+ny*w)); R.append((x-nx*w,y-ny*w))
    pts=L+R[::-1]
    return 'M '+' L '.join(f(x)+' '+f(y) for x,y in pts)+' Z'
def center(p0,p1,p2): return 'M %s %s Q %s %s %s %s'%tuple(f(v) for v in (*p0,*p1,*p2))
limbs=[((298,222),(250,172),(152,132)),((306,222),(298,142),(318,64)),((314,222),(384,174),(468,136))]
def at(l,t): return bez(*l,t)[:2]
br=[]
def branch(l,t,ctrl_off,end): 
    s=at(l,t); c=(s[0]+ctrl_off[0],s[1]+ctrl_off[1]); br.append((s,c,end))
branch(limbs[0],.42,(-6,-34),(206,70))
branch(limbs[0],.68,(-30,2),(104,156))
branch(limbs[0],.86,(-4,-22),(150,84))
branch(limbs[1],.36,(-30,-16),(248,98))
branch(limbs[1],.52,(30,-14),(374,92))
branch(limbs[2],.40,(8,-36),(408,72))
branch(limbs[2],.66,(34,-2),(524,112))
branch(limbs[2],.84,(6,-24),(476,80))
branch(limbs[1],.76,(-20,-10),(280,52))
branch(limbs[1],.80,(22,-8),(352,50))
out=[]
out.append('<g class="tr-wood-up">')
for l in limbs: out.append('<path class="tr-limb" d="%s"/>'%taper(*l,13,2.6))
for b in br: out.append('<path class="tr-limb tr-branch" d="%s"/>'%taper(*b,5.5,1.6,12))
out.append('</g>')
for l in limbs: out.append('<path class="tr-rot" pathLength="100" d="%s"/>'%center(*l))
def leaf(s): return 'M 0 0 C %s %s, %s %s, %s 0 C %s %s, %s %s, 0 0 Z'%tuple(f(v*s) for v in (5,-6.5,14,-7,20,14,7,5,6.5))
leaves=[]
def along(seg,w0,t0,step,tipbad=False):
    side=1; t=t0
    while t<0.97:
        x,y,dx,dy=bez(*seg,t); ang=math.degrees(math.atan2(dy,dx)); m=math.hypot(dx,dy); nx,ny=-dy/m,dx/m
        leaves.append((x+nx*side*w0*.3,y+ny*side*w0*.3,ang+side*random.uniform(38,68),random.uniform(.95,1.35),False))
        side=-side; t+=step*random.uniform(.85,1.15)
    x,y,dx,dy=bez(*seg,1); ang=math.degrees(math.atan2(dy,dx))
    leaves.append((x,y,ang+random.uniform(-12,12),1.3,tipbad))
for l in limbs: along(l,4,.5,.085)
for i,b in enumerate(br): along(b,3,.22,.125,tipbad=(i==6))
out.append('<g class="tr-leaves">')
for i,(x,y,a,s,bad) in enumerate(leaves):
    tone=' tr-l2' if i%3==0 else ''
    d=0.9+0.012*i
    if bad:
        out.append('<g transform="translate(%s %s)"><g class="tr-fall"><path class="tr-leaf tr-bad" style="--a:%sdeg;--d:%ss" d="%s"/><path class="tr-x" d="M 4 -8 l 14 16 M 18 -8 l -14 16"/></g><path class="tr-leaf tr-new" style="--a:%sdeg" d="%s"/></g>'%(f(x),f(y),f(a),f(d),leaf(s),f(a),leaf(s)))
        sys.stderr.write('bad leaf at %s %s\n'%(x,y))
    else:
        out.append('<g transform="translate(%s %s)"><path class="tr-leaf%s" style="--a:%sdeg;--d:%ss" d="%s"/></g>'%(f(x),f(y),tone,f(a),'%.2f'%d,leaf(s)))
out.append('</g>')
xs=[l[0] for l in leaves]; ys=[l[1] for l in leaves]
sys.stderr.write('leaves %d x %.0f..%.0f y %.0f..%.0f\n'%(len(leaves),min(xs),max(xs),min(ys),max(ys)))
print('\n'.join('          '+o for o in out))
