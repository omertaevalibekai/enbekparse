"""
Playwright-скрапер для enbek.kz — государственная биржа труда Казахстана.
Резюме публично доступны без авторизации (185 000+ резюме).
Имя и телефон доступны только после авторизации (--email/--password).
"""
import json
import re
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

from models import Candidate, SearchQuery

BASE_URL = "https://www.enbek.kz"
SEARCH_URL = f"{BASE_URL}/ru/search/resume"
LOGIN_URL = "https://passport.enbek.kz/ru/user/login?redirect_uri=https://www.enbek.kz/ru&redirect=strict"
SESSION_FILE = Path(__file__).parent / "session.json"

REGIONS = {
    "алматы":           "almaty",
    "астана":           "astana",
    "нур-султан":       "astana",
    "шымкент":          "shymkent",
    "актобе":           "aktobe",
    "атырау":           "atyrau",
    "актау":            "aktau",
    "павлодар":         "pavlodar",
    "усть-каменогорск": "ust-kamenogorsk",
    "семей":            "semey",
    "костанай":         "kostanay",
    "петропавловск":    "petropavlovsk",
    "кызылорда":        "kyzylorda",
    "уральск":          "uralsk",
    "тараз":            "taraz",
    "кокшетау":         "kokshetau",
    "талдыкорган":      "taldykorgan",
    "туркестан":        "turkestan",
    "алматинская":      "almaty_reg",
    "акмолинская":      "akmola",
}

EXPERIENCE_MAP = {
    "no":  "e0",
    "1-3": "e1",
    "3-6": "e2",
    "6+":  "e3",
}

_NOT_POSITION = frozenset([
    "найти", "поиск", "search", "войти", "регистрация", "главная",
    "резюме", "вакансии", "показать", "скрыть", "ещё", "еще",
    "отмена", "продолжить", "следующая", "назад",
])


def _delay(min_s=0.5, max_s=1.2):
    time.sleep(random.uniform(min_s, max_s))


def _extract_id(url: str) -> str:
    m = re.search(r"~(\d+)", url)
    return m.group(1) if m else url.split("/")[-1]


def city_matches(location: str, city: Optional[str]) -> bool:
    """True, если резюме относится к запрошенному городу.

    enbek.kz указывает город как "г.<Город>" (напр. "г.Астана, район Алматы").
    Матчим именно маркер города, чтобы район с тем же названием не ловился:
    запрос "Алматы" не должен цеплять "г.Астана, район Алматы".
    """
    if not location:
        return True
    if not city:
        return False
    loc = re.sub(r"^г\.?\s*", "", location.lower().strip())
    city_norm = re.sub(r"г\.\s*", "г.", city.lower())
    if "г." in city_norm:
        return f"г.{loc}" in city_norm
    # Нет маркера города (область/село) — простое вхождение
    return loc in city_norm


class EnbekScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page: Optional[Page] = None
        self._logged_in = False

    def start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx_opts = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="ru-KZ",
        )
        # Загружаем сохранённую сессию если есть
        if SESSION_FILE.exists():
            try:
                state = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                ctx_opts["storage_state"] = state
            except Exception:
                pass

        self._ctx = self._browser.new_context(**ctx_opts)
        self._page = self._ctx.new_page()
        print("  [browser] Запущен (enbek.kz)")

    def stop(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def login(self, credential: str, password: str) -> bool:
        """Авторизация через passport.enbek.kz. credential — email или телефон."""
        print("  [auth] Вхожу в enbek.kz...")
        try:
            self._page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            _delay(1.0, 1.5)

            # Выбираем вкладку Email или Телефон
            is_phone = credential.startswith("+7") or credential.startswith("8") or credential.isdigit()
            if is_phone:
                # Кликаем радио "Телефон"
                phone_radio = self._page.query_selector("input[name='contact'][value='phone'], label:has-text('Телефон')")
                if phone_radio:
                    phone_radio.click()
                    _delay(0.3, 0.5)
                phone_input = self._page.query_selector("input[type='tel']")
                if phone_input:
                    phone_input.fill(credential)
            else:
                email_input = self._page.query_selector("input[name='email']")
                if email_input:
                    email_input.fill(credential)

            pw_input = self._page.query_selector("input[name='password'], input[type='password']")
            if pw_input:
                pw_input.fill(password)

            _delay(0.3, 0.5)
            submit = self._page.query_selector("button[type='submit'], button:has-text('Войти')")
            if submit:
                submit.click()
            else:
                self._page.keyboard.press("Enter")

            # Ждём редиректа на enbek.kz
            try:
                self._page.wait_for_url("**/enbek.kz/**", timeout=15000)
            except PWTimeout:
                pass

            _delay(1.0, 1.5)
            current_url = self._page.url

            # Проверяем успех
            if "passport.enbek.kz" in current_url:
                # Смотрим есть ли ошибка
                body = self._page.inner_text("body")
                if "неверн" in body.lower() or "ошибка" in body.lower() or "invalid" in body.lower():
                    print("  [auth] Ошибка: неверный логин или пароль")
                    return False
                print("  [auth] Редирект не произошёл — возможно нужна верификация")
                return False

            # Сохраняем сессию
            state = self._ctx.storage_state()
            SESSION_FILE.write_text(json.dumps(state), encoding="utf-8")
            self._logged_in = True
            print("  [auth] Успешно! Сессия сохранена.")
            return True

        except Exception as e:
            print(f"  [auth] Ошибка входа: {e}")
            return False

    def check_session(self) -> bool:
        """Проверяет, активна ли сохранённая сессия."""
        if not SESSION_FILE.exists():
            return False
        try:
            self._page.goto(BASE_URL + "/ru", wait_until="domcontentloaded", timeout=15000)
            _delay(0.8, 1.2)
            body = self._page.inner_text("body")
            # Если авторизован — нет кнопки "Войти" или есть имя профиля
            logged = "Войти" not in body or "Личный кабинет" in body or "Выйти" in body
            if logged:
                self._logged_in = True
                print("  [auth] Сессия активна (использую сохранённые cookies)")
            return logged
        except Exception:
            return False

    def _build_url(self, query: SearchQuery, page: int = 1) -> str:
        params: dict = {}
        if query.location:
            region = REGIONS.get(query.location.lower().strip())
            if region:
                params["region"] = region
        if query.keyword:
            params["prof"] = query.keyword
        if query.experience and query.experience in EXPERIENCE_MAP:
            params["experience"] = EXPERIENCE_MAP[query.experience]
        if page > 1:
            params["page"] = page
        qs = urlencode(params, encoding="utf-8") if params else ""
        return f"{SEARCH_URL}?{qs}" if qs else SEARCH_URL

    def get_links_on_page(self, query: SearchQuery, page_num: int) -> list[str]:
        url = self._build_url(query, page_num)
        print(f"  [browser] Страница {page_num}: {url}")

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except PWTimeout:
            print(f"  [browser] Таймаут страницы {page_num}")
            return []
        _delay(1.0, 1.5)

        links = set()
        for el in self._page.query_selector_all("a[href*='/ru/resume/']"):
            href = el.get_attribute("href") or ""
            if href.startswith("/"):
                href = BASE_URL + href
            href = href.split("?")[0]
            if "/ru/resume/" in href and "~" in href:
                links.add(href)

        print(f"  [browser] Найдено {len(links)} резюме")
        return list(links)

    def has_next_page(self, page_num: int) -> bool:
        try:
            nxt = self._page.query_selector(
                f"a[href*='page={page_num + 1}'], "
                "a[rel='next'], "
                ".pagination .next:not(.disabled)"
            )
            return nxt is not None
        except Exception:
            return False

    def _get_contacts(self) -> tuple[Optional[str], Optional[str]]:
        """Кликает 'Показать контактные данные' и возвращает (full_name, phone)."""
        try:
            btn = self._page.query_selector(
                "button:has-text('Показать контактные данные'), "
                "a:has-text('Показать контактные данные')"
            )
            if not btn:
                return None, None

            btn.click()
            _delay(1.5, 2.5)

            # После клика контакты могут появиться инлайн или в модале
            body_after = self._page.inner_text("body")

            full_name = None
            phone = None

            # Телефон — ищем в формате +7XXXXXXXXXX или 8XXXXXXXXXX
            phone_m = re.search(r"(\+7[\s\-\(]?\d{3}[\s\-\(]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})", body_after)
            if not phone_m:
                phone_m = re.search(r"(8[\s\-\(]?\d{3}[\s\-\(]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})", body_after)
            if phone_m:
                phone = re.sub(r"[\s\-]", "", phone_m.group(1))

            # Имя — после "Контактное лицо", "Имя", "ФИО" или до номера
            name_m = re.search(
                r"(?:Контактное лицо|ФИО|Имя|Соискатель)\s*:?\s*\n?([А-ЯЁа-яёA-Za-z][^\n]{2,50})",
                body_after
            )
            if name_m:
                full_name = name_m.group(1).strip()

            # Если имя не нашли по метке — берём из тега tel: href
            if not phone:
                tel_link = self._page.query_selector("a[href^='tel:']")
                if tel_link:
                    href = tel_link.get_attribute("href") or ""
                    phone = href.replace("tel:", "").strip()

            return full_name, phone

        except Exception as e:
            print(f"  [browser] Ошибка получения контактов: {e}")
            return None, None

    def extract_candidate(self, url: str) -> Optional[Candidate]:
        _delay(0.5, 1.0)
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            _delay(0.8, 1.2)
        except Exception as e:
            print(f"  [browser] Ошибка {url}: {e}")
            return None

        enbek_id = _extract_id(url)
        body = self._page.inner_text("body")

        # Должность — строка перед "Показать контактные данные"
        position = None
        pos_m = re.search(r"\n([^\n]{3,60})\n(?:Показать контактные данные)", body)
        if pos_m:
            candidate_pos = pos_m.group(1).strip()
            if candidate_pos.lower() not in _NOT_POSITION:
                position = candidate_pos
        if not position:
            pos_m2 = re.search(r"Резюме\s*\n[^\n]+\n([^\n]{3,60})\n", body)
            if pos_m2:
                candidate_pos = pos_m2.group(1).strip()
                if candidate_pos.lower() not in _NOT_POSITION:
                    position = candidate_pos
        if not position:
            return None

        # Город/район
        city = None
        city_m = re.search(r"Город/Район\s*\n([^\n]+)", body)
        if city_m:
            city = city_m.group(1).strip()
        if not city:
            bread_m = re.search(r"Резюме\s*\n([^\n]+)\n" + re.escape(position), body)
            if bread_m:
                city = bread_m.group(1).strip()

        # Зарплата
        salary = None
        sal_m = re.search(r"((?:от|до)\s*[\d\s]{3,}\s*(?:тг|тенге|₸)[^\n]*)", body, re.IGNORECASE)
        if sal_m:
            salary = re.sub(r"\s+", " ", sal_m.group(1)).strip()

        # Опыт работы — общий стаж, напр. "3 года"
        experience = None
        exp_m = re.search(r"Опыт работы\s*\n([^\n]+)", body)
        if exp_m:
            experience = exp_m.group(1).strip()

        # Трудовая деятельность — места работы (компании, должности, периоды)
        work_history = None
        wh_m = re.search(
            r"Трудовая деятельность\s*\n([\s\S]{5,1200}?)(?:\nОбразование|\nПрофессиональные навыки|\nЗнание языков|\Z)",
            body,
        )
        if wh_m:
            raw = wh_m.group(1).strip()
            # Каждое место работы начинается с "с MM.YYYY по ..." — ставим разделитель
            raw = re.sub(r"\n(с\s+\d{2}\.\d{4})", r"  ||  \1", raw)
            work_history = re.sub(r"\n+", ", ", raw).strip(", ")[:600]

        # Пол и возраст
        gender_age = None
        ga_m = re.search(r"Пол, возраст\s*\n([^\n]+)", body)
        if ga_m:
            gender_age = ga_m.group(1).strip()

        # Образование
        education = None
        edu_m = re.search(r"Уровень образования\s*\n([^\n]+)", body)
        if edu_m:
            education = edu_m.group(1).strip()

        # Навыки
        skills = None
        skills_m = re.search(
            r"Профессиональные навыки\s*\n([\s\S]{5,400}?)(?:\nЛичные качества|\nЗнание языков|\nВозникли|\Z)", body
        )
        if skills_m:
            skills = re.sub(r"\s+", " ", skills_m.group(1)).strip()[:400]

        # Языки
        languages = None
        lang_m = re.search(r"Знание языков\s*\n([\s\S]{3,200}?)(?:\nВозникли|\nЛичные|\Z)", body)
        if lang_m:
            languages = re.sub(r"\s+", " ", lang_m.group(1)).strip()[:150]

        # Контакты (только при авторизации)
        full_name = None
        phone = None
        if self._logged_in:
            full_name, phone = self._get_contacts()

        return Candidate(
            enbek_id=enbek_id,
            position=position,
            full_name=full_name,
            phone=phone,
            name=gender_age,
            city=city,
            salary=salary,
            experience=experience,
            work_history=work_history,
            education=education,
            skills=skills,
            languages=languages,
            profile_url=url,
        )
