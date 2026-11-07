# AI 短剧生成智能体平台 — Codex 全流程开发提示词模板

> **用途**：将以下 Phase 0 ~ Phase 10 的提示词按顺序投喂给 Codex，引导其独立完成全流程开发。
> **运行环境**：2 核 2G 服务器
> **技术栈**：Python Django + React + TypeScript
> **交付物**：每个 Phase 末尾标注了该阶段需产出的文件，全部完成后汇总交付。

---

## Phase 0 — 项目初始化与技术选型

```text
你是一名资深 Python Django + React 全栈开发工程师，负责开发「AI 短剧生成智能体平台」。

当前环境：2 核 CPU / 2G 内存的 Linux 服务器。请据此选择轻量技术栈。

请完成以下初始化工作：

1. 后端项目结构（Django 4.2 + DRF）：
   - 项目名：drama_platform
   - 创建以下 App：users, scripts, assets, tasks, agents, studio, api_config
   - 配置 DRF、CORS、JWT 认证
   - 数据库：开发阶段用 SQLite，生产环境支持 PostgreSQL（通过环境变量切换）
   - 配置 Celery + Redis（Redis 同时作为缓存和消息队列）

2. 前端项目结构（React 18 + TypeScript + Vite）：
   - 项目名：drama-frontend
   - 使用 Ant Design 5.x 作为 UI 框架
   - 配置 Zustand 状态管理
   - 配置 React Router v6
   - 配置 Axios 拦截器（JWT 自动附加、401 自动跳转登录）

3. Docker 编排：
   - docker-compose.yml 包含：web(Django)、frontend(React/Nginx)、redis、celery-worker
   - 2核2G 适配：celery worker concurrency=2，worker 内存限制 512MB
   - .env.example 包含所有可配置项

4. 输出以下文件：
   - drama_platform/ 完整 Django 项目骨架
   - drama-frontend/ 完整 React 项目骨架
   - docker-compose.yml
   - .env.example
   - Makefile（包含 dev / build / up / down / logs / test 命令）
   - README.md（项目简介、技术栈、快速启动）
```

**Phase 0 交付物**：
- `drama_platform/` — Django 项目骨架
- `drama-frontend/` — React 项目骨架
- `docker-compose.yml`
- `.env.example`
- `Makefile`
- `README.md`

---

## Phase 1 — 用户系统与 API 配置中心

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成用户系统和 API 配置中心。

一、用户系统（users app）：
1. 自定义 User 模型（继承 AbstractUser），增加字段：
   - avatar（头像 URL）
   - role（admin / creator / viewer）
   - api_quota_remaining（剩余 API 调用额度）
2. 注册/登录/登出/刷新Token 接口（JWT）
3. 权限中间件：基于角色的接口访问控制
4. 用户 Profile 接口（修改昵称、头像、密码）

二、API 配置中心（api_config app）—— 核心功能：
用户可以自行配置各 AI 服务的 API 密钥和参数。

1. 数据模型 APIProvider：
   - provider_name: 供应商名称（如 openai / zhipu / baidu / stability / custom）
   - service_type: 服务类型（llm / tts / image_gen / video_gen / embedding）
   - api_key: 加密存储的 API Key
   - api_base_url: 自定义接口地址（支持私有部署模型）
   - model_name: 模型名称（如 gpt-4o / glm-4 / sd-xl）
   - config_params: JSONField，存储额外参数（temperature, max_tokens 等）
   - is_active: 是否启用
   - user: 关联用户（支持系统级和用户级配置）
   - priority: 优先级（同类型多配置时选择优先级最高的）

2. API Key 加密存储：
   - 使用 Django 的 Fernet 对称加密
   - 加密密钥从环境变量 ENCRYPTION_KEY 读取
   - 读取时自动解密，写入时自动加密
   - API 返回时脱敏显示（仅显示前4位和后4位）

3. 接口设计：
   - POST /api/config/providers/ — 新增 API 配置
   - GET /api/config/providers/ — 列表（脱敏）
   - PUT /api/config/providers/{id}/ — 修改配置
   - DELETE /api/config/providers/{id}/ — 删除配置
   - POST /api/config/providers/{id}/test/ — 测试连通性
   - GET /api/config/providers/by-service/{service_type}/ — 按服务类型获取最优配置

