import re


class KeywordManager:
    def __init__(self):
        # ключевые слова по нарко-тематике
        self.drug_keywords = self._load_drug_keywords()
        # гео по Казахстану
        self.kz_cities = self._load_kz_cities()
        # эмодзи, часто используемые вместо слов
        self.drug_emojis = []

        # двусмысленные слова, которые часто встречаются в нормальных текстах
        # и сами по себе не гарантируют нарко-тему
        self.ambiguous_drug_keywords = {
            "закладка",
            "закладки",
            "семена",
            "семя",
            "марки",
            "марка",
            "ice",
            "айс",
        }

        # слова, которые обычно встречаются в вакансии / объявлении о работе
        self.job_context_keywords = self._load_job_context_keywords()

    # ==========================
    #  НАБОРЫ КЛЮЧЕВЫХ СЛОВ
    # ==========================

    def _load_drug_keywords(self):
        """
        Расширяем список по максимуму.
        Любое слово отсюда => кандидат в has_drugs,
        но потом часть "мягких" слов может отфильтроваться по контексту.
        """
        return [
            # базовое
            "закладка",
            "закладки",
            "клад",
            "кладмен",
            "закладчик",

            # меф, амф и т.п.
            "меф",
            "мефедрон",
            "мефик",
            "мефчик",
            "мефушка",

            "спиды",
            "амф",
            "амфетамин",
            "фенамин",

            # соль / кристаллы
            "соль",
            "соли",
            "кристалл",
            "кристаллы",
            "кристал",
            "кристалы",

            # экстази / мдма
            "экстази",
            "мдма",
            "таблы",
            "таблетки счастья",

            # травка / гаш / шишки
            "шишки",
            "шишка",
            "гаш",
            "гашиш",
            "марихуана",
            "каннабис",
            "конопля",

            # лсд / марки
            "лсд",
            "марки",
            "марка",

            # сленг
            "белочка",

            # тяжёлые
            "кокаин",
            "кокс",
            "героин",
            "гер",
            "опиум",
            "опиаты",

            # ==== ДОБАВЛЕНО ИЗ КАТАЛОГА ФАЙЛА ====

            # стимуляторы
            "метамфетамин",
            "a-pvp",
            "a-pvp кристаллы",
            "a-pvp мука",

            # эйфоретики
            "мефедрон кристаллы",
            "мефедрон кристаллическая пудра",
            "мефедрон мука",
            "мда",

            # марихуана / товары
            "cannafood",
            "семена",

            # психоделики
            "nbome",
            "2с",
            "2с-b",
            "2с-i",
            "2с-e",
            "2с-p",

            # аптека
            "антидепрессанты",
            "депрессанты",
            "диссоциативы",
            "нейролептики",
            "ноотропы",

            # англ/сленг
            "ice",
            "айс",
            "mdma",
            "mda",
            "lsd",
            "acid",
            "weed",
            "hash",
            "hashish",
            "psy",
            "trip",
            "trips",
        ]

    def _load_kz_cities(self):
        # TODO: при желании можно забить сюда список городов РК
        return []

    def _load_job_context_keywords(self):
        """
        Слова, которые почти всегда встречаются в нормальных вакансиях / резюме.
        Если они есть, и при этом только мягкие триггеры типа 'закладка',
        то объявление считаем обычным.
        """
        return [
            "вакансия",
            "обязанности",
            "обязанность",
            "требования",
            "требуется",
            "зарплата",
            "зп",
            "kzt",
            "тенге",
            "тг",
            "оплата",
            "график работы",
            "график",
            "смены",
            "работа",
            "работать",
            "соц пакет",
            "соц. пакет",
            "оформление",
            "оформление по тк",
            "официальное трудоустройство",
            "трудовой отпуск",
            "столовая",
            "обед",
            "выходные",
            "рабочая неделя",
            "пятидневка",
            "сменный график",
            "полная занятость",
            "частичная занятость",
            "опыт работы",
            "без опыта",
            "контакты",
            "резюме",
            "email",
            "@gmail.com",
            "@mail.ru",
            "@yandex.ru",
        ]

    # ==========================
    #  ПОИСК СОВПАДЕНИЙ
    # ==========================

    def _normalize(self, text: str) -> str:
        return text.lower()

    def _has_job_context(self, text: str) -> bool:
        """
        Проверяем, похоже ли сообщение на вакансию/объявление о работе.
        Достаточно, чтобы встретилось хотя бы одно ключевое слово из списка.
        """
        if not text or not isinstance(text, str):
            return False

        text_norm = self._normalize(text)

        for kw in self.job_context_keywords:
            if kw in text_norm:
                return True

        return False

    def contains_drug_keywords(self, text: str):
        """
        Возвращает список найденных триггеров по нарко-тематике
        БЕЗ учёта контекста (фильтрация по объявлениям будет дальше).
        """
        if not text or not isinstance(text, str):
            return []

        text_norm = self._normalize(text)
        triggers = set()

        # обычные слова
        for kw in self.drug_keywords:
            if re.search(rf"\b{re.escape(kw)}\b", text_norm):
                triggers.add(kw)

        # эмодзи
        for emo in self.drug_emojis:
            if emo in text:
                triggers.add(emo)

        return list(triggers)

    def contains_kz_geo(self, text: str):
        """
        Возвращает список найденных гео-триггеров по Казахстану.
        """
        if not text or not isinstance(text, str):
            return []

        text_norm = self._normalize(text)
        triggers = set()

        for city in self.kz_cities:
            if city in text_norm:
                triggers.add(city)

        # общие слова
        common_geo = []
        for g in common_geo:
            if re.search(rf"\b{re.escape(g)}\b", text_norm):
                triggers.add(g)

        return list(triggers)

    # ==========================
    #  ОСНОВНОЙ АНАЛИЗ ТЕКСТА
    # ==========================

    def analyze_text(self, text: str):
        """
        Главная функция анализа.
        ЛЮБОЕ найденное "сильное" наркотическое слово => is_suspicious = True.
        Но если в тексте только двусмысленные слова (типа "закладка") и явный
        контекст вакансии, считаем такое сообщение НЕ подозрительным.
        """
        if not text:
            return {
                "has_drugs": False,
                "has_geo": False,
                "is_suspicious": False,
                "risk_score": 0.0,
                "triggers": [],
                "trigger_summary": "",
            }

        # собираем триггеры без учёта контекста
        raw_drug_hits = self.contains_drug_keywords(text)
        geo_hits = self.contains_kz_geo(text)

        # проверяем контекст вакансии
        looks_like_job = self._has_job_context(text)

        drug_hits = list(raw_drug_hits)

        # ===== ФИЛЬТР ВАКАНСИЙ / ОБЪЯВЛЕНИЙ =====
        # если все найденные слова ДВУСМЫСЛЕННЫЕ и это похоже на вакансию,
        # то выкидываем такие "триггеры" полностью
        if drug_hits and looks_like_job:
            if all(h in self.ambiguous_drug_keywords for h in drug_hits):
                logging = False  # просто чтобы было куда поставить брейкпоинт, если нужно
                drug_hits = []

        has_drugs = len(drug_hits) > 0
        has_geo = len(geo_hits) > 0

        # базовый риск
        risk = 0.0
        if has_drugs:
            risk += 0.7
        if has_geo:
            risk += 0.3

        risk_score = min(risk, 1.0)

        # подозрительно только если после фильтрации остались нарко-слова
        is_suspicious = has_drugs

        # собираем список триггеров для UI
        triggers = []
        if drug_hits:
            triggers.extend(drug_hits)
        if geo_hits:
            triggers.append("kz_geo")

        trigger_summary = ", ".join(sorted(set(triggers)))

        return {
            "has_drugs": has_drugs,
            "has_geo": has_geo,
            "is_suspicious": is_suspicious,
            "risk_score": risk_score,
            "triggers": triggers,
            "trigger_summary": trigger_summary,
        }

    # ==========================
    #  ВСПОМОГАТЕЛЬНОЕ
    # ==========================

    def extract_links(self, text):
        if not text:
            return []
        return re.findall(r"t\.me/[\w@]+", text)
