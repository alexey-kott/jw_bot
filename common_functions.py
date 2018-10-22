import re

import sqlite3
from typing import Tuple, List

from bs4 import BeautifulSoup

from aiohttp import ClientSession

from models import Article

MAIN_URL = "https://www.jw.org/"


def init_routing():
    with open("routing.sql", "r") as f:
        route = f.read()
        route = re.sub(r'\n', '', route)
        route = re.sub(r'\s+', ' ', route)
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM routing;")  # сначала очистим таблицу роутинга
        conn.commit()

        cursor.execute(route)
        conn.commit()
        conn.close()


async def get_page_source(url, params=None):
    async with ClientSession() as session:
        async with session.get(url, params=params) as response:
            return await response.text()


async def create_or_get_article(href: str) -> int:
    try:
        article = Article.select().where(Article.site_url == href).get()
        return article
    except Exception:
        pass
    page_source = await get_page_source(f"{MAIN_URL}{href}")
    soup = BeautifulSoup(page_source, 'lxml')

    print(soup.find_all(class_='contentBody'))

    return 1


async def get_articles(journal_name: str, year: int) -> List[Tuple[str, str]]:
    params = {
        'contentLanguageFilter': 'ru',
        'pubFilter': journal_name,
        'yearFilter': year
    }
    page_source = await get_page_source(f"{MAIN_URL}/ru/публикации/журналы/", params=params)
    soup = BeautifulSoup(page_source, 'lxml')

    articles = []
    for item in soup.find_all(class_='publicationDesc'):
        article_id = await create_or_get_article(item.h3.a['href'])
        articles.append((item.h3.a.text, article_id))

    return articles

