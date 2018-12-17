from asyncio import AbstractEventLoop, sleep
from datetime import datetime
from threading import Thread

from common_functions import parse_journal_issue, get_journal_list


class JWWatcher(Thread):
    def __init__(self, loop: AbstractEventLoop):
        super().__init__()
        self.loop = loop

    async def main(self):
        current_year = datetime.now().year
        # journal_list = {'g': 'Пробудитесь!',
        #                 'wp': 'Сторожевая башня'}

        journal_list = await get_journal_list()

        for year in range(current_year, 2000, -1):
            for journal in journal_list:
                articles = await parse_journal_issue(journal=journal, year=year)
                # for a in articles:
                #     print(a)


    def run(self):
        self.loop.create_task(self.main())
