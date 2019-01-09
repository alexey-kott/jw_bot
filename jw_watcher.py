import asyncio
import locale
import logging
import re
from logging import Logger
from asyncio import AbstractEventLoop
from datetime import datetime
from threading import Thread
from typing import Tuple

from bs4 import BeautifulSoup
from peewee import ModelSelect

from common_functions import get_page_source, export_article_to_telegraph
from models import Journal, JournalIssue

logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='./logs/log')

locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')

MAIN_URL = "https://www.jw.org"


class JWWatcher(Thread):
    def __init__(self, watcher_loop: AbstractEventLoop, watcher_logger: Logger):
        super().__init__()
        self.loop = watcher_loop
        self.logger = watcher_logger

    async def main(self):
        current_year = datetime.now().year

        journal_list = await self.get_journal_list()

        for year in range(current_year, 2000, -1):
            print(year)
            for journal in journal_list:
                self.logger.info(f'Year: {year}; journal: {journal.title}')
                try:
                    await self.parse_journal_issue(journal=journal, year=year)
                except Exception as e:
                    self.logger.exception(e)

    async def parse_journal_issue(self, journal: Journal, year: int):
        params = {
            'contentLanguageFilter': 'ru',
            'pubFilter': journal.symbol,
            'yearFilter': year
        }
        page_source = await get_page_source(f"{MAIN_URL}/ru/публикации/журналы/", params=params)
        soup = BeautifulSoup(page_source, 'lxml')

        for item in soup.find_all(class_='publicationDesc'):
            await self.check_journal_issue_availability(journal, item.h3.a['href'])

    async def get_journal_list(self) -> ModelSelect:
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

    async def check_journal_issue_availability(self, journal: Journal, link: str):
        issue_link = f"{MAIN_URL}{link}"
        self.logger.info(f"Check journal issue: {issue_link}")
        page_source = await get_page_source(issue_link)
        soup = BeautifulSoup(page_source, 'lxml')

        main_frame = soup.find('div', {'id': 'article'})

        context_title = main_frame.find('h1')
        number, year, title = self.parse_context_title(context_title)

        section1 = main_frame.find('div',
                                   {'id': 'section1'})  # div with id=section1 is annotation with header

        try:
            header = section1.find('h2', {'id': 'p2'})
            synopsis = section1.find('p', {'id': 'p3'})
            annotation = f"{header.text}\n\n{synopsis.text}"
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
                telegraph_response = await export_article_to_telegraph(journal_issue, article_link['href'], self.logger)
                print(telegraph_response)


            except Exception as e:
                print(e)
                self.logger.exception(f"Article wasn't parsed: {MAIN_URL}{article_link['href']}")

    def parse_context_title(self, title: str) -> Tuple[str, str, str]:
        [s.extract() for s in title('span')]
        match = re.search(r"(?P<number>(?<=№\s)\d+)\s(?P<year>\d{4})\s+\|\s(?P<title>.*)", title.text)

        if match is None:
            match = re.search(r"(?P<month>\S*)\s(?P<year>\d{4})\s+\|\s(?P<title>.*)", title.text)
            month_name = match.group('month')
            dt = datetime.strptime(month_name, '%B')
            number = dt.month
        else:
            number = match.group('number')

        year = match.group('year')
        title = match.group('title')

        return number, year, title

    def run(self):
        self.loop.create_task(self.main())


if __name__ == "__main__":
    logger = logging.getLogger('jw_watcher')
    logger.setLevel(logging.INFO)

    loop = asyncio.get_event_loop()
    watcher = JWWatcher(watcher_loop=loop, watcher_logger=logger)
    loop.run_until_complete(watcher.main())
    loop.close()
