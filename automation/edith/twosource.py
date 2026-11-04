"""숫자 2곳 대조(2026-11-05 호~) — content 의 숫자가 그 이슈 원 기사 두 곳에 다 있나.

11/03 호 '왜 중요해'의 '미국 2024년 5월 T+1'·'매도대금담보대출 연 7.5~10%'는 머니투데이 한 곳에만 있었다.
11/04 호 카드 ④ '2014년 출시 뒤 약 12년 만'도 조선비즈 한 곳에만 있었다(08:15 '오늘 호 함께 점검').
원칙 2(숫자·날짜는 서로 다른 출처 2건)는 RUNBOOK 에만 있고 기계 검사가 없었다 — 11/03 운영자 '내일 발행할 때 각별히 신경써줘'.

이슈마다(big_issue·items + 그 이슈의 카드, 메인 이슈는 deep·dive 카드도) 글에 나온 숫자를 뽑아,
그 이슈 sources 기사 본문 몇 곳에 같은 값이 있는지 센다(check_sources.py 가 기사를 읽어 넘긴다).
  막음 — 그 이슈 기사를 모두(2곳 이상) 읽었는데 한 곳에만 있는 숫자(날짜의 월·일·시각은 경고만 — '지난달 30일'처럼 상대 날짜로도 쓴다)
  경고 — 기사 어디에도 없는 숫자(우리가 계산·환산했으면 괜찮다), 기사를 다 못 읽은 이슈(발행을 멈추지 않는다)
값 맞추기: '14조2209억원' = '14조 2,209억 원', '1만원' = '1만 원', '%포인트' = '%p'. content 가 어림값이면('14.2조'·'약 3500억'·
'6000억원 넘게') 마지막 자리 반올림 안에서 같다고 본다 — 소수점이 있거나 조·억·만 앞이 0으로 끝날 때만(맨숫자 '10년'은 정확히).
"""
import re

FROM = "2026-11-05"   # 이 날짜 호부터 빌드가 막는다(그 전 호는 기록이라 보지 않는다)

_NUMTXT = r"\d[\d,]*(?:\.\d+)?(?:\s*[조억만천백](?:\s*\d[\d,]*(?:\.\d+)?)?)*"
_UNITS = ("%p|%포인트|퍼센트포인트|%|퍼센트|원|달러|엔|위안|유로|명|건|개월|개|곳|배|년|월|일|시간|시|분|초|위|호|대|채|가구|회|세|살|"
          "km|kg|톤|평|bp")
_TOKEN = re.compile(rf"(?<![\d.,A-Za-z])({_NUMTXT})\s?(?:여\s?)?({_UNITS})?")
_UNIT_SAME = {"퍼센트": "%", "%포인트": "%p", "퍼센트포인트": "%p", "살": "세"}
# 세는 말은 매체마다 다르게 붙인다 — 11/03 메타 '광고주 1000만곳'(아시아경제) = '1000만명'(뉴시스). 같은 값이면 같은 사실로 본다
_COUNT = {"명", "곳", "개", "개사", "가구", "채", "대", "건", "회"}
DATE_UNITS = {"월", "일", "시", "분", "초"}   # 상대 날짜('지난달 30일'·'오는 15일')로도 쓰여 한 곳에만 나와도 경고만
_BIG = {"조": 1e12, "억": 1e8, "만": 1e4}
_SMALL = {"천": 1e3, "백": 1e2}
# 날짜 꼴('11/4', '11.04')과 고정 표현('2030세대')은 사실 숫자가 아니다
_SKIP = re.compile(r"\b\d{1,2}/\d{1,2}\b|(?<![\d.])\d{1,2}\.\d{2}(?=[\s),]|$)|2030\s?(?:세대|대)")
_SKIP_KEYS = {"source", "sources", "pose", "by", "ask", "accent", "no", "series_label", "photo", "credit", "focus", "img"}


