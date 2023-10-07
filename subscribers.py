import asyncio
import logging
from typing import Optional

from aiohttp.log import access_logger
from aiogram.client.bot import Bot


class Subscribers:
    def __init__(self):
        self._bot_list: dict[Bot, list[int]] = {}

    def attach_bot(self, bot: Bot):
        if bot not in self._bot_list:
            self._bot_list[bot] = []

    def add_subscriber(self, bot: Bot, subscriber_id: int):
        if bot in self._bot_list and subscriber_id not in self._bot_list[bot]:
            self._bot_list[bot].append(subscriber_id)

    def detach_bot(self, bot: Bot):
        if bot in self._bot_list:
            self._bot_list.pop(bot)

    async def send_message(self, message: str):
        for bot in self._bot_list:
            for chat_id in self._bot_list[bot]:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message
                )
