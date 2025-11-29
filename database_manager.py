import sqlite3
import logging
import os
from datetime import datetime


class DatabaseManager:
    def __init__(self, db_name: str = "kz_drug_shops.db"):
        self.db_name = db_name

        # Если файла ещё нет – создаём
        if not os.path.exists(self.db_name):
            logging.info("📁 Создание новой базы данных...")
        else:
            logging.info("📁 Используется существующая база данных.")

        self.setup_database()

    def setup_database(self):
        """Инициализация базы данных с нужной структурой."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        # Таблица каналов
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS suspicious_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                title TEXT,
                participants_count INTEGER DEFAULT 0,
                kz_phone_ratio REAL DEFAULT 0,
                risk_score REAL DEFAULT 0,
                found_via TEXT,
                description TEXT,
                channel_type TEXT DEFAULT 'unknown',
                last_checked TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """
        )

        # Таблица сообщений
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT,
                message_text TEXT,
                contains_drugs BOOLEAN,
                contains_geo BOOLEAN,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.commit()
        conn.close()
        logging.info("✅ База данных готова к использованию")

    # =====================================================
    #  СОХРАНЕНИЕ ДАННЫХ
    # =====================================================

    def save_channel(self, channel_data: dict):
        """Сохранение подозрительного канала."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO suspicious_channels
                (username, title, participants_count, kz_phone_ratio, risk_score,
                 found_via, description, channel_type, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    channel_data.get("username"),
                    channel_data.get("title", "Unknown"),
                    channel_data.get("participants_count", 0),
                    channel_data.get("kz_phone_ratio", 0.0),
                    channel_data.get("risk_score", 0.0),
                    channel_data.get("found_via", "unknown"),
                    channel_data.get("description", ""),
                    channel_data.get("channel_type", "unknown"),
                    datetime.now(),
                ),
            )

            conn.commit()
            logging.info(f"💾 Канал сохранён: {channel_data.get('title')}")
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения канала: {e}")
        finally:
            conn.close()

    def save_message(self, message_data: dict):
        """Сохранение подозрительного сообщения."""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO channel_messages
                (channel_username, message_text, contains_drugs, contains_geo, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    message_data.get("channel_username"),
                    message_data.get("message_text", ""),
                    bool(message_data.get("contains_drugs", False)),
                    bool(message_data.get("contains_geo", False)),
                    message_data.get("timestamp", datetime.now()),
                ),
            )

            conn.commit()
            logging.info(
                f"💾 Сообщение сохранено (канал={message_data.get('channel_username')})"
            )
        except Exception as e:
            logging.error(f"❌ Ошибка сохранения сообщения: {e}")
        finally:
            conn.close()

    # =====================================================
    #  ЧТЕНИЕ ДАННЫХ ДЛЯ ДАШБОРДА/КАНАЛОВ
    # =====================================================

    def get_suspicious_channels(self, limit: int = 50):
        """Получение списка подозрительных каналов."""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM suspicious_channels
            WHERE is_active = TRUE
            ORDER BY risk_score DESC
            LIMIT ?
        """,
            (limit,),
        )

        channels = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return channels

    def get_all_channels(self):
        """Получение всех каналов."""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM suspicious_channels
            ORDER BY risk_score DESC
        """
        )

        channels = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return channels

    def get_channels_by_type(self, channel_type: str | None = None):
        """Получение каналов по типу."""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if channel_type:
            cursor.execute(
                """
                SELECT * FROM suspicious_channels
                WHERE channel_type = ? AND is_active = TRUE
                ORDER BY risk_score DESC
            """,
                (channel_type,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM suspicious_channels
                WHERE is_active = TRUE
                ORDER BY risk_score DESC
            """
            )

        channels = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return channels

    def get_channel_stats(self):
        """Статистика по типам каналов."""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT channel_type, COUNT(*) as count,
                   AVG(risk_score) as avg_risk,
                   SUM(CASE WHEN risk_score >= 0.7 THEN 1 ELSE 0 END) as high_risk_count
            FROM suspicious_channels
            WHERE is_active = TRUE
            GROUP BY channel_type
        """
        )

        stats = {}
        for row in cursor.fetchall():
            stats[row["channel_type"]] = {
                "count": row["count"],
                "avg_risk": row["avg_risk"] if row["avg_risk"] else 0,
                "high_risk_count": row["high_risk_count"],
            }

        cursor.execute(
            "SELECT COUNT(*) as cnt FROM suspicious_channels WHERE is_active = TRUE"
        )
        total_active = cursor.fetchone()["cnt"]

        cursor.execute(
            """
            SELECT COUNT(*) as cnt
            FROM suspicious_channels
            WHERE risk_score >= 0.7 AND is_active = TRUE
        """
        )
        total_high_risk = cursor.fetchone()["cnt"]

        conn.close()

        return {
            "by_type": stats,
            "total_active": total_active,
            "total_high_risk": total_high_risk,
        }

    def get_stats(self):
        """Совместимость со старым кодом."""
        return self.get_channel_stats()

    # =====================================================
    #  СООБЩЕНИЯ ДЛЯ /messages
    # =====================================================

    def get_suspicious_messages(
        self, channel_username: str | None = None, limit: int = 500
    ):
        """
        Возвращает список подозрительных сообщений
        (минимум: contains_drugs = 1), с привязкой к каналам.
        """
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        base_sql = """
            SELECT
                m.id,
                m.channel_username,
                m.message_text,
                m.contains_drugs,
                m.contains_geo,
                m.timestamp,
                c.title AS channel_title,
                c.risk_score
            FROM channel_messages m
            LEFT JOIN suspicious_channels c
                ON m.channel_username = c.username
            WHERE m.contains_drugs = 1
        """
        params: list = []

        if channel_username:
            base_sql += " AND m.channel_username = ?"
            params.append(channel_username)

        base_sql += " ORDER BY m.timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(base_sql, tuple(params))
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            row_dict = dict(row)

            # собираем триггеры для красивого отображения
            triggers = []
            if row_dict.get("contains_drugs"):
                triggers.append("drugs")
            if row_dict.get("contains_geo"):
                triggers.append("kz_geo")

            row_dict["triggers"] = ", ".join(triggers)
            # если risk_score нет (канал ещё не в suspicious_channels) – ставим 0
            if row_dict.get("risk_score") is None:
                row_dict["risk_score"] = 0.0

            messages.append(row_dict)

        return messages
