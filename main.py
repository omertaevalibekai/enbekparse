import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import sqlite3
from pathlib import Path

from agent import run_scraper
from models import SearchQuery
from storage import get_all_candidates, init_db

DB_PATH = Path(__file__).parent / "candidates.db"


def cmd_show():
    init_db()
    candidates = get_all_candidates()
    if not candidates:
        print("База пустая. Сначала запустите парсер.")
        return
    print(f"\n{'='*65}")
    print(f"Резюме в базе: {len(candidates)}")
    print(f"{'='*65}")
    for c in candidates:
        print(f"\n  Должность: {c['position']}")
        if c.get("full_name"):
            print(f"  Имя:       {c['full_name']}")
        if c.get("phone"):
            print(f"  Телефон:   {c['phone']}")
        if c.get("name"):
            print(f"  Пол/возр.: {c['name']}")
        print(f"  Город:     {c['city'] or '—'}")
        print(f"  Зарплата:  {c['salary'] or '—'}")
        print(f"  Стаж:      {c['experience'] or '—'}")
        if c.get("work_history"):
            print(f"  Опыт:      {c['work_history']}")
        print(f"  Образов.:  {c['education'] or '—'}")
        if c.get("skills"):
            print(f"  Навыки:    {c['skills'][:80]}...")
        if c.get("languages"):
            print(f"  Языки:     {c['languages']}")
        print(f"  Ссылка:    {c['profile_url']}")
    print(f"\n{'='*65}")


def cmd_clear():
    if not DB_PATH.exists():
        print("База и так пустая.")
        return
    confirm = input("Удалить все резюме из базы? (да/нет): ").strip().lower()
    if confirm in ("да", "y", "yes"):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM candidates")
        print("База очищена.")
    else:
        print("Отменено.")


def main():
    parser = argparse.ArgumentParser(
        description="enbek.kz Resume Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python main.py --keyword менеджер --location Алматы --pages 3
  python main.py --keyword разработчик --exp 1-3 --email you@mail.kz --password MyPass
  python main.py --show
  python main.py --clear

Авторизация (--email/--phone + --password):
  Раскрывает имя и телефон каждого кандидата.
  Сессия сохраняется в session.json — повторный логин не нужен.
        """,
    )
    parser.add_argument("--keyword",  default="", help="Должность / ключевое слово")
    parser.add_argument("--location", default="", help="Город (Алматы, Астана, Шымкент, ...)")
    parser.add_argument("--exp",      default="", help="Опыт: no | 1-3 | 3-6 | 6+")
    parser.add_argument("--pages",    type=int, default=3, help="Кол-во страниц (по ~10 резюме)")
    parser.add_argument("--email",    default="", help="Логин enbek.kz (email или телефон)")
    parser.add_argument("--password", default="", help="Пароль enbek.kz")
    parser.add_argument("--any-city", action="store_true",
                        help="Не фильтровать по городу (брать всё, что выдал enbek)")
    parser.add_argument("--show",     action="store_true", help="Показать резюме из базы")
    parser.add_argument("--clear",    action="store_true", help="Очистить базу")
    parser.add_argument("--visible",  action="store_true", help="Показать браузер")
    args = parser.parse_args()

    if args.show:
        cmd_show()
        return
    if args.clear:
        cmd_clear()
        return

    query = SearchQuery(
        keyword=args.keyword,
        location=args.location,
        experience=args.exp,
        max_pages=args.pages,
        strict_city=not args.any_city,
    )

    credential = args.email or args.password  # если передан только пароль — игнорируем
    if args.email and not args.password:
        print("  Предупреждение: --email указан без --password, контакты не будут раскрыты")
        credential = ""

    print(f"\nenbek.kz Recruiter  |  185 000+ резюме")
    print(f"  Должность: '{query.keyword or 'все'}'")
    city_mode = "строго" if query.strict_city and query.location else "включая соседние"
    print(f"  Город:     '{query.location or 'все'}' ({city_mode})")
    print(f"  Опыт:      '{query.experience or 'любой'}'")
    print(f"  Страниц:   {query.max_pages}")
    print(f"  Контакты:  {'ДА (авторизация)' if args.email and args.password else 'нет (без логина)'}")
    print()

    result = run_scraper(
        query,
        headless=not args.visible,
        credential=args.email,
        password=args.password,
    )

    print(f"\n{'='*65}")
    print(f"  Обработано за запуск: {result['processed_this_run']}")
    print(f"  Новых резюме:         {result['new_this_run']}")
    print(f"  Всего в базе:         {result['total_in_db']}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
