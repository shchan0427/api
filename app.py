from datetime import datetime
from html import unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen


# 나이스 교육정보 개방 포털에서 발급받은 인증키를 따옴표 안에 입력하세요.
API_KEY = ""
NEIS_URL = "https://open.neis.go.kr/hub"
HTML_PATH = Path(__file__).parent / "index1.html"

ALLERGENS = {
    1: "난류", 2: "우유", 3: "메밀", 4: "땅콩", 5: "대두",
    6: "밀", 7: "고등어", 8: "게", 9: "새우", 10: "돼지고기",
    11: "복숭아", 12: "토마토", 13: "아황산류", 14: "호두",
    15: "닭고기", 16: "쇠고기", 17: "오징어", 18: "조개류", 19: "잣",
}


def neis_rows(endpoint, params):
    if not API_KEY.strip():
        raise ValueError("app.py의 API_KEY에 나이스 인증키를 입력해 주세요.")
    query = {"KEY": API_KEY.strip(), "Type": "json", "pIndex": 1, "pSize": 100}
    query.update(params)
    url = f"{NEIS_URL}/{endpoint}?{urlencode(query)}"
    try:
        with urlopen(url, timeout=10) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError("나이스 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
    except (ValueError, UnicodeError) as exc:
        raise ValueError("나이스 응답을 읽지 못했습니다.") from exc
    if endpoint in data:
        return data[endpoint][1].get("row", [])
    result = data.get("RESULT", {})
    if result.get("CODE") == "INFO-200":
        return []
    raise ValueError(result.get("MESSAGE") or "나이스 API 응답을 확인해 주세요.")


def parse_menu(raw):
    menus = []
    for item in re.split(r"<br\s*/?>|\n", raw or "", flags=re.IGNORECASE):
        item = unescape(re.sub(r"<[^>]+>", "", item)).strip()
        if not item:
            continue
        match = re.search(r"\(([\d.,\s]+)\)\s*$", item)
        codes = sorted({int(n) for n in re.findall(r"\d+", match.group(1))}) if match else []
        codes = [n for n in codes if n in ALLERGENS]
        name = item[:match.start()].strip() if match else item
        menus.append({"name": name, "allergens": codes})
    return menus


def first(params, key):
    return params.get(key, [""])[0].strip()


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        self.send_bytes(status, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/":
            html = HTML_PATH.read_text(encoding="utf-8")
            self.send_bytes(200, "text/html; charset=utf-8", html.encode("utf-8"))
            return

        if parsed.path == "/api/schools":
            name = first(params, "name")
            if len(name) < 2:
                self.send_json(400, {"error": "학교 이름을 두 글자 이상 입력해 주세요."})
                return
            try:
                rows = neis_rows("schoolInfo", {"SCHUL_NM": name})
            except ValueError as exc:
                self.send_json(502, {"error": str(exc)})
                return
            self.send_json(200, {"schools": [
                {"name": row.get("SCHUL_NM", ""), "office": row.get("ATPT_OFCDC_SC_CODE", ""),
                 "code": row.get("SD_SCHUL_CODE", ""), "address": row.get("ORG_RDNMA", "")}
                for row in rows
            ]})
            return

        if parsed.path == "/api/meals":
            office, code, date = (first(params, key) for key in ("office", "code", "date"))
            try:
                if not office or not code or not re.fullmatch(r"\d{8}", date):
                    raise ValueError()
                datetime.strptime(date, "%Y%m%d")
            except ValueError:
                self.send_json(400, {"error": "학교와 날짜를 올바르게 선택해 주세요."})
                return
            try:
                rows = neis_rows("mealServiceDietInfo", {
                    "ATPT_OFCDC_SC_CODE": office, "SD_SCHUL_CODE": code, "MLSV_YMD": date
                })
            except ValueError as exc:
                self.send_json(502, {"error": str(exc)})
                return
            self.send_json(200, {"meals": [
                {"type": row.get("MMEAL_SC_NM", "급식"), "date": row.get("MLSV_YMD", date),
                 "calories": row.get("CAL_INFO", ""), "menus": parse_menu(row.get("DDISH_NM", ""))}
                for row in rows
            ]})
            return
        self.send_json(404, {"error": "페이지를 찾을 수 없습니다."})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 5000), Handler)
    print("브라우저에서 http://127.0.0.1:5000 을 여세요.")
    server.serve_forever()

