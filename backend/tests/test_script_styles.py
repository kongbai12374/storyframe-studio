import json
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command

from core import gateway
from core.models import PromptTemplate


STORY_STYLES = {
    "甜宠", "悬疑", "搞笑", "古装权谋", "都市逆袭", "青春成长",
    "奇幻冒险", "科幻未来", "复仇爽剧", "亲情治愈", "职场现实", "乡村生活",
}


def test_bootstrap_creates_prompt_templates_for_all_story_styles(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "unique-bootstrap-test-password-2026")
    call_command("bootstrap", username="style-test-admin", stdout=StringIO())

    templates = {
        template.name: template.prompt
        for template in PromptTemplate.objects.filter(name__in=STORY_STYLES)
    }
    assert set(templates) == STORY_STYLES
    assert all(prompt.strip() for prompt in templates.values())
    assert len({templates[name] for name in STORY_STYLES}) == len(STORY_STYLES)


def test_llm_uses_selected_style_template(context, monkeypatch):
    user, _, _ = context
    PromptTemplate.objects.create(
        name="奇幻冒险", prompt="建立一致的魔法规则并让冒险逐步升级。"
    )
    provider = SimpleNamespace(model="test-model", base_url="https://example.com")
    captured = {}
    monkeypatch.setattr(gateway, "provider_for", lambda _user, _service: provider)

    def fake_request(_provider, _endpoint, body, _limit):
        captured["body"] = body
        return json.dumps(
            {"choices": [{"message": {"content": json.dumps({"title": "测试", "scenes": []})}}]}
        ).encode()

    monkeypatch.setattr(gateway, "request_provider", fake_request)
    result = gateway.llm(user, "一名学徒发现古老遗迹", "奇幻冒险")

    assert result["title"] == "测试"
    assert "魔法规则" in captured["body"]["messages"][0]["content"]
