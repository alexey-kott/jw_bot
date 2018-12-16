from asyncio import AbstractEventLoop
from datetime import datetime
from threading import Thread

from common_functions import parse_journal_issue


class JWWatcher(Thread):
    def __init__(self, loop: AbstractEventLoop):
        super().__init__()
        self.loop = loop

    async def main(self):
        current_year = datetime.now().year
        journal_list = {'g': 'Пробудитесь!',
                        'wp': 'Сторожевая башня'}
        for year in range(current_year, 2000, -1):
            for journal_symbol, journal_name in journal_list.items():
                articles = await parse_journal_issue(journal_name=journal_symbol, year=year)
                # for a in articles:
                #     print(a)


    def run(self):
        self.loop.create_task(self.main())
