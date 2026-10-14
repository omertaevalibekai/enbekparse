import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from functools import partial
from typing_extensions import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END

from models import SearchQuery
from browser import EnbekScraper, city_matches
from storage import init_db, save_candidate, count_candidates


class ScraperState(TypedDict):
    query: SearchQuery
    current_page: int
    collected_urls: Annotated[list[str], operator.add]
    processed_count: int
    new_count: int
    done: bool


def collect_links_node(state: ScraperState, scraper: EnbekScraper) -> dict:
    query = state["query"]
    page_num = state["current_page"]

    links = scraper.get_links_on_page(query, page_num)
    has_next = scraper.has_next_page(page_num) and page_num < query.max_pages

    print(f"[agent] Стр {page_num}/{query.max_pages} — {len(links)} ссылок, продолжать: {has_next}")

    return {
        "collected_urls": links,
        "current_page": page_num + 1,
        "done": not has_next,
    }


def extract_and_save_node(state: ScraperState, scraper: EnbekScraper) -> dict:
    urls = state["collected_urls"]
    query = state["query"]
    processed = 0
    new = 0
    skipped = 0

    print(f"[agent] Обрабатываю {len(urls)} резюме...")

    for i, url in enumerate(urls, 1):
        candidate = scraper.extract_candidate(url)
        if not candidate:
            continue

        # Пост-фильтр по городу — enbek подмешивает соседние регионы
        if query.strict_city and not city_matches(query.location, candidate.city):
            skipped += 1
            print(f"  [{i}/{len(urls)}] [skip] {candidate.position[:40]} | {candidate.city or '—'} (другой город)")
            continue

        is_new = save_candidate(candidate)
        processed += 1
        if is_new:
            new += 1
        status = "NEW" if is_new else "dup"
        exp = f" | стаж: {candidate.experience}" if candidate.experience else ""
        print(f"  [{i}/{len(urls)}] [{status}] {candidate.position[:45]} | {candidate.city or '—'}{exp}")

    tail = f", пропущено по городу: {skipped}" if skipped else ""
    print(f"[agent] Сохранено: {new} новых, {processed - new} дубликатов{tail}")
    return {
        "processed_count": state["processed_count"] + processed,
        "new_count": state["new_count"] + new,
        "collected_urls": [],
    }


def should_continue(state: ScraperState) -> str:
    return "extract_and_save" if state["done"] else "collect_links"


def run_scraper(query: SearchQuery, headless: bool = True,
                credential: str = "", password: str = "") -> dict:
    from browser import SESSION_FILE
    init_db()
    scraper = EnbekScraper(headless=headless)
    scraper.start()
    try:
        # Проверяем сохранённую сессию или логинимся заново
        if SESSION_FILE.exists():
            scraper.check_session()
        if not scraper._logged_in and credential and password:
            scraper.login(credential, password)
        graph = StateGraph(ScraperState)
        graph.add_node("collect_links",    partial(collect_links_node,    scraper=scraper))
        graph.add_node("extract_and_save", partial(extract_and_save_node, scraper=scraper))
        graph.set_entry_point("collect_links")
        graph.add_conditional_edges(
            "collect_links", should_continue,
            {"collect_links": "collect_links", "extract_and_save": "extract_and_save"},
        )
        graph.add_edge("extract_and_save", END)
        app = graph.compile()

        final = app.invoke({
            "query": query,
            "current_page": 1,
            "collected_urls": [],
            "processed_count": 0,
            "new_count": 0,
            "done": False,
        })
        return {
            "total_in_db":        count_candidates(),
            "processed_this_run": final["processed_count"],
            "new_this_run":       final["new_count"],
        }
    finally:
        scraper.stop()
