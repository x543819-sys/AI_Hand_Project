"""Windows launcher for the local WSL simulation; no ROS Python on Windows."""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import time
import uuid


WSL=r'C:\Program Files\WSL\wsl.exe'


def wsl_output(*args):
    try:
        p=subprocess.run([WSL,'-d','Ubuntu-24.04','--exec',*args],capture_output=True,timeout=60,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Ubuntu 启动超过 60 秒，请检查 WSL 是否能正常打开后再启动控制台。') from exc
    if p.returncode:raise RuntimeError('WSL 命令失败，请检查 Ubuntu-24.04 与 ROS 安装。')
    return p.stdout.decode('utf-8',errors='replace').strip()


class Session:
    def __init__(self, project_dir, gui=True):
        self.root=Path(project_dir).resolve();self.process=None;self.log=None;self.lockfile=None
        parent=self.root/'sessions'/'robotics';parent.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':
            import msvcrt
            self.lockfile=(parent/'launcher.lock').open('a+b');self.lockfile.seek(0)
            if not self.lockfile.read(1):self.lockfile.write(b'0');self.lockfile.flush()
            self.lockfile.seek(0)
            try:msvcrt.locking(self.lockfile.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:
                self.lockfile.close();raise RuntimeError('已有机械臂工作台在运行，请先关闭它。')
        self.folder=parent/('session_'+uuid.uuid4().hex[:10]);self.folder.mkdir()
        self.config=self.folder/'session.json'
        try:
            linux_root=wsl_output('wslpath','-u',str(self.root))
            linux_session=wsl_output('wslpath','-u',str(self.config))
            candidates=wsl_output('hostname','-I').split()
            host=next(str(ipaddress.IPv4Address(x)) for x in candidates if ':' not in x and ipaddress.ip_address(x).is_private)
            self.settings={'host':host,'token':secrets.token_urlsafe(32),'gui':bool(gui),'domain':80+secrets.randbelow(101)}
            self.config.write_text(json.dumps(self.settings),encoding='utf-8')
            command='source /opt/ros/jazzy/setup.bash && export PYTHONPATH='+shlex.quote(linux_root)+':"${PYTHONPATH:-}" && exec python3 -m airpresent.robotics.ros_session --session '+shlex.quote(linux_session)
            self.log=(self.folder/'launcher.log').open('wb')
            self.process=subprocess.Popen([WSL,'-d','Ubuntu-24.04','--exec','bash','-lc',command],stdout=self.log,stderr=self.log,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except Exception:
            self.close();raise

    def endpoint(self):
        if self.process.poll() is not None:raise RuntimeError('仿真进程已退出，请查看 '+str(self.folder))
        file=self.folder/'endpoint.json'
        try:
            data=json.loads(file.read_text(encoding='utf-8'))
            return data['host'],int(data['port']),self.settings['token']
        except (OSError,ValueError,KeyError):return None

    def request_gui(self):
        if self.process.poll() is not None:raise RuntimeError('仿真已退出，请重新启动控制台。')
        (self.folder/'open_gui').touch()

    def close(self):
        if hasattr(self,'folder'):(self.folder/'stop').touch()
        if self.process:
            try:self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:self.process.terminate()
        if self.log:self.log.close()
        if self.lockfile:
            self.lockfile.close();self.lockfile=None
