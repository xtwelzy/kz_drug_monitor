import asyncio
import logging
from telethon.errors import RPCError


class BotSearcher:
    """
    Поиск каналов через ботов.
    Ищет ссылки типа t.me/xxxxx и проверяет их через TelegramMonitor.
    """

    def __init__(self, client, db_manager, keyword_manager, telegram_monitor):
        self.client = client
        self.db = db_manager
        self.keywords = keyword_manager
        self.tm = telegram_monitor

        self.search_bots = [
            "BotFather",
            "like",
            "vkmusic_bot",
        ]

        logging.info("✅ Bot Searcher initialized")

    async def search_all_bots(self):
        logging.info("🤖 Starting bot search...")

        for bot in self.search_bots:
            try:
                await self.query_bot(bot)
                await asyncio.sleep(3)
            except Exception:
                pass

    async def query_bot(self, bot_username):
        try:
            bot = await self.client.get_entity(bot_username)
        except RPCError:
            return
        except Exception:
            return

        logging.info(f"🤖 Querying bot: {bot_username}")

        try:
            await self.client.send_message(bot, "/start")
            await asyncio.sleep(2)
        except Exception:
            return

        try:
            messages = await self.client.get_messages(bot, limit=5)
        except Exception:
            return

        await self.analyze_bot_responses(messages, bot_username)

    async def analyze_bot_responses(self, messages, bot_name):
        for msg in messages:
            text = getattr(msg, "text", None)
            if not text:
                continue

            links = self.keywords.extract_links(text)
            if not links:
                continue

            for link in links:
                username = link.replace("https://", "").replace("http://", "").replace("t.me/", "").strip()
                logging.info(f"🤖 Bot {bot_name} suggested channel: @{username}")

                # Проверяем, что это реально канал
                try:
                    entity = await self.client.get_entity(username)
                except Exception:
                    continue

                # Читаем последние сообщения канала
                try:
                    msgs = await self.client.get_messages(entity, limit=10)
                except Exception:
                    continue

                # Проверяем через TelegramMonitor
                for m in msgs:
                    txt = getattr(m, "text", None)
                    if not txt:
                        continue
                    await self.tm._process_text_for_entity(entity, txt, f"bot_{bot_name}")

    async def periodic_bot_search(self):
        while True:
            try:
                await self.search_all_bots()
                await asyncio.sleep(3600)
            except Exception as e:
                logging.error(f"Periodic bot search error: {e}")
                await asyncio.sleep(300)
