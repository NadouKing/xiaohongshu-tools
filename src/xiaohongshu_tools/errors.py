class XiaohongshuError(Exception):
    """A safe, machine-readable failure; messages never contain page/credential dumps."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AuthenticationRequired(XiaohongshuError):
    def __init__(self):
        super().__init__("authentication_required", "请先用 xhs login 登录专用浏览器。")


class VerificationRequired(XiaohongshuError):
    def __init__(self):
        super().__init__("verification_required", "页面需要人工验证；请在可见浏览器中处理后重试。")
