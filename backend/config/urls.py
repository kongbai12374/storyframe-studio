from django.urls import path, re_path
from django.contrib import admin
from core import views as v
from core.asset_links import asset_link_file

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", v.health),
    path("api/csrf/", v.csrf),
    path("api/auth/login/", v.signin),
    path("api/auth/logout/", v.signout),
    path("api/auth/me/", v.me),
    path("api/dashboard/", v.dashboard),
    path("api/scripts/", v.scripts),
    path("api/scripts/<int:ident>/", v.script_detail),
    path("api/scripts/<int:ident>/duplicate/", v.duplicate_script),
    path("api/scripts/<int:ident>/export/", v.export_script),
    path("api/assets/", v.assets),
    path("api/asset-links/<str:token>/", asset_link_file),
    path("api/asset-links/<str:token>/<str:filename>", asset_link_file),
    path("api/assets/<int:ident>/", v.asset_detail),
    path("api/assets/<int:ident>/file/", v.asset_file),
    path("api/providers/", v.providers),
    path("api/providers/<int:ident>/", v.provider_detail),
    path("api/providers/<int:ident>/test/", v.provider_test),
    path("api/canvases/", v.canvases),
    path("api/canvases/<int:ident>/", v.canvas_detail),
    path("api/canvases/<int:ident>/run/", v.canvas_run),
    path("api/jobs/", v.jobs),
    path("api/jobs/<int:ident>/", v.job_detail),
    path("api/jobs/<int:ident>/cancel/", v.job_cancel),
    path("api/jobs/<int:ident>/retry/", v.job_retry),
    path("api/jobs/<int:ident>/download/", v.job_download),
    re_path(r"^(?P<path>.*)$", v.spa),
]
