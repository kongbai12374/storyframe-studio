# AutoDL H3 HTTP 405 排查

## 当时的问题

早期任务使用通用 `/videos` 路径，AutoDL 对应的是 ComfyUI 工作流入口。已验证的旧工作流提交路径为 `/api/v1/comfyui/comfyui_workflow/minimax_h3_b99_001`。早期模板包含当时核对过的 `736p横`，用于复现这次问题。[原始配置](autodl-h3-video-config.json)

修正后，提交解析 `data.task_id`，用该 ID 查询 `/api/v1/comfyui/comfyui_workflow/result/{{task_id}}`。查询读取 `data.status` 和 `data.results.0.url`，匹配 `SUCCESS` 或 `completed`。该工作流使用 `Authorization`，当时的映射为空认证前缀。23 项专项及重试测试通过，未在该次修复中重新提交真实生成请求。

## 现在怎么查

1. 在「账号与服务配置」选择与模型一致的 H3 工作流模板。检查域名、提交路径和查询路径有无重复路径前缀，并按工作流文档核对鉴权。
2. 当前的 AutoDL 文生视频和多图多音频是不同模板。分辨率、时长和是否能收参考音频以对应工作流为准。西乡塘已用当前配置完成分段生成。[视频 API 与分辨率映射](video-api-guide.md) · [实测作品](canvas-flow-guide.md)
3. 任务已经取得供应商 ID 时，先从任务详情查询原任务。旧任务保留创建时的配置快照。想用改后的配置发起新生成，核查旧任务后使用「重新生成（可能再次计费）」。
