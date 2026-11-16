# v0.7.2 · Model ID 与失败详情

星图模型目录已核对（2026-11-16）：

| 页面展示名 | 请求 Model ID | 目录支持的输入 |
|---|---|---|
| Kimi-K3 | kimi-k3 | text / image_url / video_url |
| Kimi-K2.6 | kimi-k2.6 | text / image_url / video_url |

[官方公开目录](https://ai.csdn.net/api/model/v1/goods/modelsV2?page=1&size=100&search=Kimi) 的 id 字段为实际请求值，name 为展示名。API 示例中 model 字段应使用实际 ID。账号权限与套餐覆盖仍以当前账号为准。

摘要窗口的 Model ID 可以下拉选择上述两个 ID，也可手动填写其他视觉模型。仅对已核对的这两个星图 ID 修正大小写，其他平台和未知模型保持原样。

HTTP 400 不能唯一定位原因。本版展示服务返回的结构化错误 message/msg（隐藏密钥和图片数据）；不显示整个原始响应，不自动重试。移除星图请求中的额外 thinking 参数，以最小视觉请求提高模型兼容性。当前未使用真实密钥验证推理。

修复摘要窗口底部按钮被挤出：优先保留复制/继续/关闭按钮，预览随高度缩小。

# 星图接入（v0.7.1）

上一版仅提供智谱、Kimi 官方地址。星图密钥不能直接拿去访问它们的官方接口；401 只能说明该请求未通过鉴权，不能据此判定星图账号里的密钥失效。

## 配置

重启 run.bat，打开 AI 摘要，在服务下拉框选择与账号计费方式对应的入口：

| 服务选项 | Base URL | 计费 |
|---|---|---|
| 星图 Token Plan | https://ai.csdn.net/api/model/token/v1 | 消耗套餐 Credits |
| 星图 按量付费 | https://ai.csdn.net/api/model/v1 | 从账户余额扣费，不消耗套餐额度 |

程序自动拼接 /chat/completions。不会在失败后自动切换到余额入口。

Model ID 请从星图模型广场复制，选择支持图片输入且账号有权限的模型。本版不猜测可用 Model ID，切换到星图时模型栏留空，需要填写。不要使用仅支持文本的模型；Coding Plan 的编程模型是否支持图片、套餐是否覆盖该调用，请以星图当前文档及账号权限为准。

API Key 填入星图创建的密钥。切换服务会清空密钥输入框（如果该服务在本次运行里已经填写过，则恢复该服务自己的密钥）。密钥不写进配置文件。

## 自定义兼容服务

可填写 HTTPS Base URL，例如 https://example.com/v1，或完整的 /chat/completions 地址；再填写该平台的视觉模型 ID 与密钥。自定义请求不附带智谱/Kimi 专用思考参数。

## 判断错误

- HTTP 401：检查平台与地址是否配对、是否完整复制该平台密钥。
- HTTP 400/404：核对真实 Model ID、图片输入支持和接口地址。
- HTTP 402/403/429：检查额度、套餐权限及限流。

当前只做了地址、请求格式和配置界面测试，未使用真实星图密钥调用模型。模型可用性、图片输入和计费需要用你的账号验收。

官方依据（2026-11-16 核对）：
- [文本对话 API](https://ai.csdn.net/models/doc/%E6%96%87%E6%9C%AC%E5%AF%B9%E8%AF%9D%2F%E6%96%87%E6%9C%AC%E5%AF%B9%E8%AF%9DAPI)
- [选择 API 入口](https://ai.csdn.net/models/doc/%E5%87%86%E5%A4%87%E5%B7%A5%E4%BD%9C%2F%E9%80%89%E6%8B%A9API%E5%85%A5%E5%8F%A3)

官方文档是前端动态页面，接口内容由其公开文档资源与 doc-env-placeholders 脚本渲染。本轮读取了对应官方资源，未登录账号或读取密钥。
