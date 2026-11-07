import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from core.models import Profile, PromptTemplate


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")

    def handle(self, *args, **opts):
        password = os.environ.get("ADMIN_PASSWORD", "")
        validate_password(password)
        user, created = User.objects.get_or_create(
            username=opts["username"], defaults={"is_staff": True, "is_superuser": True}
        )
        if created:
            user.set_password(password)
            user.save()
        Profile.objects.get_or_create(user=user)
        for name, prompt in [
            ("甜宠", "写温暖轻快、人物关系清晰的短剧。"),
            ("悬疑", "写线索清晰、结尾反转的悬疑短剧。"),
            ("搞笑", "写节奏明快、笑点自然的喜剧短剧。"),
        ]:
            PromptTemplate.objects.get_or_create(name=name, defaults={"prompt": prompt})
        self.stdout.write("管理员与模板已初始化；已有账户密码保持不变。")