4. AI 服务统一调用层（services/ai_gateway.py）：
   - AIGateway 类，根据 service_type 自动选择配置
   - 支持 fallback：主配置失败时自动切换到备用配置
   - 统一错误处理和重试逻辑
   - 调用次数记录（用于额度管理）

输出文件：
- users/models.py, serializers.py, views.py, urls.py, permissions.py
- api_config/models.py, serializers.py, views.py, urls.py, encryption.py
- services/ai_gateway.py
- middleware/rbac.py
```

**Phase 1 交付物**：
- `users/` — 用户模型、认证、权限
- `api_config/` — API 配置模型、加密、测试连通性
- `services/ai_gateway.py` — AI 服务统一网关
- `middleware/rbac.py` — 权限中间件

---

## Phase 2 — 剧本智能生成模块

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成剧本智能生成模块。

一、数据模型（scripts app）：
1. Script（剧本）：
   - title: 标题
   - genre: 类型（爱情/悬疑/喜剧/科幻/...）
   - synopsis: 故事梗概
   - target_duration: 目标时长（秒）
   - episode_count: 集数
   - style: 风格描述
   - status: draft / generating / completed / failed
   - content: JSONField，存储完整剧本结构
   - user: 创建者

2. Storyboard（分镜脚本）：
   - script: 关联剧本
   - scene_number: 场景序号
   - description: 画面描述
   - dialogue: 台词
   - camera_angle: 镜头角度
   - duration: 时长（秒）
   - mood: 情绪氛围
   - asset_requirements: JSONField（需要的素材类型和描述）

二、剧本生成服务（services/script_generator.py）：
1. 通过 AIGateway 调用 LLM
2. 生成流程：
   - Step 1: 根据用户输入的梗概，生成故事大纲（含起承转合）
   - Step 2: 将大纲拆解为分集内容
   - Step 3: 每集拆解为分镜脚本（含画面描述、台词、镜头指示）
   - Step 4: 自动为每个分镜标注所需素材类型
3. Prompt 模板管理：
   - 内置 3 套风格模板（甜宠、悬疑、搞笑）
   - 支持用户自定义 Prompt 模板
   - Prompt 模板存储在数据库，可动态修改

三、接口设计：
- POST /api/scripts/ — 创建剧本（触发异步生成）
- GET /api/scripts/ — 剧本列表
- GET /api/scripts/{id}/ — 剧本详情（含分镜）
- PUT /api/scripts/{id}/ — 编辑剧本
- POST /api/scripts/{id}/regenerate/ — 重新生成
- GET /api/scripts/{id}/storyboard/ — 获取分镜脚本
- POST /api/scripts/{id}/export/ — 导出为 PDF/Markdown

四、异步任务：
- 剧本生成通过 Celery 异步执行
- 生成过程中通过 WebSocket 推送进度
- 支持中途取消

输出文件：
- scripts/models.py, serializers.py, views.py, urls.py
- services/script_generator.py
- services/prompt_templates.py
- tasks/script_tasks.py
- consumers/script_consumer.py（WebSocket 进度推送）
```

**Phase 2 交付物**：
- `scripts/` — 剧本与分镜模型、接口、序列化
- `services/script_generator.py` — 剧本生成服务
- `services/prompt_templates.py` — Prompt 模板管理
- `tasks/script_tasks.py` — Celery 异步任务
- `consumers/script_consumer.py` — WebSocket 进度推送

---

## Phase 3 — 素材管理模块

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成素材管理模块。

一、数据模型（assets app）：
1. Asset（素材）：
   - name: 文件名
   - asset_type: image / audio / video / text / font
   - file_path: 存储路径
   - file_size: 文件大小
   - mime_type: MIME 类型
   - tags: 标签（多对多）
   - description: 描述（用于检索）
   - metadata: JSONField（分辨率、时长、色彩等）
   - source: upload / ai_generated / system
   - user: 上传者
   - created_at: 创建时间

2. AssetTag（标签）：
   - name: 标签名
   - category: 分类（场景/人物/情绪/风格）

3. AssetCollection（素材集合）：
   - name: 集合名
   - description: 描述
   - assets: 多对多关联素材
   - user: 创建者

二、文件存储：
- 开发阶段：本地文件系统 media/ 目录
- 生产环境：支持 MinIO 对象存储（通过环境变量切换）
- 文件去重：基于 SHA256 哈希
- 缩略图自动生成（图片/视频）

