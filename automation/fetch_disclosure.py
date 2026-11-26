#!/usr/bin/env python3
"""회사 공시 원문(금융감독원 DART) — 실적·투자·합병 같은 회사 소식의 1차 자료를 키 없이 읽는다(RUNBOOK 1-3).

2026-11-26 운영자 '계속 이야기하지만 유의미한 소스를 가지고 만들어야 한다'. 진단: 11/19~11/26 H PICK 8호 중 4호가
원문 없이 '접속이 막혀 못 읽음' 이유(`pick_primary_reason`)로 나갔다 — 엔씨 IR 502·DART 화면을 못 읽음(11/25), 거래소 화면(11/21·11/22),
회사 공지(11/26). DART 는 화면이 자바스크립트로 그려져 읽지 못한다고 여겼지만, 검색 결과와 본문 뷰어(report/viewer.do)는 평범한 HTML 이라
urllib 로 읽힌다(11/26 확인 — NC 3분기 잠정실적 공정공시 본문). dart.fss.or.kr 은 `style.PRIMARY_HOSTS`(fss.or.kr)에 들어 원문으로 센다.

  python3 automation/fetch_disclosure.py 엔씨소프트                 # 최근 14일 공시 목록(접수번호·날짜·제목·주소)
  python3 automation/fetch_disclosure.py 엔씨소프트 --days 30 --grep 실적
  python3 automation/fetch_disclosure.py --read 20261111800311      # 본문(짧은 공시는 전체, 긴 보고서는 목차)
  python3 automation/fetch_disclosure.py --read 20261116002195 --section 3   # 긴 보고서의 3번 목차 본문

출처로 쓸 때: 이름 '{회사} 공시(DART)', 주소 `https://dart.fss.or.kr/dsaf001/main.do?rcpNo={접수번호}`.
'잠정'·'전망' 공시의 숫자는 확정치가 아니다 — 본문에 그렇게 쓴다. 회사가 이름을 바꿔 검색이 비면 새 이름(예: 엔씨소프트 → NC)으로 다시.
종료 코드: 0 = 찾음/읽음, 1 = 못 찾음·접속 실패.
"""
import argparse
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = "https://dart.fss.or.kr"
UA = "Mozilla/5.0 (EDIT H newsletter source check)"


