from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen


class handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        name = parse_qs(urlparse(self.path).query).get("name", [""])[0].strip()
        if len(name) < 2:
            self.respond(400, {"error": "학교 이름을 두 글자 이상 입력해 주세요."})
            return

        key = os.environ.get("NEIS_API_KEY", "").strip()
        if not key:
            self.respond(503, {"error": "Vercel 환경 변수 NEIS_API_KEY를 설정해 주세요."})
            return

        params = {"KEY": key, "Type": "json", "pIndex": 1, "pSize": 100, "SCHUL_NM": name}
        url = "https://open.neis.go.kr/hub/schoolInfo?" + urlencode(params)
        try:
            with urlopen(url, timeout=10) as response:
                data = json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            self.respond(502, {"error": "나이스 학교 정보를 불러오지 못했습니다."})
            return

        if "schoolInfo" in data:
            rows = data["schoolInfo"][1].get("row", [])
        elif data.get("RESULT", {}).get("CODE") == "INFO-200":
            rows = []
        else:
            self.respond(502, {"error": data.get("RESULT", {}).get("MESSAGE", "나이스 응답 오류")})
            return

        self.respond(200, {"schools": [
            {"name": row.get("SCHUL_NM", ""), "office": row.get("ATPT_OFCDC_SC_CODE", ""),
             "code": row.get("SD_SCHUL_CODE", ""), "address": row.get("ORG_RDNMA", "")}
            for row in rows
        ]})

