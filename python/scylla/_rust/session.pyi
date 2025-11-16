from typing import override

class Session:
    async def execute(self, request: str) -> RequestResult: ...

class RequestResult:
    @override
    def __str__(self) -> str: ...
