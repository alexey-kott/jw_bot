import json
import logging
import re
from hashlib import sha1

import sqlite3
from typing import Tuple, List

from bs4 import BeautifulSoup, Tag

from aiohttp import ClientSession
from peewee import ModelSelect
from telegraph import Telegraph
from telegraph.utils import html_to_nodes

from config import TELEGRAPH_USER_TOKEN
from models import Article, JournalIssue, Journal

MAIN_URL = "https://www.jw.org"

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


async def get_page_source(url, params=None):
    async with ClientSession() as session:
        async with session.get(url, params=params) as response:
            return await response.text()


def try_replace_link(link: str) -> str:
    # print(link)
    # print('------------------------------')
    article = Article.get_or_none(Article.url == link)

    if article:
        print(article.telegraph_url)
        return article.telegraph_url
    else:
        return link

    # print('==============================')
    # print('\n\n')
    # print(type(select))


def prepare_items(items: List[Tag]) -> str:
    AVAILABLE_TAGS = ['h1', 'h2', 'h3', 'h4', 'hr', 'img', 'p', 'ul', 'ol']

    for item in items:
        # print(item.name)

        if item.name == 'a':
            # print(item['href'])
            item['href'] = try_replace_link(item['href'])

        for match in item.find_all('span'):
            match.unwrap()
        for tag in item.find_all(['h1', 'h2', 'span']):
            if tag.name == 'h1':
                tag.name = 'h3'
            if tag.name == 'h2':
                tag.name = 'h4'
        #
        #     if tag.span is not None:
        #         tag.span.decompose()

    return ''.join([str(item) for item in items])


def calc_article_hash(items: List[Tag]) -> str:
    s = ''.join([str(i) for i in items]).encode('utf-8')
    hash_object = sha1(s)

    return hash_object.hexdigest()


async def export_article_to_telegraph(journal_issue: JournalIssue, link: str, logger: logging.Logger) -> Article:
    items = []
    page_source = await get_page_source(f"{MAIN_URL}{link}")

    soup = BeautifulSoup(page_source, 'lxml')
    banner = soup.find('div', {'class': 'lsrBannerImage'})
    if banner is not None:
        banner_img = banner.find('img')
        banner_img['src'] = banner_img['src'].replace('_xs.', '_lg.')
        banner_img_src = banner_img['src'].replace('_xs.', '_lg.')  # костыль, связанный с тем, что сайт
        # не может определить  разрешение экрана юзера и по дефолту отдаёт самые маленькие изображения
        items.append(banner_img)

    header = soup.find('div', {'id': 'article'}).find('header').find('h1')

    # ['a', 'aside', 'b', 'blockquote', 'br', 'code', 'em', 'figcaption', 'figure', 'h3', 'h4', 'hr',
    # 'i', 'iframe', 'img', 'li', 'ol', 'p', 'pre', 's', 'strong', 'u', 'ul', 'video']
    AVAILABLE_TAGS = ['h1', 'h3', 'h4', 'hr', 'img', 'p', 'ul', 'ol', 'a']
    content = soup.find('div', {'id': 'article'}).find('div', {'class': 'docSubContent'}).find_all(AVAILABLE_TAGS)

    telegraph = Telegraph(TELEGRAPH_USER_TOKEN)

    items.extend(content)

    current_article_hash = calc_article_hash(items)

    article = Article.get_or_none(Article.url == link)

    html_content = prepare_items(items)
    prepared_telegraph_page = ''.join(html_content)

    if not article:
        telegraph_response = telegraph.create_page(title=header.text,
                                                   html_content=prepared_telegraph_page)
        new_article = Article.create(title=telegraph_response['title'],
                                     url=link,
                                     telegraph_url=telegraph_response['url'],
                                     journal_issue=journal_issue,
                                     content_hash=current_article_hash)
        new_article.save()
        logger.info(f"New article. Article id: {new_article.id}, Telegraph URL: {new_article.telegraph_url}")

        return telegraph_response
    elif article.content_hash != current_article_hash:
        telegraph_raw_response = telegraph.edit_page(path=article.telegraph_url, title=header.text,
                                                     html_content=prepared_telegraph_page)
        article.content_hash = current_article_hash
        article.save()
        logger.info(f"Edited article. Article id: {article.id}, Telegraph URL: {article.telegraph_url}")
        print(telegraph_raw_response)

        return telegraph_raw_response