三、素材检索：
- 基础检索：按名称、标签、类型、时间范围筛选
- 2核2G 适配：不使用向量数据库，改用标签匹配 + 全文搜索
- 智能推荐：根据分镜脚本的 asset_requirements 自动推荐匹配素材

四、接口设计：
- POST /api/assets/upload/ — 上传素材（支持批量）
- GET /api/assets/ — 素材列表（分页、筛选、搜索）
- GET /api/assets/{id}/ — 素材详情
- DELETE /api/assets/{id}/ — 删除素材
- POST /api/assets/{id}/tag/ — 添加标签
- POST /api/assets/collections/ — 创建素材集合
- POST /api/assets/match/ — 根据分镜需求智能匹配素材
- GET /api/assets/stats/ — 素材统计（按类型、大小）

五、前端素材管理页面：
- 瀑布流/网格视图切换
- 拖拽上传
- 图片预览 Lightbox
- 视频/音频内联播放
- 标签筛选侧边栏

输出文件：
- assets/models.py, serializers.py, views.py, urls.py
- services/storage.py（文件存储抽象层）
- services/asset_matcher.py（智能匹配服务）
- tasks/asset_tasks.py（缩略图生成等异步任务）
- 前端：src/pages/Assets/（列表页、上传组件、预览组件）
```

**Phase 3 交付物**：
- `assets/` — 素材模型、接口、存储抽象
- `services/storage.py` — 文件存储抽象层（本地/MinIO）
- `services/asset_matcher.py` — 素材智能匹配
- `tasks/asset_tasks.py` — 异步任务
- 前端素材管理页面

---

## Phase 4 — 视频合成任务调度

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成视频合成任务调度系统。

一、数据模型（tasks app）：
1. VideoTask（视频合成任务）：
   - script: 关联剧本
   - storyboard: 关联分镜
   - status: pending / matching / generating_clips / composing / encoding / completed / failed
   - progress: 进度百分比 0-100
   - config: JSONField（分辨率、帧率、编码格式、水印等）
   - output_path: 输出文件路径
   - error_message: 错误信息
   - started_at / completed_at: 时间戳
   - user: 创建者

2. VideoClip（视频片段）：
   - task: 关联任务
   - scene_number: 对应分镜序号
   - clip_type: ai_generated / stock_footage / image_slideshow
   - source_asset: 使用的素材
   - file_path: 片段文件路径
   - duration: 实际时长
   - status: pending / generating / completed / failed

3. TaskLog（任务日志）：
   - task: 关联任务
   - level: info / warning / error
   - message: 日志内容
   - created_at: 时间戳

二、任务流水线（Celery Chain）：
整个视频合成拆分为 5 个串行子任务：

1. match_assets：根据分镜匹配素材
2. generate_clips：对每个分镜生成视频片段
   - 图片素材 → 使用 FFmpeg 生成 Ken Burns 效果（缩放+平移）
   - AI 生成图片 → 图生视频（调用 AI 视频生成 API）
   - 已有视频素材 → 裁剪到目标时长
3. generate_audio：TTS 生成旁白/对话配音
4. compose_video：FFmpeg 合成最终视频
   - 按分镜顺序拼接片段
   - 叠加字幕（ASS 格式）
   - 叠加背景音乐
   - 添加转场效果
5. encode_output：最终编码输出（H.264 / H.265）

三、资源管控（2核2G 适配）：
- Celery worker 并发数 = 2
- 同时只允许 1 个视频合成任务执行（使用 Celery 信号量）
- FFmpeg 进程内存限制 512MB
- 临时文件自动清理
- 任务超时：单任务最长 30 分钟

四、WebSocket 实时进度：
- 每个子任务完成时推送进度
- 推送格式：{ stage, progress, message, eta }
- 支持任务取消（优雅终止 FFmpeg 子进程）

五、接口设计：
- POST /api/tasks/video/ — 创建视频合成任务
- GET /api/tasks/ — 任务列表
- GET /api/tasks/{id}/ — 任务详情（含子任务状态）
- POST /api/tasks/{id}/cancel/ — 取消任务
- POST /api/tasks/{id}/retry/ — 重试失败任务
- GET /api/tasks/{id}/logs/ — 任务日志
- GET /api/tasks/{id}/download/ — 下载成品视频

输出文件：
- tasks/models.py, serializers.py, views.py, urls.py
- services/video_pipeline.py（流水线编排）
- services/ffmpeg_wrapper.py（FFmpeg 命令封装）
- services/tts_service.py（TTS 服务）
- tasks/video_tasks.py（Celery 任务定义）
- consumers/task_consumer.py（WebSocket 进度推送）
- utils/resource_limiter.py（资源限制工具）
```

