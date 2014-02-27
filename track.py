# -*- coding: utf-8 -*-

from gevent import monkey
monkey.patch_all()

import gevent
from gevent.queue import JoinableQueue

import requests
import codecs
import re
from pyquery import PyQuery as PQ
from lxml import etree
import gspread
from secret import GPASS
from datetime import datetime
import time
import random


DISEL_TITLE = re.compile("DIESEL\s+(?P<STYLE>[A-Z\-\s]+)\s+(?P<WASH>\d+[A-Z\d]+)")
TABLE_SLICE = re.compile("<table[^<]+</table>", re.MULTILINE)

QUEUE = JoinableQueue()
ITEMS = []

def worker():
    while True:
        item = QUEUE.get()

        try:
            proc_item(item)
        finally:
            QUEUE.task_done()


def get_ruten(url, referer=None):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1700.107 Safari/537.36',
    }

    if referer:
        headers['Referer'] = referer

    cookies = {
        '_ts_id':  '999999999999999999',
    }

    proxies = {
        "http": "http://proxy.seed.net.tw:8080",
        "https": "http://proxy.seed.net.tw:8080",
    }
    proxies = None

    return requests.get(url, 
        headers=headers, cookies=cookies, proxies=proxies).text.encode('latin1', 'ignore').decode('big5', 'ignore')


def proc_item_list(q):
    keys = ['ruten', 'pchome']

    for k in keys:
        items = q('a[%s]' % k).filter(lambda i: len(PQ(this).children('img')) == 0)
        if len(items) > 0:
            print 'found via key "%s"' % k
            break

    print 'total links found: %d' % len(items)

    if len(items) == 0:
        return -1

    c = 0
    for i in items:
        m = re.search(DISEL_TITLE, PQ(i).text())
        if not m:
            continue

        c += 1

        dt = {
            'style': m.group('STYLE'),
            'wash': m.group('WASH'),
            'url': PQ(i).attr('href')
        }

        # QUEUE.put(dt)
        proc_item(dt)
        # print dt

    return c


def proc_item(item):
    print 'processing: %s' % item

    q = PQ(url=item['url'], opener=lambda url:get_ruten(url))
    comment_url = q('#embedded_goods_comments').attr('src')

    if not comment_url:
        print 'no comment url found !!!'
        return

    q = PQ(get_ruten(comment_url, item['url']))
    for tr in q('table tbody tr'):
        td_list = PQ(tr).children('td')

        if len(td_list) != 11:
            continue
        if PQ(td_list[0]).text() == '標示腰圍':
            continue
        if PQ(td_list[3]).text() == '-':
            continue

        sitem = {}
        sitem['style'] = item['style']
        sitem['wash'] = item['wash']
        sitem['url'] = item['url']
        sitem['wsize'] = PQ(td_list[0]).text().replace('"', 'W')
        sitem['lsize'] = PQ(td_list[1]).text().replace('"', 'L')
        sitem['available'] = PQ(td_list[2]).text()
        sitem['backwidth'] = float(PQ(td_list[3]).text())
        sitem['frontwidth'] = float(PQ(td_list[4]).text())
        sitem['bottomheight'] = float(PQ(td_list[5]).text())
        sitem['bottomwidth'] = float(PQ(td_list[6]).text())
        sitem['biglegwidth'] = float(PQ(td_list[7]).text())
        sitem['footwidth'] = float(PQ(td_list[8]).text())
        sitem['outerlength'] = PQ(td_list[9]).text()
        sitem['innerlegth'] = PQ(td_list[10]).text()

        # print sitem
        ITEMS.append(sitem)

    # time.sleep(random.randint(100, 500) / 1000.0)
    time.sleep(0.5)


TITLES = [
        u'版型',
        u'刷色',
        u'腰圍',
        u'長度',
        u'庫存',
        u'後腰寬',
        u'前後腰拉齊',
        u'褲檔長',
        u'臀寬',
        u'大腿寬',
        u'褲腳寬',
        u'外側褲長',
        u'內側褲長',
        u'網址'
]


def write_items_csv():
    if len(ITEMS) == 0:
        return

    nowstr = datetime.now().strftime('%Y%m%d-%H%M%S.csv')
    f = open(nowstr, 'w')

    f.write(','.join(TITLES) + '\n')

    for i in ITEMS:
        row = [
            i['style'],
            i['wash'],
            i['wsize'],
            i['lsize'],
            i['available'],
            str(i['backwidth']),
            str(i['frontwidth']),
            str(i['bottomheight']),
            str(i['bottomwidth']),
            str(i['biglegwidth']),
            str(i['footwidth']),
            i['outerlength'],
            i['innerlegth'],
            i['url'],
        ]
        f.write(','.join(row) + '\n')       

    f.close()


def write_items():
    nowstr = datetime.now().strftime('%Y/%m/%d %H:%M:%S')

    print 'writing to google spreadsheet'
    gapp = gspread.login('toki.kanno@gmail.com', GPASS)
    doc = gapp.open('Ruten Diesel Tracker')
    sht = doc.add_worksheet(nowstr, 1, len(TITLES))
    title_cells = sht.range('A1:%s1' %  chr(ord('A') + len(TITLES) - 1 ))
    for i in range(len(TITLES)):
        title_cells[i].value = TITLES[i]
    sht.update_cells(title_cells)

    for i in ITEMS:
        print 'writing: %s' % i

        row = [
            i['style'],
            i['wash'],
            i['wsize'],
            i['lsize'],
            i['available'],
            i['backwidth'],
            i['frontwidth'],
            i['bottomheight'],
            i['bottomwidth'],
            i['biglegwidth'],
            i['footwidth'],
            i['outerlength'],
            i['innerlegth'],
            i['url'],
        ]

        sht.append_row(row)


def main():
    i = 1
    c = 0
    while True:
        q =  PQ(url='http://class.ruten.com.tw/user/index00.php?s=nevereverfor&p=%d' % i, 
            opener=lambda url: get_ruten(url))

        pc = proc_item_list(q)
        if pc < 0:
            print 'break @ i = %d, total item: %d' % (i, c)
            break

        c += pc
        i += 1

    WORKER_COUNT = 2

    for i in range(WORKER_COUNT):
         gevent.spawn(worker)

    QUEUE.join()  # block until all tasks are done

    print 'Total %d items collected' % len(ITEMS)

    if len(ITEMS) == 0:
        return

    ITEMS.sort(key = lambda x: (x['style'], x['wash'], x['lsize'], x['wsize']))

    # for i in ITEMS:
    #     print '%s %s %s %s %s' % (i['style'], i['wash'], i['wsize'], i['lsize'], i['available'])
    write_items_csv()
    # write_items()


if __name__ == '__main__':
    import sys
    if sys.getdefaultencoding() != 'utf-8':
        reload(sys)
        sys.setdefaultencoding('utf-8')

    main()
