# 用户自选视频生成 API

适用应用版本 `adbb539`。

镜序提供“视频生成 API”服务、独立生成页面和“API 视频生成”画布节点。服务地址、密钥、模型由每个用户自行配置，配置按用户隔离。视频通过供应商生成，平台负责排队、查询、下载验证与私有保存。原本地图片/字幕合成保留在单独选项卡。

## 配置步骤

1. 打开“账号与服务配置”，服务类型选择“视频生成 API”。填写供应商名称、HTTPS Base URL、模型ID和自己的Key。
2. 按供应商文档修改“视频接口映射”。AutoDL H3 和 Happy Pet 可先载入对应模板，再核对路径、鉴权、状态字段与分辨率参数。
3. 在视频生成页选择服务，填写提示词、时长和尺寸，按需要选择参考图和参考音频。点击提交后，Worker 将按队列顺序调用供应商，费用以供应商账单为准。
4. 在任务中心查看进度、原供应商任务ID、预览及下载；画布也可添加同类节点，接入剧本或参考图片。

## 支持范围

支持HTTPS/443公网JSON接口：POST提交，异步GET查询或同步返回成片URL；单个可配置鉴权头（例如Authorization+Bearer前缀，或X-API-Key+空前缀）。不执行任意代码，不承诺兼容所有厂商。multipart文件上传、HMAC签名、OAuth换取令牌、WebSocket或非JSON响应需要另外实现专用适配器。

Base URL中的路径作为前缀保留。例如Base URL为`https://供应商域名/v1`、submit_path为`/videos`，最终提交到`/v1/videos`。路径不允许替换域名。密钥只填专用API Key字段，不写入JSON模板。

异步示例（字段名须按真实文档修改）：

```json
{
  "mode": "async",
  "submit_path": "/videos",
  "poll_path": "/videos/{{task_id}}",
  "cancel_path": "",
  "cancel_method": "POST",
  "content_path": "",
  "auth_header": "Authorization",
  "auth_prefix": "Bearer ",
  "request_body": {
    "model": "{{model}}",
    "prompt": "{{prompt}}",
    "duration": "{{seconds}}",
    "size": "{{size}}"
  },
  "task_id_field": "data.id",
  "status_field": "data.status",
  "progress_field": "data.progress",
  "video_url_field": "data.video_url",
  "success_values": ["completed", "succeeded", "success"],
  "failure_values": ["failed", "error", "cancelled", "canceled"],
  "poll_seconds": 5
}
```

字段提取使用点分隔：`data.id`、`data.result.url`、`data.0.url`。不支持任意JSONPath表达式或代码。若接口同步返回成片URL，mode设为sync。若需以相对路径下载成片，可配置content_path，例如`/videos/{{task_id}}/content`，同源请求附带鉴权。

整字段占位符保留值的类型。`"duration":"{{seconds}}"` 发送整数，`"images":"{{images_urls}}"` 发送数组。参考图可用 Base64、Data URL 或签名链接。按位置映射时用 `{{image_url_0}}` 至 `{{image_url_8}}`，参考音频用 `{{audio_url_0}}` 至 `{{audio_url_2}}`。供应商可从 `PUBLIC_ORIGIN` 对应的公网 HTTPS 入口读取签名素材。渲染 AutoDL 工作流请求时会省略空字符串字段。

独立视频页接受 1–30 整数秒。尺寸选项包括 480p、768p、1080p 的横屏和竖屏，以及 480p、768p 方形。提供参考图与音频前，先确认具体工作流支持相应输入和时长。画布每次执行最多包含一个本地合成或 API 视频节点。下载需要通过 MP4 校验，默认上限为 100 MB，且受用户存储配额限制。

`{{size}}` 会把部分页面选项转换为像素尺寸字符串。例如 `768p横` 会变成 `1280x720`。如果供应商要求自己的枚举值，可以把模板的 `resolution` 写为对应的固定值。西乡塘动态版实测的 H3 请求使用固定的 `768p横`，每段提交 15 秒。

## 费用、恢复和取消

- 平台提交一次视频生成扣减一次平台调用次数；轮询不再次扣减生成次数。供应商计费规则独立，平台次数不等于供应商余额。
- 平台不会自动重复POST生成请求。提交前先记录sending，响应中的任务ID立即持久保存。提交结果未知且没有ID时，不盲目重发。
- 有原任务ID的失败/中断/本地取消任务，可以“查询原任务 / 核查后重试”，继续查询与下载，不另建供应商生成任务。
- 确定另起一次生成时，点“重新生成（可能再次计费）”。任务详情会在提交期间禁用重试按钮，同一页面上同一次操作响应失败时，再点该操作会复用幂等键。
- 取消本地任务不保证供应商停止或退费。配置cancel_path时平台会尝试对应请求，并记录确认情况；未配置或无法确认时显示供应商可能继续运行。
- 网络响应有时间和大小上限；异步任务最多等待约12分钟，之后保留原ID供稍后查询。供应商可能在平台超时后继续生成。

## 安全与限制

沿用Fernet密钥加密、用户归属、CSRF和配额检查；公网地址与DNS校验、TLS固定解析IP、禁自动重定向。CDN下载不携带供应商鉴权头；仅同源下载附带。签名下载URL只用于当次下载，不作为公开链接泄漏给其他用户。
活动任务期间限制修改和删除相应视频配置。画布保存和连线只修改项目，执行节点才会调用供应商。给 H3 传入参考音频时，使用独立视频生成页或 `video_api` 请求的 `audio_ids`。画布的配音合成用于视频生成后的旁白处理。[画布流程](canvas-flow-guide.md)


## 验收记录

自动化覆盖提交、状态查询、CDN 下载、鉴权预览和恢复时复用远程 ID。2026-11-21 的西乡塘案例实测 AutoDL H3 分段生成和 IndexTTS2 配音。收到四段约 15 秒的视频后，由 Windows 本机 FFmpeg 剪成一分钟成片。模板参数需按自己的账号与工作流核对。[测试与验收](test-report.md) · [早期 405 修复记录](autodl-405-fix.md)
