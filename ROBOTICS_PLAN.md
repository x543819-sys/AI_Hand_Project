# v0.9 接入进展（2026-11-17）

三关节机械臂已接入真实 Gazebo：Windows 合成手势 → TCP → WSL ROS 2 → 解析 IK → JointTrajectoryController → gz_ros2_control，已通过实际关节位移、松手/断连停止与升降测试。Windows 摄像头工作台入口为 run_robot.bat，真人操作待试用。

这是完整 MoveIt Servo 路线之前的最小仿真闭环；当前没有使用 Servo，也没有夹爪物理抓放。具体使用、环境和限制见 ROBOT_ARM_GUIDE.md。

## 已安装环境

WSL 3.0.5、Ubuntu 24.04.5（WSL 2）、ROS 2 Jazzy、Gazebo Harmonic 8.15.0、gz_ros2_control 与 MoveIt 已在本机安装。

真实 ROS C++/Python 通信已通过；Gazebo 官方滑台在控制器 active 后执行目标 -0.4，实际回读 -0.3989327，验证了真实仿真控制与反馈链路。复验工具为 tools/verify_ros_sim_runtime.py，需要在 Ubuntu 中 source /opt/ros/jazzy/setup.bash 后运行，建议设置独立 ROS_DOMAIN_ID 与 Gazebo 分区。

当前 WSLg 使用 llvmpipe 软件渲染，GUI 加速/性能仍需优化。下面保留最初的调研方案与当时的检查记录，其中“未安装/未执行”描述的是调研时状态，以本文顶部及使用指南的当前进展为准。

# 历史调研：手势机械臂仿真接入方案

日期：2026-11-17。状态：已完成参考调研、环境检查及独立的手势速度意图原型；未运行 ROS、RViz、Gazebo 或真实机器人。现有 PPT 与三维工作台行为不变。

## 本机条件

`wsl --list --verbose` / `wsl --status` 返回未安装 WSL，退出码 1。PATH 中未找到 Docker。没有开始安装系统功能或 Linux 发行版。

推荐第一轮选 Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic + MoveIt 2 + gz_ros2_control。这是仍受支持的配套组合，不是当前最新发行版；选择它主要为匹配现有 Python 3.12 与参考工程。安装前需要确认可用磁盘、虚拟化、WSLg 图形与相机接入方式。

## 开源参考与取舍

### Shubhg1498/vision-single-arm-teleop