**Phase 4 交付物**：
- `tasks/` — 任务模型、接口、日志
- `services/video_pipeline.py` — 视频合成流水线
- `services/ffmpeg_wrapper.py` — FFmpeg 封装
- `services/tts_service.py` — TTS 服务
- `tasks/video_tasks.py` — Celery 任务
- `consumers/task_consumer.py` — WebSocket 进度
- `utils/resource_limiter.py` — 资源限制

---

## Phase 5 — 智能体自动化系统

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成智能体自动化生产系统。

一、数据模型（agents app）：
1. Agent（智能体定义）：
   - name: 名称
   - role: 角色（screenwriter / director / editor / reviewer / producer）
   - description: 角色描述
   - system_prompt: 系统提示词
   - model_config: 关联的 API 配置（使用哪个 LLM）
   - tools: JSONField（可调用的工具列表）
   - is_active: 是否启用
   - user: 创建者（支持系统内置和用户自定义）

2. AgentWorkflow（工作流）：
   - name: 工作流名称
   - description: 描述
   - steps: JSONField（步骤定义，含顺序、条件分支、并行）
   - trigger_type: manual / scheduled / webhook
   - is_active: 是否启用

3. AgentRun（运行记录）：
   - workflow: 关联工作流
   - status: running / completed / failed / paused
   - input_data: 输入数据
   - output_data: 输出数据
   - step_results: JSONField（每步执行结果）
   - started_at / completed_at
   - user: 触发者

二、内置智能体角色：
1. 编剧 Agent（screenwriter）：
   - 职责：根据主题生成剧本
   - 工具：剧本生成、分镜拆解
2. 导演 Agent（director）：
   - 职责：审核分镜、调整镜头语言
   - 工具：分镜修改、风格调整
3. 剪辑 Agent（editor）：
   - 职责：素材匹配、视频合成
   - 工具：素材检索、视频合成流水线
4. 审核 Agent（reviewer）：
   - 职责：内容合规审核、质量评估
   - 工具：敏感词检测、画面质量评分
5. 制片人 Agent（producer）：
   - 职责：协调全流程、进度管理
   - 工具：工作流编排、状态查询

三、工作流引擎（轻量实现，2核2G 适配）：
- 不使用 LangGraph（太重），自研轻量工作流引擎
- 支持：串行、并行、条件分支、循环、人工审核节点
- 工作流定义示例：
  ```
  steps:
    - id: write_script
      agent: screenwriter
      input: { topic: "{{user_input}}" }
    - id: review_script
      agent: reviewer
      input: { script: "{{write_script.output}}" }
      condition: "{{review_script.score}} < 7 ? revise : continue"
    - id: match_and_compose
      agent: editor
      input: { script: "{{write_script.output}}" }
    - id: final_review
      agent: reviewer
      input: { video: "{{match_and_compose.output}}" }
  ```

四、接口设计：
- GET /api/agents/ — 智能体列表
- POST /api/agents/ — 创建自定义智能体
- PUT /api/agents/{id}/ — 修改智能体配置
- POST /api/workflows/ — 创建工作流
- POST /api/workflows/{id}/run/ — 执行工作流
- GET /api/workflows/{id}/runs/ — 运行记录
- GET /api/runs/{id}/ — 运行详情（含每步输出）
- POST /api/runs/{id}/pause/ — 暂停（等待人工审核）
- POST /api/runs/{id}/resume/ — 恢复执行

