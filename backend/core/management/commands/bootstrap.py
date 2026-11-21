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
            (
                "甜宠",
                "创作温暖轻快的爱情短剧，突出双向奔赴、细腻互动和有记忆点的甜蜜瞬间；人物关系与情感推进要自然。",
            ),
            (
                "悬疑",
                "创作层层递进的悬疑短剧，埋下可回收的线索，保持信息公平，利用误导和反转制造紧张感；结尾留下明确钩子。",
            ),
            (
                "搞笑",
                "创作节奏明快的喜剧短剧，以人物性格、误会或反差制造笑点；避免生硬段子，让包袱在情节中自然发生。",
            ),
            (
                "古装权谋",
                "创作古装权谋短剧，围绕利益、身份与阵营博弈推进剧情；交代清楚人物立场，让计谋有因果，关键场景有反转。",
            ),
            (
                "都市逆袭",
                "创作当代都市逆袭短剧，主角从现实困境出发，凭能力与选择逐步翻盘；强化阶段性爽点，同时避免无因开挂。",
            ),
            (
                "青春成长",
                "创作青春成长短剧，聚焦友情、初恋、家庭或梦想中的真实选择；对白贴近年轻人的表达，情绪真挚而不说教。",
            ),
            (
                "奇幻冒险",
                "创作奇幻冒险短剧，建立易懂且前后一致的世界规则；让主角带着明确目标闯关，逐步揭开世界秘密并承担选择后果。",
            ),
            (
                "科幻未来",
                "创作近未来科幻短剧，以一个清晰的科技设定推动人物冲突；把技术影响落到具体的人和选择上，避免设定堆砌。",
            ),
            (
                "复仇爽剧",
                "创作节奏紧凑的复仇短剧，交代伤害、目标与行动策略；让主角逐步夺回主动权，每次反击都有铺垫和即时回报。",
            ),
            (
                "亲情治愈",
                "创作细腻克制的亲情治愈短剧，呈现家庭成员之间的误解、亏欠与和解；通过日常细节表达情感，结尾温暖但不煽情。",
            ),
            (
                "职场现实",
                "创作贴近现实的职场短剧，围绕协作、责任、成长或利益冲突展开；人物决策符合职场处境，不把专业问题简单脸谱化。",
            ),
            (
                "乡村生活",
                "创作有生活气息的乡村短剧，展现熟人关系、家庭生计与社区变化；尊重乡村人物的主体性，兼具烟火气与戏剧张力。",
            ),
        ]:
            PromptTemplate.objects.get_or_create(name=name, defaults={"prompt": prompt})
        self.stdout.write("管理员与模板已初始化；已有账户密码保持不变。")
