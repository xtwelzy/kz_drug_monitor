import asyncio
import logging

from database_manager import DatabaseManager
from keyword_manager import KeywordManager


class ChannelDiscoverer:
    def __init__(self, client, db_manager: DatabaseManager, keyword_manager: KeywordManager, telegram_monitor):
        self.client = client
        self.db = db_manager
        self.keywords = keyword_manager
        self.tm = telegram_monitor

        logging.info("✅ Channel Discoverer initialized")

    # ======================================================
    #   ОСНОВНОЙ ПОИСК КАНАЛОВ
    # ======================================================

    async def discover_channels(self):
        logging.info("📡 Starting channel discovery...")

        found = 0

        try:
            async for dialog in self.client.iter_dialogs(limit=100):
                try:
                    # Берём только чаты / каналы
                    if not (dialog.is_channel or dialog.is_group):
                        continue

                    entity = dialog.entity

                    channel_info = await self.analyze_channel(entity)

                    # 🔥 ВАЖНО: если анализа нет → пропустить
                    if channel_info is None:
                        continue

                    self.db.save_channel(channel_info)
                    found += 1

                    logging.info(f"Found: {channel_info['title']}")

                except Exception as e:
                    logging.error(f"Dialog scan error: {e}")

        except Exception as e:
            logging.error(f"Discovery error: {e}")

        logging.info(f"🔍 Channel discovery done. Suspicious found: {found}")
        return found

    # ======================================================
    #   АНАЛИЗ КАНАЛА
    # ======================================================

    async def analyze_channel(self, entity):
        try:
            full = await self.client.get_entity(entity)

            channel_type = (
                "channel"
                if hasattr(full, "broadcast") and full.broadcast
                else "chat"
            )

            # Анализ названия
            title = getattr(full, "title", "")
            desc = getattr(full, "about", "")

            risk = 0.0

            title_an = self.keywords.analyze_text(title)
            if title_an.get("is_suspicious"):
                risk += 0.4

            desc_an = self.keywords.analyze_text(desc)
            if desc_an.get("is_suspicious"):
                risk += 0.3

            if risk < 0.1:
                return None  # не сохраняем простые каналы

            return {
                "username": getattr(full, "username", None),
                "title": getattr(full, "title", "Unknown"),
                "participants_count": getattr(full, "participants_count", 0),
                "kz_phone_ratio": 0.0,
                "risk_score": risk,
                "found_via": "auto_discovery",
                "description": desc,
                "channel_type": channel_type,
            }

        except Exception:
            return None

    # ======================================================
    #   ПЕРИОДИЧЕСКИЙ ПОИСК
    # ======================================================

    async def periodic_discovery(self):
        while True:
            try:
                await self.discover_channels()
                await asyncio.sleep(7200)  # каждые 2 часа
            except Exception as e:
                logging.error(f"Periodic discovery error: {e}")
                await asyncio.sleep(300)