输出文件：
- agents/models.py, serializers.py, views.py, urls.py
- services/workflow_engine.py（轻量工作流引擎）
- services/agent_executor.py（智能体执行器）
- agents/builtin_agents.py（内置智能体定义）
- tasks/agent_tasks.py（异步执行任务）
```

**Phase 5 交付物**：
- `agents/` — 智能体模型、接口
- `services/workflow_engine.py` — 轻量工作流引擎
- `services/agent_executor.py` — 智能体执行器
- `agents/builtin_agents.py` — 内置角色定义
- `tasks/agent_tasks.py` — 异步任务

---

## Phase 6 — 后台管理系统（Studio）

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成 B 端后台管理系统。

一、数据模型（studio app）：
1. Dashboard（看板数据缓存）：
   - 使用 Django 缓存框架，每 5 分钟刷新
   - 统计项：今日生成数、成功率、平均耗时、用户活跃度

二、后台功能模块：

1. 数据看板（Dashboard）：
   - 总览卡片：总作品数、总视频数、总时长、存储用量
   - 折线图：近 7 天/30 天生成趋势
   - 饼图：任务状态分布
   - 排行榜：最活跃用户、最常用模板
   - 使用 Chart.js 或 ECharts（前端渲染）

2. 作品管理：
   - 剧本列表（搜索、筛选、批量删除）
   - 视频作品列表（预览、下载、状态筛选）
   - 素材库管理（存储用量统计）

3. 任务监控：
   - 实时任务队列（Celery Flower 集成或自建）
   - 任务详情查看（日志、耗时、错误信息）
   - 失败任务重试
   - 任务统计（成功率、平均耗时）

4. 用户管理：
   - 用户列表（搜索、角色筛选）
   - 用户详情（作品数、API 调用量、存储用量）
   - 角色分配、账号启用/禁用
   - API 额度管理

5. 系统配置：
   - 全局 API 配置（系统级默认配置）
   - 存储配置（本地/MinIO）
   - 视频编码默认参数
   - 系统公告管理

6. 智能体管理：
   - 智能体列表（启用/禁用）
   - Prompt 编辑器（在线修改系统提示词）
   - 工作流可视化编辑（简单的拖拽排序）

三、前端页面结构：
- 使用 Ant Design Pro Layout（侧边栏 + 顶部导航）
- 路由：
  /dashboard — 数据看板
  /scripts — 剧本管理
  /videos — 视频作品管理
  /assets — 素材管理
  /tasks — 任务监控
  /agents — 智能体管理
  /workflows — 工作流管理
  /users — 用户管理
  /settings — 系统配置
  /profile — 个人设置（含 API 配置）

输出文件：
- studio/views.py, urls.py, serializers.py
- services/dashboard_service.py（看板数据聚合）
- 前端：
  - src/layouts/MainLayout.tsx
  - src/pages/Dashboard/
  - src/pages/Scripts/
  - src/pages/Videos/
  - src/pages/Tasks/
  - src/pages/Agents/
  - src/pages/Workflows/
  - src/pages/Users/
  - src/pages/Settings/
  - src/pages/Profile/（含 API 配置面板）
  - src/components/（通用组件：统计卡片、图表、表格封装）
```

**Phase 6 交付物**：
- `studio/` — 后台管理后端接口
- `services/dashboard_service.py` — 看板数据服务
- 前端全部页面和通用组件

---

## Phase 7 — 前端核心交互页面

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成前端核心交互功能。

一、剧本创作工作台（/creator/script）：
- 左侧：剧本编辑器（富文本，支持分镜结构）
- 右侧：AI 助手面板（输入梗概 → 生成大纲 → 生成剧本）
- 底部：分镜预览卡片（可拖拽排序）
- 支持实时编辑和 AI 续写

二、视频合成控制台（/creator/compose）：
- Step 1: 选择剧本
- Step 2: 配置参数（分辨率、风格、配音）
- Step 3: 素材确认（预览匹配结果，可手动替换）
- Step 4: 开始合成（WebSocket 实时进度条）
- Step 5: 预览和下载

三、智能体配置面板（/creator/agent-config）：
- 可视化配置智能体参数
- Prompt 编辑器（带语法高亮）
- 测试运行按钮（输入测试数据 → 查看输出）
- 保存为模板

四、通用前端组件封装：
- AsyncButton：异步操作按钮（自动 loading、错误提示）
- FileUploader：文件上传（拖拽、进度、预览）
- JsonEditor：JSON 编辑器（用于配置参数）
- ProgressTracker：多阶段进度追踪组件
- WebSocketHook：WebSocket 连接管理 Hook
- ApiConfigForm：API 配置表单（密钥输入、测试连通、加密提示）

