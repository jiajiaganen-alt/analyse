"""业务异常定义与统一异常处理。"""

from __future__ import annotations


class AppError(Exception):
    """带 HTTP 状态码的业务异常，由全局异常处理器转换为统一 JSON。"""

    def __init__(self, message: str, status_code: int = 400, code: str = "BUSINESS_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
