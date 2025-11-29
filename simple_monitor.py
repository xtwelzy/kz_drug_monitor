import asyncio
import logging
from telethon import TelegramClient, events
from config import API_ID, API_HASH, PHONE_NUMBER
from database import DatabaseManager
from keyword_manager import KeywordManager

# Простое логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


async def simple_monitor():
    """Упрощенный мониторинг без ошибок"""
    client = TelegramClient("simple_monitor", API_ID, API_HASH)
    await client.start(phone=PHONE_NUMBER)

    db = DatabaseManager()
    keywords = KeywordManager()

    print("🚀 Simple monitor started!")
    print("📱 Join Kazakh channels manually in Telegram")
    print("🔍 System will analyze all new messages")

    @client.on(events.NewMessage)
    async def handler(event):
        try:
            if event.message.text:
                text = event.message.text
                analysis = keywords.analyze_text(text)

                if analysis["is_suspicious"]:
                    print(f"🎯 FOUND SUSPICIOUS MESSAGE!")
                    print(f"   Channel: {getattr(event.chat, 'title', 'Unknown')}")
                    print(f"   Text: {text[:100]}...")

                    # Сохраняем канал
                    channel_data = {
                        "username": getattr(
                            event.chat, "username", f"id_{event.chat.id}"
                        ),
                        "title": getattr(event.chat, "title", "Unknown Channel"),
                        "participants_count": getattr(
                            event.chat, "participants_count", 0
                        ),
                        "risk_score": 0.8,
                        "found_via": "simple_monitor",
                        "description": "Automatically detected",
                    }
                    db.save_channel(channel_data)
                    print(f"💾 Channel saved to database!")

        except Exception as e:
            print(f"Error: {e}")

    print("✅ Monitoring active. Waiting for messages...")

    # Также делаем активный поиск
    async def active_search():
        while True:
            try:
                # Ищем в общих чатах
                async for dialog in client.iter_dialogs(limit=50):
                    if dialog.is_channel:
                        try:
                            messages = await client.get_messages(
                                dialog.entity, limit=10
                            )
                            for message in messages:
                                if message.text:
                                    analysis = keywords.analyze_text(message.text)
                                    if analysis["is_suspicious"]:
                                        print(
                                            f"🔍 Found in {dialog.name}: {message.text[:100]}..."
                                        )
                                        channel_data = {
                                            "username": getattr(
                                                dialog.entity,
                                                "username",
                                                f"id_{dialog.entity.id}",
                                            ),
                                            "title": dialog.name,
                                            "participants_count": getattr(
                                                dialog.entity, "participants_count", 0
                                            ),
                                            "risk_score": 0.6,
                                            "found_via": "active_scan",
                                            "description": "Found during active scan",
                                        }
                                        db.save_channel(channel_data)
                        except:
                            pass
                await asyncio.sleep(300)  # Проверка каждые 5 минут
            except Exception as e:
                print(f"Search error: {e}")
                await asyncio.sleep(60)

    asyncio.create_task(active_search())
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(simple_monitor())