- [仓库](https://github.com/Shubhg1498/vision-single-arm-teleop)
- 阅读 README 和 ros2_ws/src/vdat_teleop/vdat_teleop/servo_twist_relay_node.py；树 SHA 33c6baad9680cb51666e7e6c38376492bb6a1874。
- 最接近目标：MediaPipe → 末端 TwistStamped → MoveIt Servo → ros2_control / gz_ros2_control → Gazebo Panda。参考其输入、限速中继与控制器分层。
- 中继代码包含输入超时、线速度限制、加速度限制与平滑。本项目先独立实现控制意图、捏合离合与超时；加速度限制、机器人状态反馈和碰撞约束交由后续仿真联调补齐。
- README 明确区分 RViz fake hardware 与 Gazebo 接触物理，且指出单目深度与实际抓取的操作困难。不会把 RViz 可视化或固定物体附着当成 Gazebo 抓取验证。

### flowercastle/ros2-gesture-gazebo-arm

- [仓库](https://github.com/flowercastle/ros2-gesture-gazebo-arm)，MIT。
- 阅读 README、目录结构；树 SHA cbc1a6eac62692a922a300668c236cf5aff02a39。
- 参考 Jazzy/Harmonic、控制器状态检查、先固定轨迹后手势的验证顺序。
- 不沿用旧 mp.solutions API，不复制降级依赖/破坏系统 Python 的命令，不采用宽泛 pkill 清理。README 的无重力展示方案不能作为后续物理抓取有效性的证据。

### kernelshreyak/gesture-controlled-arm

- [仓库](https://github.com/kernelshreyak/gesture-controlled-arm)
- 阅读 README，参考识别、重定向、仿真指令与反馈节点分离，以及合成输入先验收的做法。
- 该项目采用 Lyrical / Gazebo Sim 10.5 / Python 3.14；不与本轮 Jazzy/Harmonic 环境混装。其 README 对真人 GUI 和抓取实验的限制也有明确说明。
- 本轮没有复制第三方模型、控制器代码或安装脚本，各上游许可证仍需在选型确定后逐项核对。

## 目标架构

摄像头 → 已有 MediaPipe Tasks / 捏合识别 → HandVelocity 意图 → ROS 2 TwistStamped 适配 → MoveIt Servo → ros2_control → gz_ros2_control → Gazebo 机械臂。

从仿真 JointState / 控制器与 Servo 状态回读实际结果；界面显示的是实际反馈，不能只显示发送目标。

Windows 摄像头与 WSL 的接入需实测。可选 Windows 识别后桥接到 WSL，或 Linux 可用的 USB 相机；不能假设 WSL 默认就能读取笔记本摄像头。初次联调先用合成输入，避免相机与 ROS 故障混在一起。若跨系统桥接，需要独立配置会话、消息顺序/时间、断线停指令；不把现有仅回环的三维 API 直接暴露到外网。

## 第一版交互

- 明确启用后，先松开再捏合；短时确认后建立相对起点。
- 捏合后偏离起点形成速度摇杆：偏离越多速度越大；回到起点或松开停止。首版最大平移速度原型参数为 0.04 m/s，仅用于后续仿真调试。
- XY 平面操作与 XZ 深度操作显式切换；单目关键点 Z 不直接当作米制深度。
- 丢手、跟踪跳变、无效数据和 200ms 未更新输出零速度，并要求再次松开。ROS 接收端还需独立看门狗及订阅新鲜度检查，不能仅靠发送端。
- 夹爪开合与运动离合分开，避免捏合既驱动移动又反复开合夹爪。
- 禁用自动回零/复位运动；后续回零必须单独、明确触发。

现有原型 airpresent/robotics/intent.py 没有 ROS 导入、网络连接或硬件控制，也尚未接入相机与三维工作台。

## 验证顺序

1. 本机纯 Python：速度边界、松开停、丢手停、过期输入停、切换平面和异常输入。已通过 6 项专用测试。
2. Linux 环境：确认 ROS 2、Gazebo、控制器版本；运行官方 gz_ros2_control 示例并回读状态。尚未执行。
3. Panda 或适配机械臂：合成 TwistStamped 输入 → MoveIt Servo → Gazebo。验证指令轴向、实际关节反馈和停止延迟。尚未执行。
4. 接入真人手势，低速完成 XY 移动、明确深度切换和停住；统计任务完成时间与误触发。尚未执行。
5. 再做夹爪物理接触与抓放任务，保留重力、接触与摩擦，禁止用渲染附着替代物理验收。尚未执行。

原型限速与看门狗测试不构成碰撞安全、路径可达性、奇异位形处理或实机可用证明。本轮范围仅为仿真研究，不连接真实机械臂。

## 安装边界

WSL 安装涉及 Windows 系统功能、管理员权限、发行版下载，可能要求重启。需用户确认后再执行；不会自动重启计算机。安装命令以微软官方流程为准，Ubuntu 版本应明确选 24.04，而非随默认发行版变化。

## 官方依据

- [ROS/Gazebo 配套版本](https://gazebosim.org/docs/harmonic/ros_installation/)
- [MoveIt Servo](https://moveit.picknik.ai/main/doc/examples/realtime_servo/realtime_servo_tutorial.html)
- [Jazzy gz_ros2_control](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html)
- [WSL 安装与重启说明](https://learn.microsoft.com/en-us/windows/wsl/install)
