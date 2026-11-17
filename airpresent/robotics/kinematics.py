"""Analytic kinematics for the project's three-joint simulation arm."""
import math

L1, L2, HEIGHT = .28, .24, .20
JOINTS = ('base_yaw', 'shoulder', 'elbow')
HOME = (0., .65, -1.20)
LIMITS = ((-1.4,1.4),(-.7,1.3),(-1.8,-.15))


def simulation_dt(previous,current):
    if previous is None or current is None:return 0.
    if not math.isfinite(previous) or not math.isfinite(current):return 0.
    return min(.05,max(0.,current-previous))


def fk(q):
    yaw,s,e=q
    r=L1*math.cos(s)+L2*math.cos(s+e)
    return (r*math.cos(yaw),r*math.sin(yaw),HEIGHT+L1*math.sin(s)+L2*math.sin(s+e))


def ik(point):
    if len(point)!=3 or not all(math.isfinite(x) for x in point):return None
    x,y,z=point;r=math.hypot(x,y)
    if not .20<=r<=.49 or not .14<=z<=.60:return None
    h=z-HEIGHT;c=(r*r+h*h-L1*L1-L2*L2)/(2*L1*L2)
    if not -1<=c<=1:return None
    e=-math.acos(c)
    s=math.atan2(h,r)-math.atan2(L2*math.sin(e),L1+L2*math.cos(e))
    q=(math.atan2(y,x),s,e)
    return q if all(lo<=v<=hi for v,(lo,hi) in zip(q,LIMITS)) else None


def step(point,velocity,dt):
    if not 0<dt<=.1 or not all(math.isfinite(x) for x in velocity):return None
    desired=tuple(p+v*dt for p,v in zip(point,velocity))
    q=ik(desired)
    return (desired,q) if q else None
