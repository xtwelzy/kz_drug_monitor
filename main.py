import asyncio
import logging
import threading
import queue as thread_queue

from telethon import TelegramClient

from config import ACCOUNTS
from database_manager import DatabaseManager
from keyword_manager import KeywordManager
from telegram_monitor import TelegramMonitor
from bot_searcher import BotSearcher
from channel_discoverer import ChannelDiscoverer
from scan_tasks import scan_queue

import web_interface
import uvicorn


class AccountRunner:
    """
    Один телеграм-аккаунт (своя сессия + свой API_ID/API_HASH) и все воркеры вокруг него.
    """

    def __init__(self, cfg: dict, db: DatabaseManager, keywords: KeywordManager):
        self.session_name: str = cfg["SESSION"]
        self.phone: str = cfg["PHONE"]
        self.api_id: int = int(cfg["API_ID"])
        self.api_hash: str = cfg["API_HASH"]

        self.db = db
        self.keywords = keywords

        self.client: TelegramClient | None = None
        self.telegram_monitor: TelegramMonitor | None = None
        self.bot_searcher: BotSearcher | None = None
        self.channel_discoverer: ChannelDiscoverer | None = None

    async def initialize(self) -> bool:
        """
        Логин для конкретного аккаунта и создание модулей.
        """
        try:
            self.client = TelegramClient(
                self.session_name,
                self.api_id,
                self.api_hash,
            )
            await self.client.start(phone=self.phone)

            me = await self.client.get_me()
            logging.info(
                f"✅ [{self.session_name}] logged in as: "
                f"{me.first_name} ({me.phone})"
            )

            self.telegram_monitor = TelegramMonitor(
                client=self.client,
                db_manager=self.db,
                keyword_manager=self.keywords,
                dialogs_limit=200,
                history_limit=200,
            )

            self.bot_searcher = BotSearcher(
                self.client,
                self.db,
                self.keywords,
                self.telegram_monitor,
            )

            self.channel_discoverer = ChannelDiscoverer(
                self.client,
                self.db,
                self.keywords,
                self.telegram_monitor,
            )

            return True

        except Exception as e:
            logging.error(f"❌ [{self.session_name}] init error: {e}")
            return False

    async def manual_scan_worker(self):
        """
        Воркер для очереди ручных сканов.
        Очередь общая, несколько аккаунтов могут разбирать её параллельно.
        """
        if not self.telegram_monitor:
            return

        while True:
            try:
                channel_identifier = scan_queue.get_nowait()
            except thread_queue.Empty:
                await asyncio.sleep(1)
                continue

            try:
                logging.info(
                    f"🧾 [{self.session_name}] manual scan: {channel_identifier}"
                )
                result = await self.telegram_monitor.manual_scan_chat(
                    channel_identifier,
                    limit=500,
                )
                logging.info(
                    f"✅ [{self.session_name}] manual scan [{result.get('title')}]: "
                    f"scanned={result.get('scanned')}, "
                    f"suspicious={result.get('suspicious')}"
                )
            except Exception as e:
                logging.error(
                    f"❌ [{self.session_name}] manual scan error "
                    f"for {channel_identifier}: {e}"
                )

    async def start_all_tasks(self):
        """
        Запускаем для аккаунта:
        - мониторинг чатов/каналов
        - работу ботов
        - автопоиск каналов
        - воркер ручных сканов
        """
        if not self.telegram_monitor:
            logging.error(f"❌ [{self.session_name}] telegram_monitor is None")
            return

        # старт мониторинга (initial_scan + обработчик новых сообщений)
        await self.telegram_monitor.start_monitoring()

        # периодический поиск через ботов
        if self.bot_searcher:
            asyncio.create_task(self.bot_searcher.periodic_bot_search())

        # автопоиск каналов
        if self.channel_discoverer:
            asyncio.create_task(self.channel_discoverer.periodic_discovery())
            asyncio.create_task(self.channel_discoverer.discover_channels())

        # воркер ручных сканов
        asyncio.create_task(self.manual_scan_worker())

        logging.info(f"✅ [{self.session_name}] monitoring started")


class MultiKZMonitor:
    """
    Главный контроллер: много аккаунтов, одна БД, один веб-интерфейс.
    """

    def __init__(self):
        self.db = DatabaseManager()
        self.keywords = KeywordManager()
        self.accounts: list[AccountRunner] = []

        logging.info("✅ Multi KZ Drug Monitor initialized")

    async def initialize_all(self) -> bool:
        """
        Инициализируем все аккаунты из config.ACCOUNTS.
        """
        for cfg in ACCOUNTS:
            # базовые проверки
            required = ("SESSION", "PHONE", "API_ID", "API_HASH")
            if not all(k in cfg and cfg[k] for k in required):
                logging.error(f"❌ Bad account config (missing fields): {cfg}")
                continue

            runner = AccountRunner(cfg, db=self.db, keywords=self.keywords)
            ok = await runner.initialize()
            if ok:
                self.accounts.append(runner)

        if not self.accounts:
            logging.error("❌ No accounts were initialized. Check ACCOUNTS in config.py")
            return False

        logging.info(f"✅ Initialized {len(self.accounts)} accounts")
        return True

    async def start_all(self):
        """
        Запускаем мониторинг по всем аккаунтам.
        """
        for runner in self.accounts:
            await runner.start_all_tasks()

        logging.info("✅ All accounts monitoring started")
        # держим event loop живым
        await asyncio.Future()


# ----------------- Веб-интерфейс (FastAPI + Uvicorn) -----------------
def run_web_interface():
    """
    Запуск веб-интерфейса в отдельном потоке.
    """
    try:
        uvicorn.run(
            web_interface.app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            access_log=False,
        )
    except Exception as e:
        logging.error(f"❌ Web interface error: {e}")


# ----------------- MAIN -----------------
async def main():
    logging.info("🚀 Starting Multi-Account KZ Drug Shop Monitor...")

    monitor = MultiKZMonitor()

    if await monitor.initialize_all():
        # Веб поднимаем один раз
        web_thread = threading.Thread(target=run_web_interface, daemon=True)
        web_thread.start()
        logging.info("🌐 Web interface available at: http://localhost:8000")

        await monitor.start_all()
    else:
        logging.error("❌ Failed to initialize any account")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⏹️ System stopped by user")
    except Exception as e:
        logging.error(f"❌ Critical error: {e}")
