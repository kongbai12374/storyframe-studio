# API参考

基础路径/api/，登录使用Django Session cookie。首次写请求先GET /api/csrf/取得csrfToken，再在X-CSRFToken头传入。所有JSON写请求必须为对象。文件上传使用multipart/form-data。未登录403，参数400，越权/不存在404，版本冲突409，过大413，限流429，数据库繁忙503。

|方法|路径|用途|
|---|---|---|
|GET|csrf/|获得CSRF令牌|
|POST|auth/login/|username/password登录|
|POST|auth/logout/|登出|
|GET/PATCH|auth/me/|个人信息；name或old_password/password|
|GET|dashboard/|本人统计、存储与调用配额|
|GET/POST|scripts/|分页/搜索剧本；创建|
|GET/PUT/DELETE|scripts/{id}/|详情/条件更新/删除|
|POST|scripts/{id}/duplicate/|复制|
|GET|scripts/{id}/export/|Markdown下载|
|GET/POST|assets/|分页筛选或上传file与tags|
|GET/PATCH/DELETE|assets/{id}/|详情、修改tags、删除未引用素材|
|GET|assets/{id}/file/|鉴权流式读取；thumbnail=1读取缩略图|
|GET/POST|providers/|脱敏列表/保存配置|
|PUT/DELETE|providers/{id}/|更新/删除|
|POST|providers/{id}/test/|URL解析及密钥可读检查，不发送付费请求|
|GET/POST|canvases/|分页/创建项目|
|GET/PUT/DELETE|canvases/{id}/|读取/条件保存/删除|
|POST|canvases/{id}/run/|提交完整或选中节点及其依赖|
|GET/POST|jobs/|分页或提交compose/llm|
|GET|jobs/{id}/|阶段/进度/结果/最近100条日志|
|POST|jobs/{id}/cancel/|取消|
|POST|jobs/{id}/retry/|重试，可能付费时需要confirm_paid=true|
|GET|jobs/{id}/download/|预览；download=1下载|
|GET|/health/|web和worker心跳健康|

分页参数page、limit（最大100）；返回results、total、page、limit。素材支持q/kind/tag；剧本支持q。

创建剧本：
```json
{"title":"山间来信","style":"甜宠","synopsis":"久别后的重逢","scenes":[{"description":"山间日光","dialogue":"你好，世界。","duration":5,"image_id":1,"audio_id":null}]}
```
返回201，包含id、revision=1和完整内容。PUT提交当前revision，成功递增；旧revision返回409。

提交合成：
```json
{"kind":"compose","script_id":1,"use_tts":false,"idempotency_key":"client-generated-unique-key"}
```
返回202任务对象。重复同用户幂等键返回原任务，不重复排队。LLM请求使用kind=llm、synopsis、style；该操作可能产生供应商费用。

保存画布：
```json
{"name":"故事流程","revision":1,"document":{"nodes":[{"id":"note-1","type":"studio","position":{"x":0,"y":0},"data":{"kind":"note","label":"一个想法","text":"从这里开始"}}],"edges":[],"viewport":{"x":0,"y":0,"zoom":1}}}
```
执行请求含revision和idempotency_key，可加selected节点ID数组。只存便签的画布不可执行；非法连线、循环、越权引用和密钥字段会被拒绝。首版每次流程限一个视频合成节点，多分支仍串行。


## 文生图与删除更新（2026-11-07）

新增 POST /api/jobs/ kind=image_api（需confirm_paid）、图片类型供应商service=image、视频image_ids数组（最多9张）与 DELETE /api/jobs/{id}/（仅终态、引用保护、清理本地成片）。任务、素材、剧本和画布列表均支持批量删除。最新77项后端与8项前端通过，浏览器模拟验证通过。使用方式及协议限制见[文生图与删除说明](image-generation-guide.md)。未调用真实图片供应商。用户反馈现有视频生成已成功。
