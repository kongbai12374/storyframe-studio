from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="所属用户")
    quota_bytes = models.PositiveBigIntegerField(
        default=500 * 1024 * 1024, verbose_name="存储空间上限"
    )
    api_calls_remaining = models.PositiveIntegerField(
        default=100, verbose_name="可用 AI 调用次数"
    )

    class Meta:
        verbose_name = "用户配额"
        verbose_name_plural = "用户配额"

    def __str__(self):
        return f"{self.user.username} 的配额"


class Provider(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="所属用户")
    name = models.CharField(max_length=80, verbose_name="服务名称")
    service = models.CharField(
        max_length=10,
        choices=[
            ("llm", "大语言模型"),
            ("tts", "语音合成"),
            ("video", "视频生成"),
            ("image", "图片生成"),
        ],
        verbose_name="服务类型",
    )
    base_url = models.URLField(max_length=300, verbose_name="接口地址")
    model = models.CharField(max_length=100, verbose_name="模型标识")
    video_config = models.JSONField(default=dict, blank=True, verbose_name="视频参数")
    encrypted_key = models.TextField(verbose_name="加密后的密钥")
    key_tail = models.CharField(max_length=4, blank=True, verbose_name="密钥尾号")
    active = models.BooleanField(default=True, verbose_name="已启用")

    class Meta:
        verbose_name = "AI 服务配置"
        verbose_name_plural = "AI 服务配置"

    def __str__(self):
        return self.name


class Asset(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="所属用户")
    name = models.CharField(max_length=160, verbose_name="素材名称")
    kind = models.CharField(
        max_length=10,
        choices=[("image", "图片"), ("audio", "音频")],
        verbose_name="素材类型",
    )
    path = models.CharField(max_length=200, verbose_name="文件路径")
    thumbnail = models.CharField(max_length=200, blank=True, verbose_name="缩略图路径")
    sha256 = models.CharField(max_length=64, verbose_name="文件校验值")
    size = models.PositiveBigIntegerField(verbose_name="文件大小")
    metadata = models.JSONField(default=dict, verbose_name="附加信息")
    tags = models.CharField(max_length=200, blank=True, verbose_name="标签")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "sha256"], name="user_asset_hash")
        ]
        verbose_name = "素材"
        verbose_name_plural = "素材"

    def __str__(self):
        return self.name


class Script(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="所属用户")
    title = models.CharField(max_length=160, verbose_name="剧本标题")
    synopsis = models.TextField(blank=True, verbose_name="故事梗概")
    style = models.CharField(max_length=20, default="甜宠", verbose_name="故事风格")
    scenes = models.JSONField(default=list, verbose_name="分镜场景")
    revision = models.PositiveIntegerField(default=1, verbose_name="修订版本")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "剧本"
        verbose_name_plural = "剧本"

    def __str__(self):
        return self.title


class CanvasProject(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="所属用户")
    name = models.CharField(max_length=160, verbose_name="画布名称")
    schema_version = models.PositiveIntegerField(default=1, verbose_name="数据结构版本")
    revision = models.PositiveIntegerField(default=1, verbose_name="修订版本")
    document = models.JSONField(default=dict, verbose_name="画布内容")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "创作画布"
        verbose_name_plural = "创作画布"

    def __str__(self):
        return self.name


class Job(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="所属用户")
    kind = models.CharField(max_length=20, default="compose", verbose_name="任务类型")
    status = models.CharField(
        max_length=24, default="queued", db_index=True, verbose_name="任务状态"
    )
    stage = models.CharField(max_length=100, default="排队中", verbose_name="当前阶段")
    progress = models.PositiveIntegerField(default=0, verbose_name="完成进度")
    remote_state = models.JSONField(default=dict, blank=True, verbose_name="服务端状态")
    snapshot = models.JSONField(default=dict, verbose_name="任务输入快照")
    result = models.JSONField(default=dict, verbose_name="生成结果")
    error = models.TextField(blank=True, verbose_name="错误信息")
    error_code = models.CharField(max_length=50, blank=True, verbose_name="错误代码")
    idempotency_key = models.CharField(max_length=100, verbose_name="防重复提交标识")
    lease_owner = models.CharField(max_length=64, blank=True, verbose_name="执行者")
    heartbeat_at = models.DateTimeField(null=True, blank=True, verbose_name="最近心跳时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    attempts = models.PositiveIntegerField(default=0, verbose_name="已尝试次数")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"], name="job_idempotency"
            )
        ]
        verbose_name = "生成任务"
        verbose_name_plural = "生成任务"

    def __str__(self):
        statuses = {
            "queued": "排队中",
            "running": "处理中",
            "cancel_requested": "正在取消",
            "succeeded": "已完成",
            "failed": "失败",
            "canceled": "已取消",
        }
        return f"任务 #{self.pk}（{statuses.get(self.status, self.status)}）"


class JobLog(models.Model):
    job = models.ForeignKey(
        Job, on_delete=models.CASCADE, related_name="logs", verbose_name="关联任务"
    )
    message = models.CharField(max_length=500, verbose_name="日志内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="记录时间")

    class Meta:
        verbose_name = "任务日志"
        verbose_name_plural = "任务日志"

    def __str__(self):
        return f"任务 #{self.job_id} 日志"


class PromptTemplate(models.Model):
    name = models.CharField(max_length=30, unique=True, verbose_name="模板名称")
    prompt = models.TextField(verbose_name="提示词内容")

    class Meta:
        verbose_name = "提示词模板"
        verbose_name_plural = "提示词模板"

    def __str__(self):
        return self.name


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=40, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class AIRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="所属用户")
    provider = models.ForeignKey(
        Provider, on_delete=models.SET_NULL, null=True, verbose_name="服务配置"
    )
    service = models.CharField(max_length=10, verbose_name="服务类型")
    endpoint = models.CharField(max_length=40, verbose_name="接口路径")
    status = models.CharField(max_length=20, default="submitted", verbose_name="请求状态")
    http_status = models.PositiveIntegerField(null=True, verbose_name="HTTP 状态码")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="提交时间")
    completed_at = models.DateTimeField(null=True, verbose_name="完成时间")

    class Meta:
        verbose_name = "AI 请求记录"
        verbose_name_plural = "AI 请求记录"

    def __str__(self):
        services = {
            "llm": "大语言模型",
            "tts": "语音合成",
            "video": "视频生成",
            "image": "图片生成",
        }
        return f"{services.get(self.service, self.service)} 请求 #{self.pk}"
