import asyncio

from aiohttp import ClientSession
from bs4 import BeautifulSoup


MAIN_URL = "https://www.jw.org/ru"


async def parse_journals_per_year(session: ClientSession, year: str):
    params = {
        'contentLanguageFilter': 'ru',
        'pubFilter': '',
        'yearFilter': year
    }
    async with session.get(f"{MAIN_URL}/публикации/журналы/", params=params) as response:
        soup = BeautifulSoup(await response.text(), 'lxml')

        journal_links = soup.find_all("div", class_="publicationDesc")
        for i in journal_links:
            print(i)



async def parse_journals(session: ClientSession):
    async with session.get(f"{MAIN_URL}/публикации/журналы/") as response:
        journals_page = await response.text()

        soup = BeautifulSoup(journals_page, 'lxml')
        pub_filters = soup.find("select", {"id": "yearFilter"})
        for option in pub_filters.find_all("option", {'value': lambda x: x != ''}):
            await parse_journals_per_year(session, option['value'])


async def main():
    async with ClientSession() as session:
        await parse_journals(session)


if __name__ == "__main__":
    asyncio.run(main())