"""统一的业务异常定义。由 main.py 的异常处理器转换为 JSON 响应。"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """带 HTTP 状态码与模块名的业务异常。"""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        module: str = "api",
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.module = module
        self.detail = detail

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "detail": self.message,
            "error": {
                "module_name": self.module,
                "error_message": self.message,
            },
        }
        if self.detail is not None:
            payload["error"]["detail"] = self.detail
            payload["detail_data"] = self.detail
        return payload