def _get(url, data=None, tries=2):
    body = urllib.parse.urlencode(data).encode() if data else None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
            for enc in ("utf-8", "cp949"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as e:   # noqa: BLE001 — 네트워크 오류는 한 번 더, 그래도 안 되면 위로
            if i + 1 == tries:
                raise
            print(f"  (다시 시도: {e})", file=sys.stderr)
            time.sleep(1.5)


def text_of(fragment):
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", fragment)
    t = re.sub(r"(?is)<tr\b.*?</tr>", lambda m: re.sub(r"\s+", " ", m.group(0)), t)   # 표 한 줄 = 한 줄
    t = re.sub(r"(?i)</t[dh]>", " | ", t)
    t = re.sub(r"(?i)</tr>|<br\s*/?>|</p>|</div>|</h\d>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip(" |") for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln)


ROW = re.compile(r"(?s)<tr>(.*?)</tr>")
RCP = re.compile(r'rcpNo=(\d{14})"[^>]*>(.*?)</a>', re.S)
CORP = re.compile(r"openCorpInfoNew\([^)]*\)[^>]*>(.*?)</a>", re.S)
DAY = re.compile(r"<td>\s*(20\d{2}\.\d{2}\.\d{2})\s*</td>")


def parse_list(page):
    """검색 결과 HTML → [{rcp, corp, title, date, url}] (최신순)."""
    out = []
    for row in ROW.findall(page):
        m = RCP.search(row)
        if not m:
            continue
        corp = CORP.search(row)
        day = DAY.search(row)
        out.append({"rcp": m.group(1), "corp": text_of(corp.group(1)) if corp else "",
                    "title": re.sub(r"\s+", " ", text_of(m.group(2))).strip(),
                    "date": day.group(1).replace(".", "-") if day else "",
                    "url": f"{BASE}/dsaf001/main.do?rcpNo={m.group(1)}"})
    return out


PAGE_SIZE = 100
MAX_PAGES = 5


def search(company, days=14, today=None, get=None):
    """기간 안 공시 전부(최신순) — 한 쪽에 다 안 들어가는 큰 회사는 다음 쪽까지(최대 MAX_PAGES, PR #226 리뷰)."""
    today, get = today or datetime.now(), get or _get
    out = []
    for page in range(1, MAX_PAGES + 1):
        data = {"textCrpNm": company, "startDate": (today - timedelta(days=days)).strftime("%Y%m%d"),
                "endDate": today.strftime("%Y%m%d"), "currentPage": page, "maxResults": PAGE_SIZE, "maxLinks": 10,
                "sort": "date", "series": "desc"}
        rows = parse_list(get(f"{BASE}/dsab007/detailSearch.ax", data))
        out += [r for r in rows if r["rcp"] not in {o["rcp"] for o in out}]
        if len(rows) < PAGE_SIZE:
            break
    return out


TOC = re.compile(r"node\d+\['text'\] = \"(.*?)\";\s*node\d+\['id'\] = \"[^\"]*\";\s*node\d+\['rcpNo'\] = \"(\d+)\";\s*"
                 r"node\d+\['dcmNo'\] = \"(\d+)\";\s*node\d+\['eleId'\] = \"(\d+)\";\s*node\d+\['offset'\] = \"(\d+)\";\s*"
                 r"node\d+\['length'\] = \"(\d+)\";\s*node\d+\['dtd'\] = \"([^\"]*)\"", re.S)
FIRST = re.compile(r'viewDoc\("(\d+)", "(\d+)", "(\d+)", "(\d+)", "(\d+)", "([^"]*)"')


def toc_of(main_page):
    """공시 뷰어 첫 화면 → 목차 [(제목, (rcp, dcm, ele, off, len, dtd))]. 목차가 없으면 첫 문서 하나."""
    items = [(html.unescape(m.group(1)).strip(), m.groups()[1:]) for m in TOC.finditer(main_page)]
    if not items:
        f = FIRST.search(main_page)
        if f:
            items = [("본문", f.groups())]
    return items


def viewer(args):
    rcp, dcm, ele, off, ln, dtd = args
    q = urllib.parse.urlencode({"rcpNo": rcp, "dcmNo": dcm, "eleId": ele, "offset": off, "length": ln, "dtd": dtd})
    return text_of(_get(f"{BASE}/report/viewer.do?{q}"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="DART 공시 원문 — 목록·본문(키 없이)")
    ap.add_argument("company", nargs="?", help="회사 이름(공시에 쓰는 이름)")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--grep", nargs="*", default=[], help="제목에 이 말이 든 공시만")
    ap.add_argument("--read", metavar="접수번호", help="공시 본문 읽기")
    ap.add_argument("--section", type=int, help="긴 보고서에서 읽을 목차 번호(--read 와 함께)")
    ap.add_argument("--max", type=int, default=6000, help="본문 최대 글자 수")
    a = ap.parse_args(argv)
    try:
        if a.read:
            items = toc_of(_get(f"{BASE}/dsaf001/main.do?rcpNo={a.read}"))
            if not items:
                print("본문을 찾지 못했어요 — 접수번호를 확인하세요.", file=sys.stderr)
                return 1
            print(f"출처 주소: {BASE}/dsaf001/main.do?rcpNo={a.read}")
            if len(items) > 1 and a.section is None:
                print("목차(긴 보고서 — --section 번호로 읽기):")
                for i, (title, _) in enumerate(items, 1):
                    print(f"  {i:>2}. {title}")
                return 0
            idx = (a.section or 1) - 1
            if not 0 <= idx < len(items):
                print(f"목차 번호는 1~{len(items)}", file=sys.stderr)
                return 1
            body = viewer(items[idx][1])
            print(f"[{items[idx][0]}]\n{body[:a.max]}")
            if len(body) > a.max:
                print(f"… ({len(body) - a.max}자 더 — --max 로 늘리기)")
            return 0
        if not a.company:
            ap.error("회사 이름이나 --read 접수번호를 주세요")
        rows = search(a.company, a.days)
        if a.grep:
            rows = [r for r in rows if any(g in r["title"] for g in a.grep)]
        if not rows:
            print(f"'{a.company}' 최근 {a.days}일 공시가 없어요(이름이 바뀌었으면 새 이름으로).", file=sys.stderr)
            return 1
        for r in rows:
            print(f"{r['date']} {r['rcp']} [{r['corp']}] {r['title']}\n    {r['url']}")
        return 0
    except Exception as e:   # noqa: BLE001
        print(f"DART 접속 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
