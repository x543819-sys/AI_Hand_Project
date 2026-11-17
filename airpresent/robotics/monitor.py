"""Always-on-top controls and a view drawn exclusively from actual joint feedback."""
import math
import tkinter as tk
from tkinter import ttk
from .kinematics import L1,HEIGHT,fk


def arm_points(q):
    yaw,shoulder,_=q
    elbow=(L1*math.cos(shoulder)*math.cos(yaw),L1*math.cos(shoulder)*math.sin(yaw),HEIGHT+L1*math.sin(shoulder))
    return [(0.,0.,0.),(0.,0.,HEIGHT),elbow,fk(q)]


def paint_arm(canvas,q,bounds,plane='xy',trail=(),origin=None):
    x0,y0,x1,y1=bounds;tag='arm_feedback';canvas.delete(tag)
    canvas.create_rectangle(x0,y0,x1,y1,fill='#172936',outline='#3d5968',tags=tag)
    scale=min((x1-x0-50)/.75,(y1-y0-55)/.62)
    def project(p):
        if plane=='xy':return (x0+(x1-x0)/2+p[1]*scale,y1-26-p[0]*scale)
        return (x0+30+p[0]*scale,y1-26-p[2]*scale)
    canvas.create_text(x0+10,y0+16,anchor='w',text='实际姿态 · '+('XY 俯视' if plane=='xy' else 'XZ 侧视'),fill='#b9cbd8',font=('Microsoft YaHei UI',10),tags=tag)
    coordinates=[project(p) for p in arm_points(q)]
    for i,(a,b) in enumerate(zip(coordinates,coordinates[1:])):
        canvas.create_line(*a,*b,fill=('#6f8795','#65e0bc','#b9cbd8')[i],width=8,tags=tag)
    for x,y in coordinates:canvas.create_oval(x-5,y-5,x+5,y+5,fill='#ffcf6e',outline='',tags=tag)
    if len(trail)>1:
        points=[v for p in trail for v in project(p)]
        canvas.create_line(*points,fill='#ffaf60',width=3,tags=tag)
    if origin is not None:
        distance=math.dist(origin,fk(q))*1000
        canvas.create_text(x1-10,y0+16,anchor='e',text='位移 %.1f mm'%distance,fill='#65e0bc',font=('Microsoft YaHei UI',10),tags=tag)
    return coordinates


class Monitor:
    def __init__(self,app):
        self.app=app;self.key=None;self.window=tk.Toplevel(app.root)
        self.window.title('AirHand · 悬浮控制');self.window.geometry('450x620+30+70')
        self.window.configure(bg='#111b26');self.window.attributes('-topmost',True)
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.bind('<space>',lambda event:app.pause());self.window.bind('<Escape>',lambda event:app.pause())
        tk.Label(self.window,textvariable=app.control,bg='#111b26',fg='#65e0bc',font=('Microsoft YaHei UI',12),wraplength=420).pack(fill='x',padx=10,pady=(10,4))
        tk.Label(self.window,textvariable=app.hint,bg='#111b26',fg='#b9cbd8',wraplength=420,justify='left').pack(fill='x',padx=10)
        self.canvas=tk.Canvas(self.window,bg='#172936',height=230,highlightthickness=0);self.canvas.pack(fill='both',expand=True,padx=10,pady=7)
        self.plane=tk.StringVar(value=app.arm_plane)
        row=tk.Frame(self.window,bg='#111b26');row.pack(fill='x',padx=10)
        ttk.Radiobutton(row,text='XY 俯视',variable=self.plane,value='xy').pack(side='left')
        ttk.Radiobutton(row,text='XZ 侧视',variable=self.plane,value='xz').pack(side='left')
        ttk.Button(row,text='显示主面板',command=app.show_main).pack(side='right')
        grid=tk.Frame(self.window,bg='#111b26');grid.pack(fill='x',padx=10,pady=6)
        self.buttons=[]
        for i,(direction,title) in enumerate([('x+','伸出'),('x-','收回'),('y+','侧移+'),('y-','侧移−'),('z+','抬高'),('z-','降低')]):
            button=ttk.Button(grid,text=title,command=lambda d=direction:app.press_jog(d))
            button.grid(row=i//3,column=i%3,sticky='ew',padx=2,pady=2);self.buttons.append(button)
        grid.columnconfigure((0,1,2),weight=1)
        row=tk.Frame(self.window,bg='#111b26');row.pack(fill='x',padx=10,pady=(0,5))
        self.hand=ttk.Button(row,text='启用手势',command=app.toggle_control);self.hand.pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='摄像头开关',command=app.toggle_camera).pack(side='left',fill='x',expand=True,padx=4)
        ttk.Button(row,text='停止 / 空格',command=app.pause).pack(side='left',fill='x',expand=True)
        self.info=tk.StringVar()
        tk.Label(self.window,textvariable=self.info,bg='#111b26',fg='#b9cbd8',wraplength=420).pack(fill='x',padx=10,pady=(0,8))

    def render(self):
        state=self.app.feedback;q=state.get('actual_q');tip=state.get('actual_tip')
        ready=state.get('ready') and not self.app.closing
        for button in self.buttons:
            desired='normal' if ready else 'disabled'
            if str(button.cget('state'))!=desired:button.configure(state=desired)
        self.hand.configure(text='停用手势' if self.app.enabled else '启用手势')
        rate=state.get('_sim_rate')
        self.info.set(('仿真 %.2f× · '%rate if rate is not None else '')+('实际末端：%.3f / %.3f / %.3f m'%tuple(tip) if tip else '等待实际反馈'))
        if q:
            key=(tuple(round(v,4) for v in q),self.plane.get(),self.canvas.winfo_width(),self.canvas.winfo_height())
            if key!=self.key:
                paint_arm(self.canvas,q,(0,0,max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height())),self.plane.get(),self.app.arm_trail,self.app.arm_origin)
                self.key=key

    def close(self):
        self.window.destroy();self.app.monitor=None;self.app.show_main()
