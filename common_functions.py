import logging
import re
from hashlib import sha1

import sqlite3
from pathlib import Path
from sqlite3 import IntegrityError
from typing import Tuple, List, Collection

from bs4 import BeautifulSoup, Tag, NavigableString

from aiohttp import ClientSession
from telegraph.aio import Telegraph
from telegraph.exceptions import NotAllowedTag, TelegraphException

from config import TELEGRAPH_USER_TOKEN
from models import Article, JournalIssue, Journal

MAIN_URL = "https://www.jw.org"
CHUNK_SIZE = 1024
FILE_DIR = Path("./files")

AVAILABLE_TAGS = ['a', 'aside', 'b', 'blockquote', 'br', 'code', 'em', 'figcaption', 'figure',
                  'h3', 'h4', 'hr', 'i', 'iframe', 'img', 'li', 'ol', 'p', 'pre', 's',
                  'strong', 'u', 'ul', 'video']
# AVAILABLE_TAGS = ['h1', 'h3', 'h4', 'hr', 'img', 'p', 'ul', 'ol', 'a', 'strong']

LOG_PATH = Path('./logs/log')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='./logs/log')
logger = logging.getLogger('jwwatcher')
logger.setLevel(logging.INFO)


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


def set_init_db_values():
    init_routing()


async def get_page_source(url, params=None) -> str:
    async with ClientSession() as session:
        async with session.get(url, params=params) as response:
            return await response.text()


async def download_file(file_url: str, file_name=None, params=None):
    if file_name:
        file_path = FILE_DIR / f"{file_name.rsplit('/')[1]}.mp3"
    else:
        file_path = FILE_DIR / file_url.rsplit("/")[0]

    async with ClientSession() as session:
        async with session.get(file_url, params=params) as response:
            with open(file_path, 'wb') as fd:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    fd.write(chunk)


def try_replace_link(link: str) -> str:
    article = Article.get_or_none(Article.url == link)

    if article:
        print(article.telegraph_path)
        return article.telegraph_path
    else:
        return link


def prepare_items(items: List[Tag]) -> str:
    excluded_tags = []
    for item in items:
        for descendant in item.descendants:
            if isinstance(descendant, Tag):
                if descendant.name not in AVAILABLE_TAGS:
                    if descendant.name == 'sup':
                        inner_content = f"^{descendant.string}"
                        if descendant.string is not None:
                            descendant.string.replace_with(inner_content)

                    excluded_tags.append(descendant.name)

                if descendant.name == 'a':
                    descendant.attrs['href'] = try_replace_link(descendant.attrs.get('href'))
                if descendant.name == 'h1':
                    descendant.name = 'h3'
                if descendant.name == 'h2':
                    descendant.name = 'h4'
                if descendant.name == 'img':
                    descendant.attrs['src'] = descendant.attrs['src'].replace('_xs.', '_lg.')

    for item in items:
        for excluded_tag in excluded_tags:
            tags: Collection[Tag] = item.find_all(excluded_tag)
            for tag in tags:
                tag.unwrap()

    # items = filter(lambda x: x is not None, items)

    return ''.join([str(item) for item in items])


def calc_article_hash(page_source: str) -> str:
    # s = ''.join([str(i) for i in items]).encode('utf-8')
    hash_object = sha1(page_source.encode('utf-8'))

    return hash_object.hexdigest()


def form_telegraph_page(page_source: str) -> Tuple[str, str]:
    items = []
    soup = BeautifulSoup(page_source, 'lxml')
    banner = soup.find('figure', {'class': 'article-top-related-image'})
    if banner is not None:
        banner_img = banner.find('img')
        banner_img['src'] = banner_img['src'].replace('_xs.', '_lg.')
        # banner_img_src = banner_img['src'].replace('_xs.', '_lg.')  # костыль, связанный с тем, что сайт
        # не может определить  разрешение экрана юзера и по дефолту отдаёт самые маленькие изображения
        items.append(banner_img)

    header = soup.find(id='article').find('header').find('h1')

    content = soup.find(id='article').find('div', {'class': 'docSubContent'}).find_all(AVAILABLE_TAGS)
    items.extend(content)

    html_content = prepare_items(items)
    prepared_telegraph_page = ''.join(html_content)

    return header.text, prepared_telegraph_page


async def export_article_to_telegraph(journal_issue: JournalIssue, link: str) -> Article:
    page_source = await get_page_source(f"{MAIN_URL}{link}")

    header, html_content = form_telegraph_page(page_source)
    current_article_hash = calc_article_hash(html_content)

    article = Article.get_or_none(Article.url == link)

    telegraph = Telegraph(TELEGRAPH_USER_TOKEN)
    if not article:
        try:
            telegraph_response = await telegraph.create_page(title=header, html_content=html_content)

            new_article = Article.create(title=telegraph_response['title'],
                                         url=link,
                                         telegraph_path=telegraph_response['path'],
                                         journal_issue=journal_issue,
                                         content_hash=current_article_hash)
            new_article.save()
            logger.info(f"New article. Article id: {new_article.id}, Telegraph URL: {new_article.telegraph_path}")
            return new_article

        except NotAllowedTag as e:
            logger.exception(e)
            with open('error_content.html', 'w') as file:
                file.write(html_content)

        except TelegraphException as e:
            logger.exception(f"Page was not imported to Telegraph: {article.text}")

        except IntegrityError as e:
            logger.exception(e)

    elif article.content_hash != current_article_hash:
        try:
            telegraph_raw_response = await telegraph.edit_page(path=article.telegraph_path, title=header,
                                                               html_content=html_content)
            article.content_hash = current_article_hash
            article.save()
            logger.info(f"Edited article. Article id: {article.id}, Telegraph URL: {article.telegraph_path}")
            logger.debug(telegraph_raw_response)
        except TelegraphException as e:
            logger.exception(f"Article was not edited, article_id = {article.id}, {e}")

    return article


def month_to_number(month_name: str) -> int:
    month_name = month_name.lower()
    return {
            'январь': 1,
            'февраль': 2,
            'март': 3,
            'апрель': 4,
            'май': 5,
            'июнь': 6,
            'июль': 7,
            'август': 8,
            'сентябрь': 9,
            'октябрь': 10,
            'ноябрь': 11,
            'декабрь': 12
    }[month_name]