def value(numtxt):
    """'14조2209억' → 1.42209e13, '5천6백만' → 5.6e7, '2,209' → 2209."""
    total = section = 0.0
    cur = None
    for tok in re.findall(r"\d+(?:\.\d+)?|[조억만천백]", re.sub(r"[,\s]", "", numtxt)):
        if tok[0].isdigit():
            cur = float(tok)
        elif tok in _SMALL:
            section += (cur if cur is not None else 1.0) * _SMALL[tok]
            cur = None
        else:
            section += cur or 0.0
            total += (section or 1.0) * _BIG[tok]
            section, cur = 0.0, None
    return total + section + (cur or 0.0)


def _tolerance(numtxt, v, approx=False):
    """어림값의 반올림 폭 — 소수점이 있으면 그 마지막 자리, 조·억·만·천 앞 숫자가 0으로 끝나면 그 0 자리,
    '약 34만 원'·'3만5000여 명'·'6000억원 넘게'처럼 어림말이 붙으면 마지막 자리 반(approx). 아니면 0(정확히 — '34만3000원'은 34만3300원과 다르다)."""
    t = re.sub(r"[,\s]", "", numtxt)
    parts = re.findall(r"(\d+(?:\.\d+)?)([조억만천백]?)", t)
    if not parts:
        return 0.0
    digits, unit = parts[-1]
    scale = _BIG.get(unit) or _SMALL.get(unit) or 1.0
    if "." in digits:
        return 0.5 * scale * 10 ** -len(digits.split(".")[1])
    zeros = len(digits) - len(digits.rstrip("0"))
    if unit and zeros and digits.rstrip("0"):
        return 0.5 * scale * 10 ** zeros
    if approx:
        return 0.5 * scale * 10 ** zeros
    return 0.0


def numbers(text):
    """글 → [(원문, 값, 단위, 반올림 폭)]. 한 자리 맨숫자('3분기'·'4일')는 너무 흔해 빼고, 소수·조억만 붙은 수는 둔다."""
    text = _SKIP.sub(" ", re.sub(r"https?://\S+|==|\*\*", " ", str(text)).replace("％", "%"))   # 주소 속 번호(파일 id)는 숫자가 아니다
    out = []
    for m in _TOKEN.finditer(text):
        num, unit = m.group(1).strip(), _UNIT_SAME.get(m.group(2) or "", m.group(2) or "")
        plain_digits = re.sub(r"[,\s]", "", num)
        if re.fullmatch(r"\d", plain_digits):
            continue
        v = value(num)
        approx = bool(re.search(r"약\s?$", text[max(0, m.start() - 3):m.start()]) or "여" in m.group(0)
                      or re.match(r"\s?(?:가량|안팎|쯤|정도|남짓|넘게)", text[m.end():m.end() + 4]))
        out.append((m.group(0).strip(), v, unit, _tolerance(num, v, approx)))
    return out


def same(c, a):
    """content 숫자 c(원문, 값, 단위, 폭) ↔ 기사 숫자 a — 단위는 둘 다 있을 때만 같아야 한다."""
    _, cv, cu, tol = c
    _, av, au, _ = a
    if cu and au and cu != au and not (cu in _COUNT and au in _COUNT):
        return False
    return abs(cv - av) <= max(tol, 1e-9 * max(abs(cv), 1.0))


def _flat(name, v):
    if v is None or isinstance(v, (bool, int, float)):
        return []
    if isinstance(v, str):
        return [(name, v)] if v.strip() else []
    if isinstance(v, list):
        return [x for i, y in enumerate(v, 1) for x in _flat(f"{name} {i}", y)]
    if isinstance(v, dict):
        if isinstance(v.get("value"), (str, int, float)) and isinstance(v.get("unit"), str):   # stat {value '6423', unit '억원'} → '6423억원'
            v = {**v, "value": f"{v['value']}{v['unit']}", "unit": None}
        return [x for k, y in v.items() if k not in _SKIP_KEYS for x in _flat(f"{name}.{k}", y)]
    return []


