"""Small authenticated local TCP protocol; no camera images cross the bridge."""
import hmac
import json
import math
import socket
import time
from dataclasses import dataclass
from ..gestures import Gesture, Observation

MAX_PACKET=8192
JOG_VELOCITIES={'x+':(.025,0.,0.),'x-':(-.025,0.,0.),'y+':(0.,.025,0.),
                'y-':(0.,-.025,0.),'z+':(0.,0.,.025),'z-':(0.,0.,-.025),None:(0.,0.,0.)}


@dataclass(frozen=True)
class Jog:
    direction: str | None = None


def decode(packet, token, previous, now):
    if not isinstance(packet,dict) or not isinstance(packet.get('token'),str) or not hmac.compare_digest(packet['token'],token):
        raise ValueError('Authentication failed')
    if packet.get('hello') is True:return None
    seq=packet.get('seq');stamp=packet.get('stamp');age=packet.get('age_ms')
    if type(seq) is not int or seq<=previous:raise ValueError('Out of order')
    if type(stamp) not in (float,int) or not math.isfinite(stamp):raise ValueError('Invalid timestamp')
    if not -.1<=now-stamp<=.3:raise ValueError(f'Stale packet ({now-stamp:.3f}s)')
    if type(age) not in (float,int) or not math.isfinite(age) or not 0<=age<=250:raise ValueError('Stale camera frame')
    if type(packet.get('enabled')) is not bool or packet.get('mode') not in ('xy','xz'):raise ValueError('Invalid control flags')
    if packet.get('source')=='buttons':
        direction=packet.get('jog')
        if direction is not None and (not isinstance(direction,str) or direction not in JOG_VELOCITIES):raise ValueError('Invalid jog direction')
        return seq,packet['enabled'],packet['mode'],Jog(direction if packet['enabled'] else None)
    raw=packet.get('observation',{})
    if not isinstance(raw,dict):raise ValueError('Invalid observation')
    gesture=Gesture(raw.get('gesture',Gesture.NONE.value));point=raw.get('pointer')
    if point is not None and (not isinstance(point,list) or len(point)!=2 or not all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in point)):
        raise ValueError('Invalid point')
    release=raw.get('released')
    if release is not None and type(release) is not bool:raise ValueError('Invalid release evidence')
    palm=raw.get('palm')
    if palm is not None and (not isinstance(palm,list) or len(palm)!=2 or not all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1 for v in palm)):
        raise ValueError('Invalid palm')
    return seq,packet['enabled'],packet['mode'],Observation(gesture,tuple(point) if point is not None else None,
        tuple(palm) if palm is not None else None,pinch_released=release)


class Client:
    def __init__(self,host,port,token):
        self.sock=socket.create_connection((host,port),timeout=1)
        self.sock.settimeout(2)
        self.stream=self.sock.makefile('rb')
        self.token=token;self.seq=0
        samples=[]
        for _ in range(5):
            started=time.monotonic();answer=self.exchange({'token':token,'hello':True});ended=time.monotonic()
            samples.append((ended-started,answer['server_time']-(started+ended)/2))
        self.offset=min(samples)[1]

    def exchange(self,packet):
        self.sock.sendall(json.dumps(packet,allow_nan=False).encode()+b'\n')
        data=self.stream.readline(MAX_PACKET+1)
        if not data or len(data)>MAX_PACKET:raise ConnectionError('Bridge disconnected (response bytes: '+str(len(data))+')')
        answer=json.loads(data)
        if answer.get('error'):raise ConnectionError(answer['error'])
        return answer

    def send(self,observation,enabled=False,mode='xy',age_ms=0):
        return self._send({'age_ms':age_ms,'enabled':enabled,'mode':mode,'observation':{
            'gesture':observation.gesture.value,'pointer':observation.pointer,'palm':observation.palm,'released':observation.pinch_released}})

    def send_jog(self,direction=None):
        if direction not in JOG_VELOCITIES:raise ValueError('Invalid jog direction')
        return self._send({'age_ms':0,'enabled':direction is not None,'mode':'xy','source':'buttons','jog':direction})

    def _send(self,payload):
        self.seq+=1
        started=time.monotonic()
        answer=self.exchange({'token':self.token,'seq':self.seq,'stamp':started+self.offset,**payload})
        ended=time.monotonic()
        # Host and VM monotonic clocks may drift. Refresh only on a fast round trip;
        # the receiver still rejects delayed packets and enforces its own watchdog.
        if ended-started<.15:self.offset=answer['server_time']-(started+ended)/2
        return answer

    def close(self):
        try:self.stream.close()
        finally:self.sock.close()
