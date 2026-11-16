# 三维工作台：GitHub 调研与取舍

核对日期：2026-11-16。新模块由本项目独立编写；实际引入的是 Three.js 官方固定版本及其 MIT 许可证。模型为程序生成的示意结构，没有复制参考仓库里的模型素材。

## 1. collidingScopes/3d-model-playground

- [仓库](https://github.com/collidingScopes/3d-model-playground)
- 复核提交：90e681d955baafd46bfa08c62efb9a9af8fe0371
- 阅读 README.md、game.js，重点看 interactionMode、捏合抓取状态、旋转位移与双手缩放。
- 吸收：捏合形成操作离合；明确选择旋转/缩放等模式；手势与视觉反馈结合。
- 调整：所读代码捏合阈值为屏幕像素 45，平滑系数固定为每帧 0.4。本项目沿用已有手掌比例归一化、捏合进入/退出阈值与有效松开证据，渲染插值按时间计算。增加切换模式先松开、短时确认、异常位移和帧间隔保护。
- 首版采用单手捏合小幅移动，避免双手长期悬空；双手缩放作为后续可选交互。
- 许可证：README 声明 MIT；所查根目录未找到独立 LICENSE。本轮只借鉴交互思路，未复制源码或素材。

## 2. donmccurdy/three-gltf-viewer

- [仓库](https://github.com/donmccurdy/three-gltf-viewer)
- 复核提交：e10c599170ae0552fd74660bce15fbbe93f7f11a
- 阅读 src/viewer.js 与 LICENSE。
- 吸收：包围盒计算、居中和适配视角、模型替换时释放几何体/材质/纹理。
- 取舍：完整查看器支持多类压缩和环境贴图；本版先支持资源内嵌、未压缩 GLB，不加载在线解码器或外部纹理。
- 许可证：MIT。本轮未直接复制该查看器源码。

## 3. V1nc3ntL1ang/Gest2Act

- [仓库](https://github.com/V1nc3ntL1ang/Gest2Act)
- 复核提交：930a540154a24027a6254382343e9573e503b6b8
- 阅读 README.md、viewer.js 与根目录。
- 吸收：Python 识别与浏览器三维渲染分离，模型显示与手势识别分别调试。
- 调整：使用同源、仅回环服务和随机会话令牌；只发送最新状态，不排队积压。保留鼠标操作，启动时不自动开摄像头。
- 许可证：本轮所查根目录未见 LICENSE；未复制源码、训练模型或三维模型。

## 4. mrdoob/three.js（实际依赖）

- [官方仓库](https://github.com/mrdoob/three.js/tree/r180)
- 标签 r180，提交 0af9729d0c143a86a1d725d6e2c3ad83301f3f34。
- 引入 three.module.min.js、three.core.min.js、OrbitControls.js、GLTFLoader.js、BufferGeometryUtils.js。
- 原 MIT 许可证位于 airpresent/viewer3d/web/vendor/LICENSE-three.txt；来源与 SHA256 位于同目录 manifest.json。
- 所有渲染依赖随项目本地提供，浏览器验证没有外部请求。

## 后续研究方向

本版本是规则手势控制的交互展示原型，不声称手势识别算法创新。个性化手势训练尚未实现。

下一阶段建议单独完成：用户样本采集、关键点归一化、训练/验证分离、自定义静态手势分类与命令映射，再比较跨用户准确率、误触发率、任务完成时间。先采集自然放松、遮挡和相似动作等负样本，避免只在训练手势上演示成功。