五、状态管理（Zustand stores）：
- useAuthStore：登录状态、用户信息
- useScriptStore：当前编辑的剧本
- useTaskStore：任务状态和进度
- useAssetStore：素材选择和匹配
- useConfigStore：API 配置

六、API 服务层：
- src/api/ 下按模块拆分
- 统一错误处理（Toast 提示）
- 请求/响应类型定义（TypeScript）

输出文件：
- src/pages/Creator/ScriptWorkbench/
- src/pages/Creator/ComposeConsole/
- src/pages/Creator/AgentConfig/
- src/components/AsyncButton.tsx
- src/components/FileUploader.tsx
- src/components/JsonEditor.tsx
- src/components/ProgressTracker.tsx
- src/hooks/useWebSocket.ts
- src/hooks/useApiConfig.ts
- src/stores/*.ts
- src/api/*.ts
```

**Phase 7 交付物**：
- 前端核心交互页面（剧本工作台、合成控制台、智能体配置）
- 通用业务组件
- 状态管理和 API 服务层

---

## Phase 8 — 测试与代码质量

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成测试和代码质量保障。

一、后端测试（pytest + pytest-django）：
1. 单元测试：
   - models：模型验证、加密解密
   - services：AI Gateway、剧本生成、素材匹配、视频流水线
   - utils：工具函数
2. 接口测试：
   - 每个 API 端点的正常流程、异常流程、权限校验
3. 覆盖率目标：> 80%
4. 输出文件：tests/ 目录

二、前端测试（Vitest + React Testing Library）：
1. 组件测试：通用组件渲染和交互
2. Hook 测试：自定义 Hook 逻辑
3. 覆盖率目标：> 70%
4. 输出文件：src/**/*.test.tsx

三、代码质量工具：
1. 后端：
   - flake8 配置（.flake8）
   - black 格式化配置（pyproject.toml）
   - mypy 类型检查配置
   - isort 导入排序
2. 前端：
   - ESLint 配置（.eslintrc.js）
   - Prettier 配置（.prettierrc）
   - TypeScript strict mode
3. pre-commit hooks（.pre-commit-config.yaml）

四、安全审查：
- API Key 加密存储验证
- SQL 注入防护检查
- XSS 防护检查
- CORS 配置检查
- 文件上传类型和大小限制检查

输出文件：
- tests/（后端测试）
- src/**/*.test.tsx（前端测试）
- .flake8, pyproject.toml, .eslintrc.js, .prettierrc
- .pre-commit-config.yaml
- SECURITY.md（安全审计报告）
```

**Phase 8 交付物**：
- 后端测试套件（覆盖率 > 80%）
- 前端测试套件（覆盖率 > 70%）
- 代码质量配置文件
- 安全审计报告

---

## Phase 9 — 部署与文档

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成部署配置和全部文档。

一、生产部署配置：
1. Dockerfile（多阶段构建）：
   - 后端：Python 3.10-slim，安装依赖，收集静态文件
   - 前端：Node 18 构建 → Nginx 托管静态文件
2. docker-compose.prod.yml：
   - 增加 Nginx 反向代理
   - 增加 PostgreSQL（替代 SQLite）
   - 日志挂载
   - 健康检查
3. Nginx 配置：
   - 前端静态文件
   - API 反向代理
   - WebSocket 代理
   - Gzip 压缩
   - 静态资源缓存
4. 部署脚本：
   - deploy.sh（一键部署）
   - backup.sh（数据库备份）
   - restore.sh（数据库恢复）

二、文档：
1. README.md：
   - 项目简介和特性
   - 技术栈说明
   - 快速启动（开发环境和生产环境）
   - 目录结构说明
   - 截图展示

2. docs/architecture.md：
   - 系统架构图
   - 模块划分
   - 数据流图
   - 技术选型理由

3. docs/api-reference.md：
   - 全部 API 接口文档
   - 请求/响应示例
   - 错误码说明
   - 认证方式

4. docs/database-design.md：
   - ER 图
   - 表结构说明
   - 索引设计
   - 数据迁移说明

5. docs/deployment-guide.md：
   - 服务器要求
   - 环境准备
   - 部署步骤
   - 常见问题

6. docs/user-manual.md：
   - 功能操作指南
   - API 配置教程
   - 智能体配置教程
   - 常见问题

7. docs/development-guide.md：
   - 开发环境搭建
   - 编码规范
   - Git 工作流
   - 提交规范

输出文件：
- Dockerfile, docker-compose.prod.yml
- nginx/nginx.conf
- deploy.sh, backup.sh, restore.sh
- README.md（更新）
- docs/architecture.md
- docs/api-reference.md
- docs/database-design.md
- docs/deployment-guide.md
- docs/user-manual.md
- docs/development-guide.md
```

