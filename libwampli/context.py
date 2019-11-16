from typing import AsyncContextManager, Optional

import aiowamp

from .config import ConnectionConfig

__all__ = ["ClientContextManager"]


class ClientContextManager(AsyncContextManager[aiowamp.ClientABC]):
    _config: ConnectionConfig
    _client: Optional[aiowamp.ClientABC]

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._client = None

    async def __aenter__(self) -> aiowamp.ClientABC:
        self._client = await aiowamp.connect(self._config.endpoint, realm=self._config.realm)
        return self._client

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.close()
