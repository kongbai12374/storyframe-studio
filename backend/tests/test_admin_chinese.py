from django.contrib.auth.models import User
from django.test import Client
from core.models import Asset


def test_admin_home_and_asset_form_use_chinese_labels(db):
    user = User.objects.create_superuser("admin", password="admin-strong-test-password")
    client = Client()
    client.force_login(user)

    home = client.get("/admin/")
    assert home.status_code == 200
    assert "镜序管理后台" in home.content.decode()
    assert "内容与生成管理" in home.content.decode()
    assert "AI 服务配置" in home.content.decode()

    asset_form = client.get("/admin/core/asset/add/")
    assert asset_form.status_code == 200
    content = asset_form.content.decode()
    assert "素材名称" in content
    assert "所属用户" in content
    assert "文件校验值" in content

    asset = Asset.objects.create(
        user=user,
        name="示例素材",
        kind="image",
        path="1/example.png",
        sha256="a" * 64,
        size=10,
    )
    change_page = client.get(f"/admin/core/asset/{asset.pk}/change/")
    assert change_page.status_code == 200
    change_content = change_page.content.decode()
    assert "示例素材" in change_content
    assert "Asset object" not in change_content
    assert "图片" in change_content
