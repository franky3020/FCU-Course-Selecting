import logging
from typing import *

from bs4 import BeautifulSoup
from requests import Session, Response
from requests.cookies import RequestsCookieJar

from .error import *
from .util import *


class Crawler:
    __logger = None
    __session = None
    __post_data: Dict[str, str] = None
    __logon: bool = False
    __host = ""
    __guid = ""
    __wishmap: Dict[int, int] = None  # cid -> position

    def __init__(self):
        ft = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        sh = logging.StreamHandler()
        sh.setFormatter(ft)
        self.__logger = logging.getLogger("fcu")
        self.__logger.addHandler(sh)
        self.__logger.level = logging.DEBUG
        self.__init()

    def __init(self):
        self.__session = Session()
        self.__session.cookies = RequestsCookieJar()
        self.__wishmap = {}
        self.__logon = False
        r = self.__session.get("https://course.fcu.edu.tw")
        self.__post_data = get_hidden_values(r.text)

    def reset(self):
        self.close()
        self.__init()

    def close(self):
        self.__session.close()

    def checklogin(self):
        if not self.__logon:
            raise RuntimeError("Please login first")

    def __postback(self, url: str = "", data: Dict = None) -> Response:
        url = f"http://{self.__host}/NetPreSelect.aspx?guid={self.__guid}&lang=zh-tw" if not url else url
        self.__logger.debug(url)
        [self.__logger.debug(f"\t{k}: {v[:40]}") for k, v in self.__post_data.items()]
        [self.__logger.debug(f"\t{k}: {v}") for k, v in data.items()]
        if data:
            self.__post_data.update(data)
        r = self.__session.post(url, data=self.__post_data)
        self.__post_data = get_hidden_values(r.text)
        return r

    def login(self, username: str, password: str):
        self.__session.get("https://course.fcu.edu.tw/validateCode.aspx")
        postdata = {
            "__EVENTTARGET": "ctl00$Login1$LoginButton",
            "ctl00$Login1$RadioButtonList1": "zh-tw",
            "ctl00$Login1$UserName": username,
            "ctl00$Login1$Password": password,
            "ctl00$Login1$vcode": self.__session.cookies.get("CheckCode"),
        }
        r = self.__postback("https://course.fcu.edu.tw/Login.aspx", postdata)
        if "service" not in r.url:
            raise LoginError
        self.__logon = True
        self.__host, self.__guid = parse_url(r.url)
        self.__post_data = get_hidden_values(r.text)
        self.wishupdate(r.text)
        return r

    def checkwish(self, cid: int):
        if cid not in self.__wishmap:
            raise RuntimeError(f"course id {cid} is not in your wish list")

    def wishquery(self, cid: int) -> Dict[int, int]:
        self.checklogin()
        postdata = {
            "__EVENTTARGET": "ctl00$MainContent$TabContainer1$tabCourseSearch$wcCourseSearch$btnSearchOther",
            "ctl00$MainContent$TabContainer1$tabCourseSearch$wcCourseSearch$cbOtherCondition1": "on",
            "ctl00$MainContent$TabContainer1$tabCourseSearch$wcCourseSearch$tbSubID": f"{cid:04d}"
        }
        r = self.__postback(data=postdata)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find("table", id="ctl00_MainContent_TabContainer1_tabCourseSearch_wcCourseSearch_gvSearchResult")
        if table is None:
            raise RuntimeError(f"Nothing found")
        trs = table.find_all("tr")
        querymap = {}
        pos = 2
        for tr in trs[1:]:
            tds = tr.find_all("td", limit=2)
            cid = int(tds[1].font.string)
            querymap[cid] = pos
            pos += 1
        return querymap

    def wishadd(self, cid: int):
        self.checklogin()
        m = self.wishquery(cid)
        pos = m[cid]
        postdata = {
            f"ctl00$MainContent$TabContainer1$tabCourseSearch$wcCourseSearch$gvSearchResult$ctl{pos:02d}$btnAdd": "關注"
        }
        r = self.__postback(data=postdata)
        self.wishupdate(r.text)

    def wishremove(self, cid: int):
        self.checklogin()
        self.checkwish(cid)
        r = self.__wishaction(cid, "btnRemoveItem")
        self.wishupdate(r.text)

    def wishupdate(self, html: str):
        self.checklogin()
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", id="ctl00_MainContent_TabContainer1_tabSelected_gvWishList")
        m = {}
        if table:
            trs = table.find_all("tr")
            pos = 2
            for i in range(1, len(trs), 2):
                tds = trs[i].find_all("td", limit=2)
                cid = int(tds[1].font.string)
                m[cid] = pos
                pos += 2
        self.__wishmap = m

    def wishmap(self):
        self.checklogin()
        return self.__wishmap.copy()

    def wish_addcourse(self, cid: int):
        self.checklogin()
        self.checkwish(cid)
        r = self.__wishaction(cid, "btnAdd")
        self.wishupdate(r.text)

    def wish_register(self, cid: int) -> Tuple[int, int]:
        self.checklogin()
        self.checkwish(cid)
        r = self.__wishaction(cid, "btnQuota")
        result = re.search(r'開放人數： *(\d+) */ *(\d+)', r.text)
        return int(result[1]), int(result[2])

    def __wishaction(self, cid: int, action: str):
        self.checklogin()
        self.checkwish(cid)
        pos = self.__wishmap[cid]
        postdata = {
            "__EVENTTARGET": f"ctl00$MainContent$TabContainer1$tabSelected$gvWishList$ctl{pos:02d}${action}"
        }
        return self.__postback(data=postdata)
