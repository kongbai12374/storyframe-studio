import json
from django.http import JsonResponse
from django.core.exceptions import RequestDataTooBig
from django.db import OperationalError
from django.utils.deprecation import MiddlewareMixin


class APIInputGuard(MiddlewareMixin):
    def process_request(self, request):
        if (
            request.path.startswith("/api/")
            and request.method in ["POST", "PUT", "PATCH"]
            and request.content_type == "application/json"
        ):
            try:
                body = json.loads(request.body or b"{}")
            except RequestDataTooBig:
                return JsonResponse({"detail": "请求正文超过大小限制"}, status=413)
            except (ValueError, UnicodeError):
                return JsonResponse({"detail": "JSON格式无效"}, status=400)
            if not isinstance(body, dict):
                return JsonResponse({"detail": "请求正文必须是JSON对象"}, status=400)

    def process_exception(self, request, exception):
        if request.path.startswith("/api/") and isinstance(exception, OperationalError):
            response = JsonResponse({"detail": "数据库暂忙，请稍后重试"}, status=503)
            response["Retry-After"] = "2"
            return response
