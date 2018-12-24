from asyncio import AbstractEventLoop
from datetime import datetime
from threading import Thread

from common_functions import parse_journal_issue, get_journal_list


class JWWatcher(Thread):
    def __init__(self, loop: AbstractEventLoop):
        super().__init__()
        self.loop = loop

    async def main(self):
        current_year = datetime.now().year

        journal_list = await get_journal_list()

        for year in range(current_year, 2000, -1):
            for journal in journal_list:
                await parse_journal_issue(journal=journal, year=year)


    def run(self):
        self.loop.create_task(self.main())
