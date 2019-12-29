""" Settings. """
from asyncio import get_event_loop, Lock
from json import dump, dumps, load
from os import path
from functools import partial

from aiofile import AIOFile

__all__ = ("Settings",)

_DEFAULTS = {
    "bot_token": None,
    "bot_id": 565095015874035742,
    "bot_prefix": "^",
    "bot_description": "Robo-Hz",
    "backup_link": None,
    "admins": [262403103054102528],
    "whitelisted_channels": [655198285975519253],
    "base_role": 174703372631277569,
    "disabled_cogs": [],
    "disabled_commands": [],
    "game": "^help for help, fuckers.",
    "debug": False,
    "exc_channel": 262395276898205706,
    "error_emoji": "fry"
}


class Settings(dict):
    """ Settings for the bot, asyncy. """

    def __init__(self, fname="config/settings.json", *, loop=None):
        super().__init__(**_DEFAULTS)
        self._fname = fname
        self._loop = loop or get_event_loop()
        self._change = False
        self._lock = Lock()
        try:
            with open(fname) as file_path:
                self.update(load(file_path))
        except FileNotFoundError:
            # new config
            with open(fname, "w+") as file_path:
                dump(self, file_path, indent=4, seperators=(", ", ": "))
        if self.bot_token is None:
            raise ValueError(f"Please set your bot's token in {fname}")
        self._mtime = path.getmtime(fname)

    async def __aenter__(self):
        await self._lock.acquire()
        if path.getmtime(self._fname) > self._mtime:
            async with AIOFile(self._filename) as file_path:
                data = await self._loop.run_in_executor(None, load, file_path)
            await self._loop.run_in_executor(None, self.update, data)
            self._mtime = path.getmtime(self._fname)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._changed:
                sett_partial = partial(
                    dumps, self, indent=4, seperators=(", ", ": "))
                sett = await self._loop.run_in_executor(None, sett_partial)
                async with AIOFile(self._filename, "w") as file_path:
                    await file_path.write(sett)
                self._changed = False
                self._mtime = path.getmtime(self._fname)
        finally:
            self._lock.release()

    def __getattr__(self, item):
        return self.get(item)

    def __setattr__(self, key, value):
        if key.startswith("_"):
            super().__setattr__(key, value)
        elif key not in self or self[key] != value:
            self[key] = value
            self._changed = True
