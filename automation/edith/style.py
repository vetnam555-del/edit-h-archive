"""문장 점검 — 토스 라이팅 8원칙을 뉴스레터·카드·캡션에 옮긴 것(2026-10-03, 토스·머니그라피 레퍼런스 조사).

토스는 모든 문구를 '군더더기 빼기 · 빈 문장 빼기 · 핵심만 · 쉬운 말 · 강요 대신 제안 · 모두에게 통하는 말 · 숨은 감정 ·
다음 화면 예고' 8원칙과 해요체·능동형으로 쓴다(automation/references.md '토스·머니그라피 심층').
이 중 기계로 잡을 수 있는 것만 경고한다 — 빌드를 막지 않는다. 제작 세션이 경고를 보고 문장을 고친다.

  군더더기   기사 요약체('~것으로 나타났다', '~에 따르면'(캡션·카드)), '다양한', '되어지다'
  해요체     '~습니다/~니다' 로 끝나는 문장
  강요 대신 제안   '놓치지 마세요', '반드시', '지금 바로', '충격', '!!'
  핵심만     한 문장이 너무 길면(카드 50자·본문 80자) 둘로
  쉬운 말    풀이 없는 금융·정책 약어(예 DSR → '대출 한도 규제(DSR)') — 브랜드 이름(CU·SKT 등)은 그대로 둔다
"""
import re

from .common import plain

STYLE_FROM = "2026-10-06"   # E2 편집 개편과 같은 날 시작(같은 '문장' 변수로 묶는다)
MAX_LINES = 8

# 처음 나올 때 풀어 써야 하는 금융·정책 약어(브랜드·회사 이름은 넣지 않는다 — 그건 이름이라 풀 게 없다).
JARGON = {"DSR", "DTI", "LTV", "ETF", "ETN", "ELS", "ISA", "IRP", "CMA", "MMF", "CPI", "PPI", "GDP", "PER", "PBR", "ROE", "EPS",
          "IPO", "PF", "FOMC", "CBDC", "STO", "ESG", "LNG", "VPN", "APR", "APY", "RWA", "SaaS", "B2B", "B2C", "D2C", "MAU", "DAU",
          "ARPU", "GMV", "KPI", "OKR", "TDF", "CDS", "REITs", "BNPL", "PG", "VAN", "OTA", "LLM", "GPU", "NPU", "HBM"}

_WEED = [
    (re.compile(r"것으로 (나타났|알려졌|전해졌|조사됐|집계됐|분석됐|보인다|예상된다|파악됐)"), "기사 요약체 — 사실을 바로 말하세요('~래요/~예요')"),
    (re.compile(r"다양한"), "'다양한' — 무엇이 몇 가지인지 구체적으로"),
    (re.compile(r"되어지|되어진|되어져"), "이중 피동 — '~돼요/~됐어요'"),
    (re.compile(r"할 수 있을 것으로|하는 것이 (중요|필요)"), "빈 문장 — 핵심만 남기세요"),
]
_WEED_SOCIAL = [(re.compile(r"에 따르면"), "'~에 따르면' — 캡션·카드는 입말로('~래요'), 출처는 출처 칸에")]
_FORCE = [(re.compile(p), why) for p, why in [
    (r"놓치지 마", "강요 — 제안으로('~해 보면 좋아요')"),
    (r"반드시", "강요 — 이유를 말하고 제안으로"),
    (r"지금 바로", "재촉 — 빼도 뜻이 같아요"),
    (r"충격", "겁주기·낚시 단어"),
    (r"!!", "느낌표 겹침"),
]]
_FORMAL = re.compile(r"[가-힣]+니다(?=[.!?)\s]|$)")
_SENT = re.compile(r"[^.?!\n]+[.?!]?")
_ACRONYM = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9]{2,5})(?![A-Za-z0-9])")


def _texts(d):
    """(위치, 글, 종류) — 종류: card(카드·제목) / body(뉴스레터 본문) / social(캡션)."""
    out = [("제목", d.get("title"), "card"), ("부제", d.get("subtitle"), "body"), ("에디터 H 노트", d.get("lead"), "body"),
           ("H의 한 줄", d.get("observation"), "obs")]
    big = d.get("big_issue") or {}
    out += [(f"H PICK 무슨 일이야 {i}", p, "body") for i, p in enumerate(big.get("paragraphs") or [], 1)]
    why = big.get("why") or []
    out += [(f"H PICK 왜 중요해 {i}", p, "body") for i, p in enumerate([why] if isinstance(why, str) else why, 1)]
    out.append(("H PICK 그래서", big.get("takeaway"), "body"))
    for it in d.get("items") or []:
        t = plain(it.get("title") or "")[:14]
        out += [(f"'{t}' 본문", it.get("body"), "body"), (f"'{t}' 그래서", it.get("takeaway"), "body")]
    for b in d.get("briefs") or []:
        out.append((f"한 줄 뉴스 '{plain(b.get('title') or '')[:14]}'", f"{b.get('title', '')} {b.get('body', '')}", "body"))
    cards = d.get("cards") or {}
    for i, it in enumerate(cards.get("issues") or [], 1):
        out += [(f"카드 {i} 제목", it.get("headline"), "card"), (f"카드 {i} 본문", it.get("body"), "card"),
                (f"카드 {i} 그래서", it.get("takeaway"), "card")]
    deep = cards.get("deep") or {}
    out += [(f"심층 카드 요점 {i}", p, "card") for i, p in enumerate(deep.get("points") or [], 1)]
    ig = d.get("instagram") or {}
    out += [("인스타 캡션", ig.get("caption"), "social"), ("인스타 질문", ig.get("ask"), "social")]
    return [(w, plain(str(t)).replace("\n", " ").strip(), k) for w, t, k in out if t]


