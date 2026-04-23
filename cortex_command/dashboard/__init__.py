"""Real-time web dashboard for monitoring overnight and pipeline agent sessions.

Serves a FastAPI + Jinja2 web application with a background asyncio polling
loop that reads project state files and caches parsed results in memory.
HTTP handlers serve from cache. All file I/O is wrapped in try/except so
parsers never raise on missing or malformed files.

Entry point: python3 -m cortex_command.dashboard
"""

__version__ = "0.1.0"
