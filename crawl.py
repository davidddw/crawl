#!/usr/bin/env python3
# -*- coding:utf-8 -*-

from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
import time
import os.path
import logging
import asyncio
import aiohttp
import requests
import urllib3
import tqdm

URL = 'http://www.9dxs.com/3/3024/'
DIR_PATH = 'download'
CHAPTER_ENCODING = 'utf8'
CONTENT_ENCODING = 'gbk'

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.3"
                   "6 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,image/we"
               "bp,image/apng,*/*;q=0.8")
}

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.INFO)
handler = logging.FileHandler("log.txt", encoding='utf8')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s'
                              ' - %(message)s')
handler.setFormatter(formatter)
console = logging.StreamHandler()
console.setLevel(logging.ERROR)

logger.addHandler(handler)
logger.addHandler(console)

sema = asyncio.BoundedSemaphore(5)


class AsnycSpider():
    def __init__(self, url, downloaddir=DIR_PATH):
        parse_string = urlparse(url)
        if parse_string.scheme == 'https':
            self.SSL = True
        else:
            self.SSL = False
        self.url = url + '/' if not url.endswith('/') else url
        self.chapter_list = list()
        self.downloaddir = downloaddir

    def download(self, first, last):
        self.__get_chapters(first, last)
        self.eventloop()

    def get_absolute_path(self, path):
        pattern = re.compile(r"^.*/")
        return re.sub(pattern, "", path)

    def __get_first_html(self, url_str):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url_str, headers=HEADERS, verify=self.SSL)
        return response.text.encode(response.encoding).decode(CHAPTER_ENCODING)

    def __get_chapters(self, first=None, last=None):
        begin = time.time()
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(begin))
        print('First Page Job at {}.'.format(time_str))
        html_string = self.__get_first_html(self.url + 'index.html')
        chapters = self.parse_chapter(html_string)
        first = 0 if first is None else first
        last = len(chapters) if last is None else last
        self.chapter_list = chapters[first:last]
        end = time.time()
        print('First Page take {:.4} seconds.'.format(end - begin))

    async def get_content_from_url(self, url):
        respdata = ''
        try:
            async with aiohttp.ClientSession() as session:
                async with sema, session.get(url, headers=HEADERS,
                                             timeout=300) as r:
                    if r.status == 200:
                        respdata = await r.text(encoding=CONTENT_ENCODING,
                                                errors='ignore')
                    else:
                        logging.error(
                            '{} is blocked, status code: '.format(url),
                            r.status)
        except Exception as e:
            logging.exception('Error for {}'.format(e), exc_info=True)
        return respdata

    async def handle_tasks(self, task_id, work_queue):
        while not work_queue.empty():
            current_url = await work_queue.get()
            try:
                await self.process_request(current_url)
            except Exception as e:
                logging.exception('Error for {}'.format(e), exc_info=True)

    def eventloop(self):
        start = time.time()
        timestr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start))
        print('Start Download Job at {}.'.format(timestr))
        q = asyncio.Queue()
        [q.put_nowait(url) for url in self.chapter_list]
        loop = asyncio.get_event_loop()
        tasks = [
            self.handle_tasks(
                task_id,
                q,
            ) for task_id in range(len(self.chapter_list))
        ]
        loop.run_until_complete(self.wait_with_progress(tasks))
        end = time.time()
        print('Total take {:.4} seconds.'.format(end - start))
        loop.close()

    async def wait_with_progress(self, tasks):
        return [
            await f for f in tqdm.tqdm(
                asyncio.as_completed(tasks), ascii=True, total=len(tasks))
        ]

    async def process_request(self, url):
        html = await self.get_content_from_url(url['href'])
        formated_html = self.parse_content(url['text'], html)
        target_file = os.path.join(self.downloaddir,
                                   self.__get_filename(url['href']) + '.txt')
        filename = os.path.abspath(target_file)
        self.__save_to_file(self.custom_strip(formated_html), filename,
                            url['text'])
        return 'Completed'

    def __get_filename(self, m):
        pattern = re.compile(r'http.*/(\d*).html')
        items = re.findall(pattern, m)
        if (items):
            return items[0]
        else:
            return ''

    def custom_strip(self, x):
        remove_tag1 = re.compile(r'<br>')
        remove_tag2 = re.compile(r'&nbsp;')
        x = re.sub(remove_tag1, '\n', x)
        x = re.sub(remove_tag2, ' ', x)
        return x.strip()

    def __save_to_file(self, content, fileName, title):
        path = os.path.dirname(fileName)
        if not os.path.exists(path):
            os.makedirs(path)
        with open(fileName, 'w', encoding='utf-8') as f:
            logger.info('Write {} ==> {} successful.'.format(title, fileName))
            f.write(content)

    def merge_file(self, filename):
        target_list = os.path.abspath(os.path.join(self.downloaddir))
        filelist = os.listdir(target_list)
        filelist.sort()
        with open(filename, 'w', encoding='utf-8') as outfile:
            for fname in tqdm.tqdm(filelist, ascii=True):
                real_file = os.path.abspath(
                    os.path.join(self.downloaddir, fname))
                with open(real_file, 'r', encoding='utf-8') as infile:
                    for line in infile:
                        outfile.write(line)
                    outfile.write('\n\n')
                logger.info('Write {} successful.'.format(real_file))

    def parse_content(self, title, html):
        return ''

    def parse_chapter(self, html):
        return ''


class NovelSpider(AsnycSpider):
    def __init__(self, url, downloaddir=DIR_PATH):
        super().__init__(url, downloaddir=downloaddir)

    def parse_content(self, title, html):
        formated_html = ''
        try:
            soup = BeautifulSoup(html, 'lxml')
            content = soup.find("div", attrs={"class": "content"})
            content = content.get_text('\n\n    ', strip=True)
            formated_html = '{}\n\n{}'.format(title, content)
        except Exception as e:
            raise e
        return formated_html

    def parse_chapter(self, html):
        chapter_list = list()
        try:
            soup = BeautifulSoup(html, 'lxml')
            chapter_div = soup.find(id='novel56235')
            hrefs = chapter_div.find_all('dd')
            chapter_list = [{
                'href':
                self.url + self.get_absolute_path(i.find('a').get('href')),
                'text':
                i.find('a').text
            } for i in hrefs if i.find('a')]
        except Exception as e:
            raise e
        return chapter_list

    def custom_strip(self, x):
        # remove_tag1 = re.compile(r'(<br />|<br>)+')
        # remove_tag2 = re.compile(r'(&nbsp;){4}')
        # x = re.sub(remove_tag1, '\n\n', x)
        # x = re.sub(remove_tag2, '\n\n', x)
        return x.strip()


if __name__ == "__main__":
    spider = NovelSpider('https://www.77nt.com/56235/', 'download8')
    # spider.download(2500, 2520)
    spider.merge_file("target.txt")
