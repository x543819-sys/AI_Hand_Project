"""Local test harness. Synthetic hand input enters only through this tool's stdin."""
from pathlib import Path
import json
from queue import Queue
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from airpresent.gestures import Observation, Gesture
from airpresent.tracker import Frame
from airpresent.viewer3d.server import Runtime, create_server


def main():
    inputs={'pose':'none','x':.5,'y':.5}
    class Worker:
        def __init__(self,*args):
            self.messages=Queue();self.running=False;self.thread=None
        def start(self):
            self.running=True;self.messages.put(('ready','测试相机：合成输入，未打开设备'))
        def stop(self):self.running=False
        def latest(self):
            if not self.running:return None
            pose=inputs['pose']
            obs=Observation() if pose=='none' else Observation(Gesture.PINCH_NEXT if pose=='pinch' else Gesture.UNKNOWN,
                (inputs['x'],inputs['y']),pinch_released=pose=='release')
            return Frame(np.zeros((240,320,3),dtype=np.uint8),obs,time.monotonic(),30,1)
    runtime=Runtime(Path(__file__).resolve().parents[1],Worker)
    server,token=create_server(runtime)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def read():
        for line in sys.stdin:
            try:inputs.update(json.loads(line))
            except ValueError:pass
    threading.Thread(target=read,daemon=True).start()
    print(json.dumps({'port':server.server_port,'token':token}),flush=True)
    try:
        while not runtime.stop.wait(.015):runtime.poll()
    finally:
        runtime.close();server.shutdown();server.server_close()


if __name__=='__main__':main()
