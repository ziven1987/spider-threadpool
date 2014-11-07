# coding:utf-8
from Queue import Queue
import threading
from BeautifulSoup import BeautifulSoup
import urllib2, re, sqlite3, os
from optparse import OptionParser
import logging
logger = logging.getLogger()


# 读取url线程类
class readUrlThread(threading.Thread):
    def __init__(self, urlqueue, htmlqueue, readurls, key, deep):
        threading.Thread.__init__(self)
        self.urlqueue = urlqueue
        self.htmlqueue = htmlqueue
        self.key = key
        self.readurls = readurls
        self.deep = deep
        self.urls = readurls
        
    # 取得url
    def geturl(self, urltuple):
        deep, url = urltuple
        try:
            html = urllib2.urlopen(url).read()
        except UnicodeError, e: # 如果出现Unicode异常 转换后再次放入队列
            self.urlqueue.put((deep, url.encode('raw_unicode_escape')))
            return None
        except Exception,e:
            print u'抓取错误：', e
            return None
        if not deep >= self.deep: # 判断是否到达层数
            soup = BeautifulSoup(html, fromEncoding='utf-8')
            urlall = soup.findAll('a', onclick=None, href=re.compile('^http:|^/'))
            if url.endswith('/'):
                url = url[:-1]
            for i in urlall:
                if i['href'].startswith('/'):
                    i['href'] = url + i['href']
                if i['href'] not in self.urls: #如果没在已经读取URL列表中时，加入到列表和队列
                    self.urls.append(i['href'])
                    self.urlqueue.put((deep+1, i['href']))
        return html
    
    # 过滤字符串
    def htmlfilter(self, url, html):
        if self.key: # 匹配关键字、加入队列
            re_string = self.key
            soup = BeautifulSoup(html, fromEncoding='utf-8')
            if soup.findAll(content = re.compile(re_string)):
                self.htmlqueue.put((url, self.key, html))
        else:
            self.htmlqueue.put((url, '', html))
    
    def run(self):
        while True:
            urltuple = self.urlqueue.get()
            deep, url = urltuple
            print u'抓取 URL:', self.urlqueue.qsize(), deep, url
            logger.info('CurrentDepth : %d, Totally visited %d Links, Current visited url:%s.\n' %(deep,len(self.readurls), url))
            html = self.geturl(urltuple)
            if html:
                self.htmlfilter(url, html)
            self.urlqueue.task_done() # 向url队列发送信号

class writeDatabaseThread(threading.Thread):
    def __init__(self, htmlqueue, sqlitefile):
        threading.Thread.__init__(self)
        self.htmlqueue = htmlqueue
        self.sqlitefile = sqlitefile
    
    def run(self):
        sqliteCon = sqlite3.connect(self.sqlitefile)
        sqliteCon.text_factory = str
        cur=sqliteCon.cursor()
        cur.execute('''
        create table if not exists data (
          id INTEGER PRIMARY KEY  AUTOINCREMENT  ,
          url text,
          key text,
          html text
        )
        ''')
        sqliteCon.commit()
        while True:
            url, key, html = self.htmlqueue.get()
            self.htmlqueue.task_done()
            try:
                cur.execute("insert into data (url,key,html) values (?,?,?)",(url, key, html))
                sqliteCon.commit()
                print u'写入：', url, self.htmlqueue.qsize()
            except Exception,e:
                print u'数据库错误：', e
                self.htmlqueue.put((url, key, html))
        sqliteCon.close()


def work(url, deep, threads, dbfile, key):
    urlqueue = Queue()
    htmlqueue = Queue()
    readurls = []
    for i in range(threads):
        r = readUrlThread(urlqueue, htmlqueue, readurls, key, deep)
        r.setDaemon(True)
        r.start()
    urlqueue.put((1,url))
    #如果有数据库操作执行
    if dbfile:
        if os.path.isfile(dbfile):
            os.remove(dbfile)
        w = writeDatabaseThread(htmlqueue, dbfile)
        w.setDaemon(True)
        w.start()
    
    urlqueue.join()
    htmlqueue.join()
    print u'运行完成, 链接数量:%d' % len(readurls)

#日志配置函数 
def logConfig(logFile,logLevel): 
    #移除现有的同名日志文件 
    if os.path.isfile(logFile): 
        os.remove(logFile) 
    #数字越大记录越详细 
    LEVELS = { 
         1:logging.CRITICAL, 
         2:logging.ERROR, 
         3:logging.WARNING, 
         4:logging.INFO, 
         5:logging.DEBUG 
     } 
    level = LEVELS[logLevel] 
    logging.basicConfig(filename = logFile,level = level) 


if __name__ == '__main__':
    #命令行参数解析 
    usage = u''
    parser = OptionParser(usage) 
    
    parser.add_option("-u", dest="url", type="string",
                      help=u"指定爬虫开始地址")
    parser.add_option("-d", dest="deep", type="int",
                      help=u"指定爬虫深度")
    parser.add_option("-f", dest="logfile", default="spider.log", type="string",
                      help=u"日志记录文件，默认spider.log")
    parser.add_option("-l", dest="loglevel", default="5", type="int",
                      help=u"日志记录文件记录详细程度，数字越大记录越详细，可选参数")
    parser.add_option("--thread", dest="thread", default="10", type="int",
                      help=u"指定线程池大小，多线程爬取页面，可选参数，默认10")
    parser.add_option("--dbfile", dest="dbfile", type="string",
                      help=u"存放结果数据到指定的数据库(sqlite)文件中")
    parser.add_option("--key", metavar="key", default="", type="string",
                      help=u"页面内的关键词，获取满足该关键词的网页，可选参数，默认为所有页面")
    parser.add_option("--testself", action="store_false", dest="testself", default=False,
                      help=u"程序自测，可选参数")
    (options, args) = parser.parse_args()
    if options.testself:
        import doctest
        doctest.testmod()
    else:
        logConfig(options.logfile, options.loglevel)
        work(options.url, options.deep, options.thread, options.dbfile, options.key)