# 轻量模板对照

对照 `adbb539` 的应用实现，以当前项目文档为操作依据。[原始需求](../codex-drama-platform-prompts.md) · [轻量开发基线](../codex-drama-platform-prompts-lightweight.md)

| 能力 | 当前实现 |
|---|---|
| 应用与数据 | Django REST API、React、TypeScript、SQLite WAL 与本地私有素材。Web 和 Worker 分为两个应用容器。 |
| 创作流程 | 手动编辑或用 LLM 生成剧本，编辑分镜，上传图片和配音，按画布依赖串行执行。 |
| 视频与音频 | 720p 本地合成与中文字幕；配置外部图片、TTS、视频接口，支持远端任务查询及配音混合。 |
| 执行可靠性 | 持久队列、幂等、快照、资源准入、取任务租约、取消和中断恢复。带检查点的全流程按节点记录结果。 |
| 部署 | Nginx 前端与 HTTPS、同源 Session/CSRF、中文管理后台、定时备份、隔离恢复。 |

Django 业务模型集中在 `core`。React 使用 React Router 7 和 React Flow。每次画布执行最多包含一个本地合成或 API 视频节点，多个片段可分任务生成后剪辑。供应商服务按实际模型和账号权限配置，实测案例见[画布流程](canvas-flow-guide.md)。

通用多智能体、循环与并行画布、实时多人协作、WebSocket、向量检索、PDF 导出和对象存储仍属于原模板的扩展方向。[现行架构](architecture.md) · [验证情况](test-report.md)