def issue_texts(d):
    """content.load 결과 → [(tag, sources, [(칸 이름, 글)])] — big_issue·items 마다 그 이슈 글 + 그 이슈 카드(+ 메인은 deep·dive 카드)."""
    cards = {c.get("tag"): c for c in d.get("card_issues") or []}
    extra = (d.get("cards") or {})
    out = []
    for i, it in enumerate(d.get("all_items") or []):
        texts = []
        for k in ("title", "body", "takeaway", "why", "paragraphs", "checklist", "numbers", "stat", "compare", "metrics", "lead"):
            texts += _flat(k, it.get(k))
        card = cards.get(it.get("tag")) or {}
        for k in ("headline", "body", "number", "takeaway", "metrics", "compare"):
            texts += _flat(f"카드 {k}", card.get(k))
        if i == 0:   # 메인 이슈(H PICK)의 깊이 읽기 카드
            texts += _flat("카드 deep", extra.get("deep")) + _flat("카드 dive", extra.get("dive"))
        out.append((it.get("tag") or f"이슈 {i + 1}", it.get("sources") or [], texts))
    return out


def article_numbers(article):
    """read_article.read() 결과(또는 같은 꼴 dict) → 숫자 목록. 제목·요약·본문 모두."""
    return numbers(" \n".join(str(article.get(k) or "") for k in ("title", "description", "body")))


def check(d, articles):
    """content(load 결과) + {url: 기사 dict 또는 None(못 읽음)} → {"blocked": [...], "warnings": [...], "issues": [...]}.
    blocked·warnings 는 사람이 읽는 한 줄들, issues 는 이슈마다 읽은 기사 수·한 곳에만 있는 숫자·어디에도 없는 숫자."""
    blocked, warnings, issues = [], [], []
    for tag, sources, texts in issue_texts(d):
        srcs = list({s["url"]: (s.get("name") or s["url"], s["url"]) for s in sources if s.get("url")}.values())   # 같은 기사를 두 번 적어도 한 곳
        read = [(name, article_numbers(articles[url])) for name, url in srcs if articles.get(url)]
        unread = [name for name, url in srcs if not articles.get(url)]
        row = {"tag": tag, "sources": len(srcs), "read": len(read), "unread": unread, "single": [], "none": []}
        issues.append(row)
        if unread:
            warnings.append(f"[{tag}] 기사 {len(srcs)}곳 중 {len(read)}곳만 읽음({'·'.join(unread)} 못 읽음) — 이 이슈 숫자는 2곳 대조를 못 했어요."
                            " read_article.py 로 다시 읽거나 --search 로 같은 사실의 다른 매체 기사를 찾아 sources 에 더하세요")
        if len(read) < 2:
            continue
        seen = set()
        for where, text in texts:
            for c in numbers(text):
                key = (round(c[1], 6), c[2])
                if key in seen:
                    continue
                seen.add(key)
                found = [name for name, nums in read if any(same(c, a) for a in nums)]
                if len(found) >= 2:
                    continue
                item = {"num": c[0], "where": where, "found": found}
                if not found:
                    row["none"].append(item)
                    warnings.append(f"[{tag}] '{c[0]}' — 읽은 기사 {len(read)}곳 어디에도 없어요({where}). 우리가 계산·환산한 값이면 괜찮고, 아니면 숫자를 확인하세요")
                elif unread or c[2] in DATE_UNITS:
                    row["single"].append(item)
                    warnings.append(f"[{tag}] '{c[0]}' — {found[0]}에만 있어요({where})"
                                    + (" — 날짜는 다른 기사가 '지난달·오는'처럼 쓸 수 있어 경고만" if c[2] in DATE_UNITS else ""))
                else:
                    row["single"].append(item)
                    blocked.append(f"[{tag}] '{c[0]}' — {found[0]}에만 있어요({where}). 두 기사에 다 있는 사실로 바꾸거나, 숫자를 빼거나, "
                                   "같은 숫자를 쓴 다른 매체 기사를 sources 에 더하세요(원칙 2)")
    return {"blocked": blocked, "warnings": warnings, "issues": issues}
