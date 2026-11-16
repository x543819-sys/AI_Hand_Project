# GitHub 参考筛选

查阅日期：2026-11-16。已阅读以下仓库的相关 README、目录或具体代码，按当前项目的识别与输出问题筛选。当前 v0.4 的控制代码为本项目实现，没有整段移植这些仓库代码。

| 项目 | 可借鉴部分 | 不直接采用的部分 | 许可观察 |
| --- | --- | --- | --- |
| [Kazuhito00/hand-gesture-recognition-using-mediapipe](https://github.com/Kazuhito00/hand-gesture-recognition-using-mediapipe) | 相对关键点归一化、采集训练样本、静态手势与轨迹分类分开 | 示例依赖 MediaPipe 0.8.1；app.py 使用 mp.solutions，轨迹历史长度固定 16 帧，不能直接搬到当前 Tasks 环境，也需要评估等待成本 | README 标明 Apache-2.0 |
| [HarishDvs/gesture-enabled-presentation](https://github.com/HarishDvs/gesture-enabled-presentation) | ppt_control_v2.py 用 COM 访问 SlideShowWindow.View，支持直接操作 PPT | slideshow 变量被赋成整数后又作为对象调用；GUI、语音识别和控制逻辑耦合，不能整体移植 | GitHub 元数据标明 MIT |
| [Pdanulya/Hand-Gesture-Smart-Presentation-Controller](https://github.com/Pdanulya/Hand-Gesture-Smart-Presentation-Controller) | 滑动检测、锁定、指示与笔画撤销分模块 | swipe_detector.py 等待 12 帧、阈值为画宽 0.18、冷却 1.2 秒；max_y_drift 参数未用于最终判定，且仍通过 PyAutoGUI 输出，不能解决当前的小视野和输出确认问题 | 已读取的根目录未见 LICENSE；仅参考设计 |
| [MoonshotAI/MoonshotAI-Cookbook](https://github.com/MoonshotAI/MoonshotAI-Cookbook) | 官方 API 示例组织、自动重连和缓存示例，可用于之后的模型接入层 | 示例目录不是完整 PPT 摘要系统；不需要为单页摘要先引入完整 Agent 框架 | 本次仅读取示例，不复制实现 |
| [google-ai-edge/mediapipe-samples](https://github.com/google-ai-edge/mediapipe-samples/tree/main/examples/hand_landmarker) | 当前 Hand Landmarker 接口与模型使用方式，后续双手跟踪的基础 | 不包含业务上的 T 触发防重复、PPT 输出确认或 LLM 摘要 | 官方示例，具体复用遵循对应文件许可 |

## 本项目的取舍

1. 动作使用手掌本身的位置变化，并按手掌宽度适配，降低对摄像头视野和甩动速度的要求。
2. PPT 使用原生放映接口，并读取页码确认。原生键盘事件发出不再等同于翻页成功。
3. 在摘要功能中复用当前页导出工具，先接通手动按钮链路，再添加双手 T。
4. 如需训练识别器，借鉴数据采集和归一化思路，按参与者或录制批次划分训练／测试；不把公开示例的演示效果当作本项目的准确率。

官方接口资料：[PowerPoint SlideShowWindow](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.slideshowwindow)、[Kimi API 概览](https://www.kimi.com/help/kimi-api/api-overview)、[智谱视觉模型](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-4.6v)。
