import logging
from datetime import datetime
from typing import Optional

from telethon import events
from telethon.tl.types import User

from config import ALERT_CHAT
from database_manager import DatabaseManager
from keyword_manager import KeywordManager


class TelegramMonitor:
    def __init__(
        self,
        client,
        db_manager: DatabaseManager,
        keyword_manager: KeywordManager,
        dialogs_limit: int = 200,
        history_limit: int = 200,
    ):
        self.client = client
        self.db = db_manager
        self.keywords = keyword_manager

        # Лимиты на начальное сканирование
        self.dialogs_limit = dialogs_limit
        self.history_limit = history_limit

        # Куда шлём алерты
        self.alert_chat: str | None = ALERT_CHAT
        self._alert_username_norm = (
            (self.alert_chat or "").lstrip("@").lower() if self.alert_chat else ""
        )

        # Плейсхолдер под агрегаторы
        self.kz_aggregators = [
            "almaty_life",
            "astana_city",
            "kz_news",
            "kazakhstan_now",
            "almaty_guide",
            "astana_info",
        ]

        logging.info("✅ Telegram Monitor initialized")

    # ====================================================
    #  ВСПОМОГАТЕЛЬНОЕ: проверка, что это наш алерт-чат
    # ====================================================

    def _is_alert_entity(self, entity) -> bool:
        if not self._alert_username_norm:
            return False
        username = getattr(entity, "username", None)
        if not username:
            return False
        return username.lstrip("@").lower() == self._alert_username_norm

    # ====================================================
    #  ЗАПУСК МОНИТОРИНГА
    # ====================================================

    async def start_monitoring(self):
        """
        1) Один раз прошиваем историю диалогов (history scan)
        2) Подписываемся на новые сообщения
        """
        logging.info("🚀 Starting Telegram monitoring...")

        await self.initial_scan()

        @self.client.on(events.NewMessage(incoming=True))
        async def message_handler(event):
            await self.analyze_message(event)

        logging.info("✅ Telegram monitoring started")

    # ====================================================
    #  НАЧАЛЬНОЕ СКАНИРОВАНИЕ ИСТОРИИ
    # ====================================================

    async def initial_scan(self):
        """
        Пройтись по диалогам и проанализировать последние N сообщений
        в каждом канале/чате, где сидит аккаунт.
        """
        logging.info("📂 Initial history scan started...")

        async for dialog in self.client.iter_dialogs(limit=self.dialogs_limit):
            entity = dialog.entity

            # Личку с пользователями пропускаем – интересуют чаты/каналы
            if dialog.is_user and isinstance(entity, User):
                continue

            # Не сканируем свой же алерт-чат
            if self._is_alert_entity(entity):
                continue

            title = getattr(entity, "title", getattr(entity, "username", "Unknown"))
            logging.info(f"   🔍 Scanning history for: {title!r}")

            try:
                async for message in self.client.iter_messages(
                    entity, limit=self.history_limit
                ):
                    if not message or not message.message:
                        continue

                    # Информация об авторе
                    sender_username = None
                    sender_name = None
                    try:
                        sender = await message.get_sender()
                        if sender:
                            sender_username = getattr(sender, "username", None)
                            first = getattr(sender, "first_name", "") or ""
                            last = getattr(sender, "last_name", "") or ""
                            sender_name = (first + " " + last).strip() or sender_username
                    except Exception:
                        pass

                    await self._process_text_for_entity(
                        entity=entity,
                        text=message.message,
                        source="history",
                        message_id=message.id,
                        sender_username=sender_username,
                        sender_name=sender_name,
                    )
            except Exception as e:
                logging.error(f"Dialog scan error: {e}")

        logging.info("✅ Initial history scan finished")

    # ====================================================
    #  ЖИВЫЕ СООБЩЕНИЯ
    # ====================================================

    async def analyze_message(self, event):
        """Анализ входящих сообщений (в реальном времени)."""
        try:
            if not event or not event.message or not event.message.text:
                return

            chat = event.chat or event.input_chat
            if chat is not None and self._is_alert_entity(chat):
                # Не анализируем свой алерт-чат, чтобы не было рекурсии
                return

            msg = event.message
            text = msg.text

            # Информация об авторе
            sender_username = None
            sender_name = None
            try:
                sender = await msg.get_sender()
                if sender:
                    sender_username = getattr(sender, "username", None)
                    first = getattr(sender, "first_name", "") or ""
                    last = getattr(sender, "last_name", "") or ""
                    sender_name = (first + " " + last).strip() or sender_username
            except Exception:
                pass

            await self._process_text_for_entity(
                entity=chat,
                text=text,
                source="live",
                message_id=msg.id,
                sender_username=sender_username,
                sender_name=sender_name,
            )

        except Exception as e:
            logging.error(f"Error analyzing message: {e}")

    # ====================================================
    #  ОБЩАЯ ЛОГИКА АНАЛИЗА ТЕКСТА
    # ====================================================

    async def _process_text_for_entity(
        self,
        entity,
        text: str,
        source: str,
        analysis: Optional[dict] = None,
        message_id: Optional[int] = None,
        sender_username: Optional[str] = None,
        sender_name: Optional[str] = None,
    ):
        """
        Общий обработчик текста:
        - прогон через KeywordManager
        - если подозрительно — сохраняем сообщение и канал, шлём алерт
        """
        if not text:
            return

        if analysis is None:
            analysis = self.keywords.analyze_text(text)

        if not analysis or not analysis.get("is_suspicious"):
            return

        title = getattr(entity, "title", "Unknown")
        username = getattr(entity, "username", None)

        logging.info(
            f"⚠️ Suspicious message in [{title!r} (@{username})] "
            f"from {source}: {text[:120].replace(chr(10), ' ')}..."
        )

        # 1) Сохраняем сообщение
        try:
            self.db.save_message(
                {
                    "channel_username": username,
                    "message_text": text,
                    "contains_drugs": analysis.get("has_drugs", False),
                    "contains_geo": analysis.get("has_geo", False),
                    "timestamp": datetime.utcnow(),
                }
            )
        except Exception as e:
            logging.error(f"Error saving suspicious message: {e}")

        # 2) Анализируем/сохраняем канал
        try:
            await self.analyze_and_save_channel(entity, found_via=source)
        except Exception as e:
            logging.error(f"Error analyzing/saving channel: {e}")

        # 3) Шлём алерт в Telegram
        try:
            await self._send_alert(
                entity=entity,
                text=text,
                analysis=analysis,
                source=source,
                message_id=message_id,
                sender_username=sender_username,
                sender_name=sender_name,
            )
        except Exception as e:
            logging.error(f"Error sending alert: {e}")

    # ====================================================
    #  РУЧНОЙ СКАН ОТДЕЛЬНОГО ЧАТА / КАНАЛА
    # ====================================================

    async def manual_scan_chat(self, identifier: str, limit: int = 1500) -> dict:
        """
        Ручной запуск сканирования конкретного чата/канала.
        identifier: @username, ссылка t.me/... или просто username.
        """
        ident_raw = (identifier or "").strip()
        if not ident_raw:
            raise ValueError("Пустое имя канала/чата")

        ident = ident_raw
        if ident.startswith("http://") or ident.startswith("https://"):
            ident = ident.split("/")[-1]
        if ident.startswith("@"):
            ident = ident[1:]

        try:
            channel = await self.client.get_entity(ident)
        except Exception as e:
            logging.error(f"Manual scan: cannot resolve {ident_raw!r}: {e}")
            return {
                "ok": False,
                "error": str(e),
                "identifier": ident_raw,
                "scanned": 0,
                "suspicious": 0,
                "title": ident_raw,
            }

        if self._is_alert_entity(channel):
            return {
                "ok": False,
                "error": "Нельзя сканировать алерт-канал",
                "identifier": ident_raw,
                "scanned": 0,
                "suspicious": 0,
                "title": getattr(channel, "title", ident_raw),
            }

        title = getattr(channel, "title", getattr(channel, "username", ident))
        logging.info(
            f"🔎 Manual scan started for [{title!r}] ({ident_raw}), "
            f"last {limit} messages..."
        )

        scanned = 0
        suspicious = 0

        async for msg in self.client.iter_messages(channel, limit=limit):
            if not msg or not msg.message:
                continue

            scanned += 1

            # инфа об авторе
            sender_username = None
            sender_name = None
            try:
                sender = await msg.get_sender()
                if sender:
                    sender_username = getattr(sender, "username", None)
                    first = getattr(sender, "first_name", "") or ""
                    last = getattr(sender, "last_name", "") or ""
                    sender_name = (first + " " + last).strip() or sender_username
            except Exception:
                pass

            analysis = self.keywords.analyze_text(msg.message)
            if analysis.get("is_suspicious"):
                suspicious += 1

            await self._process_text_for_entity(
                entity=channel,
                text=msg.message,
                source="manual_scan",
                analysis=analysis,
                message_id=msg.id,
                sender_username=sender_username,
                sender_name=sender_name,
            )

        logging.info(
            f"✅ Manual scan finished for [{title!r}]: "
            f"scanned={scanned}, suspicious={suspicious}"
        )

        return {
            "ok": True,
            "identifier": ident_raw,
            "title": title,
            "scanned": scanned,
            "suspicious": suspicious,
        }

    # ====================================================
    #  ОТПРАВКА АЛЕРТА В ТГ
    # ====================================================

    async def _send_alert(
        self,
        entity,
        text: str,
        analysis: dict,
        source: str,
        message_id: Optional[int] = None,
        sender_username: Optional[str] = None,
        sender_name: Optional[str] = None,
    ):
        """Отправка алерта в Telegram-чат/канал."""
        if not self.alert_chat:
            return

        if self._is_alert_entity(entity):
            # Не шлём алерты в сам алерт-канал как источник
            return

        try:
            title = getattr(entity, "title", getattr(entity, "username", "Unknown"))
            username = getattr(entity, "username", None)

            # красивые триггеры
            triggers = []
            if analysis.get("has_drugs"):
                triggers.append("drugs")
            if analysis.get("has_geo"):
                triggers.append("kz_geo")
            trig_str = ", ".join(triggers) if triggers else "—"

            risk = analysis.get("risk_score", 0.0) * 100
            risk_str = f"{risk:.0f}%"

            link_part = f"@{username}" if username else "(без username)"

            # Автор
            if sender_username:
                author_str = f"@{sender_username}"
            elif sender_name:
                author_str = sender_name
            else:
                author_str = "неизвестен"

            # Ссылка на сообщение (если есть публичный username)
            message_link = None
            if username and message_id:
                message_link = f"https://t.me/{username}/{message_id}"

            msg = (
                "🚨 *Подозрительное сообщение обнаружено*\n\n"
                f"*Канал/чат:* {title} {link_part}\n"
                f"*Источник:* `{source}`\n"
                f"*Автор:* {author_str}\n"
                f"*Ссылка:* {message_link or 'недоступна'}\n"
                f"*Риск:* {risk_str}\n"
                f"*Триггеры:* `{trig_str}`\n\n"
                f"```{text[:350]}```"
            )

            await self.client.send_message(
                self.alert_chat,
                msg,
                parse_mode="markdown",
            )

        except Exception as e:
            logging.error(f"Error sending alert: {e}")

    # ====================================================
    #  АНАЛИЗ КАНАЛА / ЧАТА
    # ====================================================

    async def analyze_and_save_channel(self, channel_entity, found_via: str):
        """Анализ и сохранение канала/чата.

        ВАЖНО: теперь мы сохраняем канал ВСЕГДА, если он был проанализирован,
        даже если риск низкий. Это нужно, чтобы дашборд и вкладка "Каналы"
        всегда отображали то, что реально сканировалось.
        """
        try:
            channel = await self.client.get_entity(channel_entity)

            channel_type = (
                "channel"
                if hasattr(channel, "broadcast") and channel.broadcast
                else "chat"
            )

            channel_info = {
                "username": getattr(channel, "username", None),
                "title": getattr(channel, "title", "Unknown"),
                "participants_count": getattr(channel, "participants_count", 0),
                "found_via": found_via,
                "description": getattr(channel, "about", ""),
                "channel_type": channel_type,
            }

            # анализ географии
            kz_ratio = await self.analyze_geography(channel)
            channel_info["kz_phone_ratio"] = kz_ratio

            # анализ контента
            risk_score = await self.analyze_content(channel)
            channel_info["risk_score"] = risk_score

            # 🔥 Сохраняем ВСЕГДА, даже если risk_score очень маленький
            self.db.save_channel(channel_info)

            logging.info(
                f"💾 Saved channel: {channel_info['title']} "
                f"(risk: {risk_score:.2f}, kz_ratio: {kz_ratio:.2f}, via={found_via})"
            )

        except Exception as e:
            logging.error(f"Error analyzing channel: {e}")

    async def analyze_geography(self, channel):
        """Анализ географии подписчиков (без падения при ошибках прав)."""
        try:
            participants = await self.client.get_participants(channel, limit=10)
            kz_count = 0
            total = 0

            for user in participants:
                phone = getattr(user, "phone", None)
                if not phone:
                    continue

                total += 1
                if phone.startswith("+77") or phone.startswith("77"):
                    kz_count += 1

            return kz_count / total if total > 0 else 0.0

        except Exception:
            return 0.0

    async def analyze_content(self, channel):
        """Анализ контента канала по последним сообщениям."""
        try:
            messages = await self.client.get_messages(channel, limit=15)
            suspicious_count = 0
            total_messages = 0

            for message in messages:
                if not message or not message.text:
                    continue

                total_messages += 1
                analysis = self.keywords.analyze_text(message.text)
                if analysis.get("is_suspicious"):
                    suspicious_count += 1

            risk_score = (
                suspicious_count / total_messages if total_messages > 0 else 0.0
            )
            return min(risk_score, 1.0)

        except Exception as e:
            logging.warning(f"Content analysis error: {e}")
            return 0.0