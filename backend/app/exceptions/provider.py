# exceptions.py
from app.enmus.exception import ProviderErrorEnum


class ProviderError(Exception):
    def __init__(self, message: str,code: ProviderErrorEnum) -> None:
        super().__init__(message)
        self.code=code
        self.message = message


class ProviderNameExistsError(ValueError):
    """供应商重名。

    继承 ``ValueError`` 是为了不改变既有调用方的捕获语义；单独成类是为了让路由能
    返回结构化 ``data.reason``，前端不必再去匹配中文文案（文案一改就静默失效）。
    """
        
        