def _clip(text, m, width=18):
    a, b = max(0, m.start() - 6), min(len(text), m.end() + width - 6)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


FOLD = 125   # 인스타 캡션이 '더 보기' 전에 보여 주는 대략의 글자 수


def caption_keyword(d):
    """캡션 첫 화면('더 보기' 전 약 125자)에 오늘 핵심어(해시태그 앞 3개)가 있는가 — 없으면 경고 한 줄.
    2026-10-09 운영자 공유 자료: 인스타 대표(Mosseri)는 해시태그가 도달을 늘리는 수단이 아니라 분류용이라 했고(2025-12 부터 5개 제한),
    검색은 이름·소개글·캡션 글을 읽는다 — 핵심어는 해시태그 나열 대신 첫 문장에 자연스럽게."""
    ig = d.get("instagram") or {}
    tags = [t for t in (re.sub(r"\s+", "", plain(str(t)).lstrip("#")) for t in (ig.get("hashtags") or [])[:3]) if t]
    head = plain(ig.get("caption") or "")[:FOLD]
    if not tags or not head:
        return []
    compact = re.sub(r"\s+", "", head)
    words = re.findall(r"[0-9A-Za-z]+|[가-힣]+", head)
    if any(t in compact or any(len(w) > 1 and w in t for w in words) for t in tags):
        return []
    return [f"인스타 캡션: 첫 {FOLD}자('더 보기' 전)에 오늘 핵심어({', '.join(tags)})가 없어요 — 검색에 걸리게 첫 줄이나 둘째 문장에 자연스럽게"]


SHARE_FROM = "2026-10-10"   # E6 — 이 날부터 데일리 호는 instagram.share_to 를 쓴다
_BROAD_WHO = {"친구", "지인", "모두", "여러분", "누구나", "가족", "사람", "주변 사람"}


def share_check(d):
    """instagram.share_to(누구에게 보낼지) — 비었거나 너무 넓으면 경고 한 줄."""
    if str(d.get("date", ""))[:10] < SHARE_FROM:
        return []
    who = plain((d.get("instagram") or {}).get("share_to") or "").strip()
    if not who:
        return ["인스타 share_to 가 비었어요 — 이 소식이 꼭 필요한 사람(예: '프리랜서 친구', '청약 준비하는 친구')을 적으세요"]
    if who in _BROAD_WHO or len(who) > 14:
        return [f"인스타 share_to '{who}' — 너무 넓거나 길어요. 이 소식이 꼭 필요한 사람을 2~14자로 콕 집어 주세요"]
    return []


def lint(d):
    """경고 문장 목록(최대 MAX_LINES 개 + 남은 개수). 형식 2·데일리·STYLE_FROM 이후 호만."""
    if d.get("format") != 2 or d.get("rewind") or str(d.get("date", ""))[:10] < STYLE_FROM:
        return []
    found, seen_acr = caption_keyword(d) + share_check(d), set()
    for where, text, kind in _texts(d):
        rules = _WEED + _FORCE + (_WEED_SOCIAL if kind in ("social", "card", "obs") else [])
        for rx, why in rules:
            m = rx.search(text)
            if m:
                found.append(f"{where}: '{_clip(text, m)}' — {why}")
        m = _FORMAL.search(text)
        if m:
            found.append(f"{where}: '{_clip(text, m)}' — 해요체로('~해요/~예요')")
        limit = {"card": 50, "obs": 90}.get(kind, 80)
        for s in _SENT.findall(text):
            s = s.strip()
            if len(s) > limit:
                found.append(f"{where}: 한 문장 {len(s)}자 — {limit}자 안으로 나누세요('{s[:16]}…')")
                break
        for m in _ACRONYM.finditer(text):
            a = m.group(1)
            if a not in JARGON or a in seen_acr:
                continue
            seen_acr.add(a)
            near = text[max(0, m.start() - 16):m.end() + 2]
            if f"({a})" in near or re.search(rf"{a}\s*\(", text[m.start():m.end() + 3]):
                continue
            found.append(f"{where}: '{a}' — 처음 나올 때 쉬운 말로 풀어 주세요(예: 대출 한도 규제(DSR))")
    if len(found) > MAX_LINES:
        found = found[:MAX_LINES] + [f"… 그 밖에 {len(found) - MAX_LINES}곳"]
    return found
