# 用户自选视频生成 API

本次新增“视频生成 API”服务、独立生成页面和“API 视频生成”画布节点。服务地址、密钥、模型由每个用户自行配置，配置按用户隔离。视频通过供应商生成，平台负责排队、查询、下载验证与私有保存。原本地图片/字幕合成保留在单独选项卡。

## 配置步骤

1. 打开“个人与 API 配置”，服务类型选择“视频生成 API”。填写供应商名称、HTTPS Base URL、模型ID和自己的Key。
2. 按供应商文档修改“视频接口映射”。初始内容只是通用结构示例，不代表任何真实供应商都适用。
3. 到视频生成页选择该服务，填写提示词、时长和方向，可选参考图片。勾选发送数据及供应商费用确认后才可提交。
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

请求模板支持`{{model}}`、`{{prompt}}`、`{{seconds}}`、`{{size}}`、`{{image_base64}}`、`{{image_data_url}}`。整字段占位符会保留数值类型，例如`"duration":"{{seconds}}"`实际发送整数。参考图由私有素材读取后转为JPEG Base64；平台不会把无法被外部访问的本机素材地址当作公网链接。用户勾选参考图时，需要模板实际引用图像占位符。

时长1–60整数秒，横屏1280×720或竖屏720×1280；具体可用值仍由供应商决定。下载最大100MB且受存储配额限制，最长约60秒、分辨率不超过2048，验证为MP4后保存。供应商需按其能力返回可用格式。

## 费用、恢复和取消

- 平台提交一次视频生成扣减一次平台调用次数；轮询不再次扣减生成次数。供应商计费规则独立，平台次数不等于供应商余额。
- 平台不会自动重复POST生成请求。提交前先记录sending，响应中的任务ID立即持久保存。提交结果未知且没有ID时，不盲目重发。
- 有原任务ID的失败/中断/本地取消任务，可以“查询原任务 / 核查后重试”，继续查询与下载，不另建供应商生成任务。
- 如果确认需要另一次生成，使用“重新生成（可能再次计费）”并再次确认。供应商确已失败时，同样先核查后显式重新生成。
- 取消本地任务不保证供应商停止或退费。配置cancel_path时平台会尝试对应请求，并记录确认情况；未配置或无法确认时显示供应商可能继续运行。
- 网络响应有时间和大小上限；异步任务最多等待约12分钟，之后保留原ID供稍后查询。供应商可能在平台超时后继续生成。

## 安全与限制

沿用Fernet密钥加密、用户归属、CSRF和配额检查；公网地址与DNS校验、TLS固定解析IP、禁自动重定向。CDN下载不携带供应商鉴权头；仅同源下载附带。签名下载URL只用于当次下载，不作为公开链接泄漏给其他用户。
存在活动任务时暂不允许修改/删除视频API配置，避免改变正在运行任务的协议。画布每次仍最多一个本地合成或API视频节点，串行运行，保存及连线不会调用供应商。

## 验证结果（2026-11-07）

后端原有全量回归57项通过（含21项初版视频测试），视频专项补齐后22项通过；新增的完整适配器测试使用真实MP4样例，模拟提交202→查询完成→CDN下载→ffprobe验证→鉴权预览，确认只POST一次。前端8项回归和TypeScript生产构建通过。
这些是隔离测试与协议模拟。未配置真实供应商Key，未进行真实付费调用；实际模型权限、网络、额度和返回结构待用户配置后联调。
