from django.contrib import admin
from .models import (
    Profile,
    Provider,
    Asset,
    Script,
    CanvasProject,
    Job,
    JobLog,
    PromptTemplate,
    AIRequest,
)

for model in [Profile, Asset, Script, CanvasProject, Job, JobLog, PromptTemplate]:
    admin.site.register(model)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    exclude = ["encrypted_key", "key_tail"]

    def has_add_permission(self, request):
        return False


@admin.register(AIRequest)
class AIRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "service", "status", "http_status", "created_at"]
    readonly_fields = [
        "user",
        "provider",
        "service",
        "endpoint",
        "status",
        "http_status",
        "created_at",
        "completed_at",
    ]

    def has_add_permission(self, request):
        return False
