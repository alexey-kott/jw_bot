import asyncio
import locale
import logging
import re
from logging import Logger
from asyncio import AbstractEventLoop
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Tuple

from bs4 import BeautifulSoup, Tag
from peewee import ModelSelect
from telegraph import TelegraphException

from common_functions import get_page_source, export_article_to_telegraph, LOG_PATH, month_to_number, download_file
from models import Journal, JournalIssue, init_db

logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename=LOG_PATH)

locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')

MAIN_URL = "https://www.jw.org"


class JWWatcher(Thread):
    def __init__(self, watcher_loop: AbstractEventLoop, watcher_logger: Logger):
        init_db()  # create db tables
        super().__init__()
        self.loop = watcher_loop
        self.logger = watcher_logger

    async def main(self):
        current_year = datetime.now().year

        journals_list = await self.get_journals_list()
        logger.debug(f"")

        for year in range(current_year, 2000, -1):
            for journal in journals_list:
                self.logger.info(f'Year: {year}; journal: {journal.title}')
                try:
                    await self.parse_journal_issues(journal=journal, year=year)
                except Exception as e:
                    self.logger.exception(e)

    async def parse_journal(self):
        pass

    async def parse_journal_issues(self, journal: Journal, year: int):
        params = {
            'contentLanguageFilter': 'ru',
            'pubFilter': journal.symbol,
            'yearFilter': year
        }
        page_source = await get_page_source(f"{MAIN_URL}/ru/публикации/журналы/", params=params)
        soup = BeautifulSoup(page_source, 'lxml')

        for item in soup.find_all(class_='publicationDesc'):
            try:
                await self.check_journal_issue_availability(journal, item.h3.a['href'])
            except Exception as e:
                self.logger.exception(e)

    @staticmethod
    async def get_journals_list() -> ModelSelect:
        """Получаем список журналов с их обозначениями, проверяем не появилось ли чего-то нового (скорее
        всего нет, но функция в первую очередь необходима при первичном запуске приложения)
        """
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
                    logger.debug(f"New journal created: {item.text}")
                else:
                    logger.debug(f"Parsed journal: {item.text}")

        return Journal.select()

    async def check_journal_issue_availability(self, journal: Journal, link: str):
        issue_link = f"{MAIN_URL}{link}"
        self.logger.info(f"Checking journal issue: {issue_link}")
        page_source = await get_page_source(issue_link)
        soup = BeautifulSoup(page_source, 'lxml')

        main_frame = soup.find(id='article')

        context_title = main_frame.find('h1')
        number, year, title = self.parse_journal_issue_title(context_title)
        self.logger.info(f"Parse journal issue #{number}, {year}, {title}")

        section1 = main_frame.find('div',
                                   {'id': 'section1'})  # div with id=section1 is annotation with header
        # sections = main_frame.find_all(class_="section")

        try:
            header = main_frame.find('h1').text.strip()
            if section1:
                synopsis = section1.find('p', {'id': 'p2'})
            else:  # для версии СТОРОЖЕВАЯ БАШНЯ (ВЫПУСК ДЛЯ ИЗУЧЕНИЯ)
                synopsis = main_frame.find("p", {"class": "adDesc"})

            annotation = f"{header}\n\n{synopsis.text}"
        except AttributeError as e:
            annotation = ''
            self.logger.exception(e)

        journal_issue = JournalIssue.get_or_none(JournalIssue.journal == journal, JournalIssue.year == year,
                                                 JournalIssue.number == number)
        if not journal_issue:
            journal_issue = JournalIssue.create(journal=journal, year=year, number=number,
                                                title=title, annotation=annotation, link=link)

        article_items = main_frame.find_all('div', {'class': 'PublicationArticle'})

        for item in article_items:
            article_link = item.find('a')
            try:
                article = await export_article_to_telegraph(journal_issue, article_link['href'])

                await self.download_article_voice_version(article_link['href'])
                logger.debug(f"Article with ID = {article.id} processed")

            except Exception as e:
                self.logger.exception(f"Article wasn't parsed: {MAIN_URL}{article_link['href']}")

    @staticmethod
    def parse_journal_issue_title(title: Tag) -> Tuple[str, str, str]:
        # [s.extract() for s in title('span')]
        match = re.search(r"(?P<number>(?<=№\s)\d+)\s(?P<year>\d{4})\s+\|\s(?P<title>.*)", title.text)

        if match is None:
            # &nbsp; symbol between month and year recognize as \S
            match = re.search(r"(?P<month>\S*).(?P<year>\d{4})", title.text.strip())
            month_name = match.group('month')
            # dt = datetime.strptime(month_name, '%B')  # требует название месяца в родительном падеже,
            # month_number = dt.month  # в именительном выдаёт ошибку
            month_number = month_to_number(month_name)
            title = title.find('span').text
        else:
            month_number = match.group('number')
            title = match.group('title')

        year = match.group('year')

        return month_number, year, title

    @staticmethod
    async def download_article_voice_version(article_path: str) -> bool:
        page_source = await get_page_source(f"{MAIN_URL}{article_path}")
        soup = BeautifulSoup(page_source, "html5lib")
        audio_container = soup.find("audio", {"class": "vjs-tech"})
        if not audio_container:
            return False

        file_name = article_path.strip("/").split("/")
        await download_file(audio_container['src'], file_name=file_name[-1])

    def run(self):
        self.loop.create_task(self.main())


if __name__ == "__main__":
    logger = logging.getLogger('jw_watcher')
    logger.setLevel(logging.INFO)

    logger_stream_handler = logging.StreamHandler()
    logger.addHandler(logger_stream_handler)

    loop = asyncio.get_event_loop()
    watcher = JWWatcher(watcher_loop=loop, watcher_logger=logger)
    loop.run_until_complete(watcher.main())
    loop.close()
