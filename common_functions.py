import json
import re
from hashlib import sha1

import sqlite3
from typing import Tuple, List

from bs4 import BeautifulSoup, Tag

from aiohttp import ClientSession
from telegraph import Telegraph
from telegraph.utils import html_to_nodes

from config import TELEGRAPH_USER_TOKEN
from models import Article, JournalIssue, Journal

MAIN_URL = "https://www.jw.org"


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


def add_default_journals():
    pass


def set_init_db_values():
    init_routing()

    add_default_journals()


async def get_page_source(url, params=None):
    async with ClientSession() as session:
        async with session.get(url, params=params) as response:
            return await response.text()


async def post_to_telegraph(href: str):
    page_source = await get_page_source(f"{MAIN_URL}{href}")
    soup = BeautifulSoup(page_source, 'lxml')

    telegraph = Telegraph()


def parse_context_title(title: str) -> Tuple[str, str, str]:
    [s.extract() for s in title('span')]
    match = re.search("(?P<number>(?<=№\s)\d+)\s(?P<year>\d{4})\s+\|\s(?P<title>.*)", title.text)

    return match.group('number'), match.group('year'), match.group('title')


def prepare_items(items: List[Tag]) -> str:
    for item in items:
        if item.name == 'h1':
            item.name = 'h3'
        if item.name == 'h2':
            item.name = 'h4'
        if item.span is not None:
            item.span.decompose()

    return ''.join([str(item) for item in items])


def calc_article_hash(items: List[Tag]) -> str:
    s = ''.join([str(i) for i in items]).encode('utf-8')
    hash_object = sha1(s)

    return hash_object.hexdigest()


async def export_article_to_telegraph(link: str) -> Article:
    page_source = await get_page_source(f"{MAIN_URL}{link}")

    soup = BeautifulSoup(page_source, 'lxml')
    banner = soup.find('div', {'class': 'lsrBannerImage'})
    banner_img = banner.find('img')
    banner_img['src'] = banner_img['src'].replace('_xs.', '_lg.')
    banner_img_src = banner_img['src'].replace('_xs.', '_lg.')  # костыль, связанный с тем, что сайт не может определить
    # разрешение экрана юзера и по дефолту отдаёт самые
    # маленькие изображения

    header = soup.find('div', {'id': 'article'}).find('header').find('h1')
    content = soup.find('div', {'id': 'article'}).find('div', {'class': 'docSubContent'}).find_all('p')

    return
    telegraph = Telegraph(TELEGRAPH_USER_TOKEN)

    items = []
    items.append(banner_img)
    items.append(header)
    items.extend(content)

    current_article_hash = calc_article_hash(items)

    # article = Article.create(url=link, title='dlkcmlsd', telegraph_url='dcsdkms', content_hash='sdcsdcs')
    # article.save()
    article = Article.get_or_none(Article.url == 'dcdscs')

    html_content = prepare_items(items)
    prepared_telegraph_page = ''.join(html_content)

    if not article:
        telegraph_response = telegraph.create_page(title=header.text, html_content=prepared_telegraph_page)
        # print('RESPONSE:', telegraph_response)
        new_article = Article.create(title=telegraph_response['title'],
                                     url=link,
                                     telegraph_url=telegraph_response['url'],
                                     journal_issue = None,
                                     content_hash = current_article_hash)
        # article._hash = current_article_hash
        # article.telegraph_url = telegraph_response['url']
        # article.title = telegraph_response['title']
        new_article.save()
        print('NEW ARTICLE: ', new_article)
    elif article.content_hash != current_article_hash:
        telegraph_raw_response = telegraph.edit_page(path=article.telegraph_url, title=header.text,
                                                     html_content=prepared_telegraph_page)
        article.content_hash = current_article_hash
        article.save()
        print('EDITED ARTICLE: ', article)
        print(telegraph_raw_response)
    # print(telegraph_response)


async def check_journal_issue_presence(href: str) -> int:
    page_source = await get_page_source(f"{MAIN_URL}{href}")
    soup = BeautifulSoup(page_source, 'lxml')

    main_frame = soup.find('div', {'id': 'article'})

    context_title = main_frame.find('h1')
    number, year, title = parse_context_title(context_title)

    section1 = main_frame.find('div', {'id': 'section1'})  # div with id=section1 is annotation with header
    header = section1.find('h2', {'id': 'p2'})
    synopsis = section1.find('p', {'id': 'p3'})
    annotation = f"**{header.text}**\n\n{synopsis.text}"

    journal_issue = JournalIssue.get_or_none(JournalIssue.journal == '')

    article_items = main_frame.find_all('div', {'class': 'PublicationArticle'})
    for item in article_items:
        item_link = item.find('a')
        article = await export_article_to_telegraph(item_link['href'])
        article.journal_issue = journal_issue
        article.save()

    return 1


async def get_journal_list() -> None:
    '''Получаем список журналов с их обозначениями, проверяем не появилось ли чего-то нового (скорее
    всего нет, но функция в первую очередь необходима при первичном запуске приложения)
    '''
    page_source = await get_page_source(f"{MAIN_URL}/ru/публикации/журналы/")
    soup = BeautifulSoup(page_source, 'lxml')

    journal_filter = soup.find('select', {'id': 'pubFilter'})
    for item in journal_filter.find_all('option'):
        if item['value']:
            if not Journal.get_or_none(Journal.symbol == item['value']):
                journal = Journal.create(symbol=item['value'],
                                         title=item.text,
                                         priority=int(item['data-priority']))
                journal.save()

    return Journal.select()


async def parse_journal_issue(journal: Journal, year: int) -> List[Tuple[str, str]]:
    params = {
        'contentLanguageFilter': 'ru',
        'pubFilter': journal.symbol,
        'yearFilter': year
    }
    page_source = await get_page_source(f"{MAIN_URL}/ru/публикации/журналы/", params=params)
    soup = BeautifulSoup(page_source, 'lxml')

    articles = []
    for item in soup.find_all(class_='publicationDesc'):
        await check_journal_issue_presence(item.h3.a['href'])
        # articles.append((item.h3.a.text, article_id))

    return articles
