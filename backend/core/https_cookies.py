"""Keep HTTPS cookies secure while retaining the authorized loopback SSH entry."""


class SchemeCookieSecurity:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.is_secure():
            for name in ("sessionid", "csrftoken"):
                if name in response.cookies:
                    response.cookies[name]["secure"] = True
        return response