**Phase 9 交付物**：
- 生产部署配置（Docker、Nginx、部署脚本）
- 完整文档体系（7 份文档）

---

## Phase 10 — 交付验收与汇总

```text
继续开发「AI 短剧生成智能体平台」。本阶段完成最终验收和交付汇总。

一、代码审查清单：
- [ ] 所有 API 接口可正常调用
- [ ] API 配置加密存储正常工作
- [ ] 用户可自定义配置各 AI 服务的 API Key 和参数
- [ ] 剧本生成 → 素材匹配 → 视频合成 全链路可运行
- [ ] 智能体工作流可正常编排和执行
- [ ] WebSocket 进度推送正常
- [ ] 后台管理功能完整
- [ ] 2核2G 环境下资源使用合理

二、交付文件统计：
请执行以下命令统计交付文件数量，并输出到 docs/delivery-summary.md：
- find . -name "*.py" | wc -l
- find . -name "*.tsx" -o -name "*.ts" | wc -l
- find . -name "*.md" | wc -l
- find . -name "*.yml" -o -name "*.yaml" | wc -l
- find . -name "*.sh" | wc -l
- find . -type f | wc -l

三、输出交付汇总文档 docs/delivery-summary.md：
- 文件分类统计
- 各模块文件清单
- 技术栈版本清单
- 已知限制（2核2G 环境下的妥协）
- 后续优化建议

四、最终检查：
- 确保 .env.example 包含所有配置项及注释
- 确保 README.md 中的快速启动命令可一键执行
- 确保 docker-compose.yml 可在 2核2G 环境正常启动
```

**Phase 10 交付物**：
- `docs/delivery-summary.md` — 交付汇总文档

---

## 附录 A — 全部交付文件清单

| 类别 | 文件数量（预估） | 主要内容 |
|------|:---:|------|
| 后端 Python | ~50 | Django 7 个 App 的 models/views/serializers/services/tasks |
| 前端 TS/TSX | ~40 | 页面组件、通用组件、stores、api 服务 |
| 配置文件 | ~15 | Docker、Nginx、ESLint、Prettier、pyproject.toml 等 |
| 文档 Markdown | ~10 | README、架构、API、数据库、部署、用户手册等 |
| 脚本 Shell | ~5 | deploy、backup、restore、Makefile |
| 测试文件 | ~15 | pytest 测试、Vitest 测试 |
| **合计** | **~135** | |

## 附录 B — 2核2G 适配要点

| 项目 | 适配策略 |
|------|---------|
| 数据库 | 开发用 SQLite，生产用 PostgreSQL |
| Celery | worker concurrency=2，max-memory-per-child=512MB |
| 向量检索 | 不用 Milvus/Qdrant，改用标签匹配 + 全文搜索 |
| 工作流引擎 | 不用 LangGraph，自研轻量引擎 |
| FFmpeg | 单进程运行，内存限制 512MB |
| 前端构建 | NODE_OPTIONS="--max-old-space-size=1024" |
| Redis | 同时用作缓存和消息队列，节省一个服务 |
| 对象存储 | 开发用本地文件系统，生产可选 MinIO |

## 附录 C — 用户自定义 API 配置功能说明

这是本平台的核心差异化功能，允许用户自行配置：

1. **支持的 AI 服务类型**：
   - LLM（剧本生成、智能体对话）
   - TTS（配音生成）
   - 图片生成（分镜画面）
   - 视频生成（图生视频）
   - Embedding（素材语义检索）

2. **可配置项**：
   - API Key（加密存储）
   - API Base URL（支持私有部署）
   - 模型名称
   - 额外参数（temperature、max_tokens 等）
   - 优先级（多配置时自动选择）

3. **安全措施**：
   - Fernet 对称加密存储
   - API 返回时脱敏显示
   - 连通性测试接口
   - 调用额度管理

4. **Fallback 机制**：
   - 同类型多配置按优先级排序
   - 主配置失败自动切换备用
   - 失败记录日志并通知用户
