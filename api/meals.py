from datetime import datetime
from html import unescape
from http.server import BaseHTTPRequestHandler
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen


def parse_menu(raw):
    menus = []
    for item in re.split(r"<br\s*/?>|\n", raw or "", flags=re.IGNORECASE):
        item = unescape(re.sub(r"<[^>]+>", "", item)).strip()
        if not item:
            continue
        match = re.search(r"\(([\d.,\s]+)\)\s*$", item)
        codes = sorted({int(n) for n in re.findall(r"\d+", match.group(1))}) if match else []
        codes = [n for n in codes if 1 <= n <= 19]
        name = item[:match.start()].strip() if match else item
        menus.append({"name": name, "allergens": codes})
    return menus


class handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        office = params.get("office", [""])[0].strip()
        code = params.get("code", [""])[0].strip()
        date = params.get("date", [""])[0].strip()
        try:
            if not office or not code or not re.fullmatch(r"\d{8}", date):
                raise ValueError()
            datetime.strptime(date, "%Y%m%d")
        except ValueError:
            self.respond(400, {"error": "학교와 날짜를 올바르게 선택해 주세요."})
            return

        key = os.environ.get("NEIS_API_KEY", "").strip()
        if not key:
            self.respond(503, {"error": "Vercel 환경 변수 NEIS_API_KEY를 설정해 주세요."})
            return

        query = {"KEY": key, "Type": "json", "pIndex": 1, "pSize": 100,
                 "ATPT_OFCDC_SC_CODE": office, "SD_SCHUL_CODE": code, "MLSV_YMD": date}
        url = "https://open.neis.go.kr/hub/mealServiceDietInfo?" + urlencode(query)
        try:
            with urlopen(url, timeout=10) as response:
                data = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError):
            self.respond(502, {"error": "나이스 급식 정보를 불러오지 못했습니다."})
            return

        if "mealServiceDietInfo" in data:
            rows = data["mealServiceDietInfo"][1].get("row", [])
        elif data.get("RESULT", {}).get("CODE") == "INFO-200":
            rows = []
        else:
            self.respond(502, {"error": data.get("RESULT", {}).get("MESSAGE", "나이스 응답 오류")})
            return

        self.respond(200, {"meals": [
            {"type": row.get("MMEAL_SC_NM", "급식"), "date": row.get("MLSV_YMD", date),
             "calories": row.get("CAL_INFO", ""), "menus": parse_menu(row.get("DDISH_NM", ""))}
            for row in rows
        ]})

