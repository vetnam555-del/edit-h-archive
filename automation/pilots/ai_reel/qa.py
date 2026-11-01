#!/usr/bin/env python3
"""AI 릴스·H 극장 만화 검수 — 올리기 전에 반드시 돌린다(2026-11-01 운영자 "검수도 잘해주고").

사용: python3 automation/pilots/ai_reel/qa.py <episode.json> [--no-asr] [--video 다른 영상.mp4]
검사(하나라도 ✗ 면 올리지 않는다):
 1. 숫자 대조 — 화면 글자·말풍선·설명·캡션에 나온 숫자가 그날 content/{날짜}.json 에 그대로 있나(확인된 숫자만).
 2. 대사 — 완성본을 음성 인식(faster-whisper small)으로 받아 적어, 대사 줄마다 낱말이 충분히 들리나.
    대사 원고의 숫자(한글 읽기)는 content 와, 들린 숫자는 대사 숫자와 같은 값이어야 한다(11/01 Codex — 목소리가 틀린 금액을 말하면 막는다).
 3. 소리 — 통합 음량 -14±1.5 LUFS, 음성 트랙이 있다, 중간에 끊기는 곳이 없다(11/01 운영자 "소리가 중간중간 끊긴다").
 4. 영상 — 1080×1920, 길이 8~30초, 검은 화면·어둡게 번쩍이는 프레임이 한 프레임도 없다
    (11/01 운영자 "영상 중간중간에 검은색으로 끊기는 것 같다" — 끝 화면 페이드 인이 2프레임 검게 튀었다).
 5. 캡션 — reel_ai_caption.txt·comic_caption.txt 에 'AI로 만들' 한 줄, 해시태그 5개 이하, 같은 숫자 대조(끝 화면·만화 끝 장 문구도).
 6. 만화 — comic/ JPEG 3~10장, 1080×1350.
 7. 금지 — 화면 글자에 'AI로 만든 영상' 표시 없음(운영자 11/01), 실존 인물·회사 로고는 사람이 프레임 캡처로 한 번 더 본다(자동 아님).
 8. 같은 틀 반복 금지(2026-11-02~) — 첫 마디(전날까지)·훅 종류·끝 자막 머리말·끝인사가 같은 날 다른 릴스와 겹치면 실패
    (11/01 운영자 "패턴이 똑같네? 헉으로 시작하고 멘트가 비슷하다").
 9. 기사·출처 맞춤(2026-11-02~) — item(다루는 이슈 tag)과 sources 에 그 이슈의 원 기사 매체 2곳 이상(그 이슈 sources 안의 매체),
    끝 화면 note·reel_ai_caption.txt '출처' 줄에 그 매체 이름이 다 있어야 한다(11/01 운영자 "기사 및 소스에 맞춰서 진행해 달라").
    '오늘 아침 5가지' 브리핑(items 목록)은 캡션 '출처:' 줄을 영상 순서대로 이슈마다 한 칸(' / ')씩 — 그 이슈 매체 2곳, 다른 이슈 매체 없이 — 끝 화면 note 엔 출처 안내만(2026-11-01 운영자).
"""
import argparse
import datetime as dt
import difflib
import html as htmlmod
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# 큰 금액은 한 덩어리로('3천억원'·'3백억원'·'5천6백만원'·'2만5천명'도 — 11/01 Codex) — "1조6000억원"을 "1조"·"6000억"으로 쪼개 따로 찾으면 content 가 "1조5000억원과 6000억원"일 때도 통과한다(11/01 Codex)
# 등락 부호도 숫자의 일부 — "+7.08%"가 content 의 "-7.08%"로 통과하면 안 된다(11/01 Codex). 낱말 사이 '-'(2026-11-01)는 부호가 아니다
NUM = re.compile(r"(?:(?<![\w.])[+\-−▲▼]\s?)?\d[\d,]*(?:\.\d+)?(?:\s*[조억만천백]+\s*\d[\d,]*(?:\.\d+)?)*[조억만천백]*\s*(?:여\s*)?"
                 r"(?:%p|%포인트|%|원|명|건|분|초|시간|시|일|개|배|p|bp|달러|위|호|거래일|년|월|평|장|종목|가지|군데|곳|번|살|달|채|대|마리|권|잔|병)?")
SIGN = str.maketrans({"−": "-", "▲": "+", "▼": "-"})
# content 는 부호 대신 말로 쓰기도 한다 — "3.02% 내린", "3.0% 늘어", "7% 넘게 내렸어요"
DOWN = "내리|내린|내려|내렸|하락|떨어|빠진|빠졌|빠지|감소|줄어|줄었|급락|밀려|밀린|밀렸"
UP = "오른|올라|올랐|오르|상승|늘어|늘었|증가|급등|뛰었|뛴|뛰어"


def plain(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def norm_num(tok):
    return re.sub(r"[\s,여]", "", tok).translate(SIGN)   # '3만5000여 명' = 3만5000명 — 어림 '여'는 값·단위를 바꾸지 않는다(11/01 서울마라톤 편)


def numbers(text, keep_single=False):
    out = []
    for m in NUM.finditer(text):
        t = norm_num(m.group(0))
        if not keep_single and re.fullmatch(r"[+-]?\d", t):   # 한 자리 맨숫자(컷 번호 등)는 건너뛴다
            continue
        out.append(t)
    return out


def corpus_numbers(corpus):
    """content 의 숫자 → {부호 뺀 숫자: {부호}}. 부호가 없으면 바로 뒤 말(내린·오른 …)로 부호를 정한다, 없으면 ''."""
    have = {}
    for m in NUM.finditer(corpus):
        c = norm_num(m.group(0))
        sign, body = (c[0], c[1:]) if c[0] in "+-" else ("", c)
        if not sign:
            tail = corpus[m.end():m.end() + 12]
            if re.match(rf"\s*(?:\S{{1,3}}\s+)?(?:{DOWN})", tail):
                sign = "-"
            elif re.match(rf"\s*(?:\S{{1,3}}\s+)?(?:{UP})", tail):
                sign = "+"
        have.setdefault(body, set()).add(sign)
    return have


BRAND_TOKENS = {"8시", "30분", "2030"}   # 끝 화면 고정 문구(발송 시각 8시 30분·'2030의 아침') — content 숫자가 아니어도 된다
# 어디에 나와도 content 숫자가 아닌 고정 문구 — 확인 기준('기사 2곳 이상에서 확인했어요')
BRAND_PHRASES = re.compile(r"(?:기사|출처|매체|언론)\s*2\s*곳\s*이상")


def check_numbers(texts, corpus, allow=()):
    """화면 숫자를 값으로 content 와 맞춘다 — '3천억원' = '3000억원', '1조6000억원'은 한 덩어리(조각 '1조'·'6000억'으로는 통과 못 함).
    단위는 둘 다 있을 때 같아야 하고('12거래일' ≠ '11거래일'), 단위 없는 맨숫자는 같은 수나 그 수의 소수(5599 ↔ 5599.42)면 통과(% 수와는 아니다).
    부호: 화면 숫자에 +·-가 있으면 content 의 같은 수도 그 방향이어야 한다('-7.08%' 또는 '7.08% 내린'). 부호 없는 화면 숫자는 따지지 않는다."""
    cvals = content_values(corpus)
    bad = []
    for label, text in texts:
        text = BRAND_PHRASES.sub(" ", text)
        for m in NUM.finditer(text):
            t = norm_num(m.group(0))
            if re.fullmatch(r"[+-]?\d", t) or t in allow:
                continue
            sign, body = (t[0], t[1:]) if t[0] in "+-" else ("", t)
            if not sign and body.endswith(("%", "%p", "%포인트", "p")):
                sign = _sign_near(text, m.start(), m.end(), words=True)   # '3.48% 상승'·'빠졌다고' — 등락률만 말로 방향을 읽는다(11/01 Codex)
            unit = re.sub(r"^[\d.,조억만천백]+", "", body)
            v = korean_number(body[: len(body) - len(unit)] if unit else body)
            unit = UNIT_SAME.get(unit, unit)
            if v is None or not any(_num_match((round(v, 6), unit, sign), c, strict=True) for c in cvals):
                bad.append(f"{label}: '{t}'")
        # 화면의 고유어 수사 + 세는 말('반도체 세 종목') — '한 번·한 달' 같은 관용구(1)는 뺀다(11/01 Codex)
        for _, n in native_numbers(text):
            if n[0] != 1 and _say(n) not in allow and not any(_num_match(n, c, strict=True) for c in cvals):
                bad.append(f"{label}: '{_say(n)}'")
    return bad


def parse_blackdetect(stderr):
    """ffmpeg blackdetect 출력 → [(시작초, 끝초)]."""
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", stderr)]


def black_frames(video):
    """화면의 90% 이상이 검은(밝기 12% 아래) 구간 — 한 프레임(0.033초)이라도 잡는다(11/01 운영자 '검은색으로 끊긴다')."""
    er = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-vf", "blackdetect=d=0.02:pix_th=0.12:pic_th=0.90",
                         "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return parse_blackdetect(er)


def flash_frames(ts, ys, win=8, ratio=0.45, floor=30):
    """앞뒤보다 갑자기 어두운 프레임(번쩍임) → [(시각, 밝기, 앞뒤 밝기)].
    앞 win 프레임과 뒤 win 프레임 밝기 중앙값 중 작은 쪽의 ratio 배보다 어두우면 잡는다 — 밤 장면으로 넘어가는 컷은 뒤가 어두워서 걸리지 않는다."""
    hits = []
    for i, y in enumerate(ys):
        before, after = ys[max(0, i - win):i], ys[i + 1:i + 1 + win]
        if not before or not after:
            continue
        ctx = min(statistics.median(before), statistics.median(after))
        if ctx > floor and y < ctx * ratio:
            hits.append((round(ts[i], 3), round(y, 1), round(ctx, 1)))
    return hits


def dark_flashes(video):
    """완성본 프레임마다 평균 밝기(YAVG)를 재서 flash_frames 로 번쩍임을 찾는다."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stdout
    ts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", out)]
    ys = [float(x) for x in re.findall(r"YAVG=([\d.]+)", out)]
    return flash_frames(ts, ys)


def band_ratios(video, skip_tail=3.0, step=0.5, w=270, h=480):
    """프레임마다 아래 띠(높이 86~97%) 선명도 ÷ 가운데 띠(40~60%) 선명도. 끝 화면(skip_tail 초)은 뺀다.
    11/01 운영자 "화면이 꽉 차지 않고 가로형인가 다른 형태" — Seedance 가 프롬프트의 '가운데 띠에 모아라'를 가로 띠 영상 + 위아래 흐린 채움으로
    그렸다(11/01 5가지 편 20초 중 17초). 흐린 채움은 아래 띠가 가운데의 0.1배 안팎, 꽉 찬 영상(운영자 앱 H PICK 4편·10/31·11/01 편)은 0.26~0.48."""
    import numpy as np
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                               capture_output=True, text=True).stdout or 0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-t", f"{max(dur - skip_tail, 1):.2f}",
                          "-vf", f"fps={1 / step},scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (w * h)
    frames = np.frombuffer(raw[:n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32)
    out = []
    for f in frames:
        rows = (np.abs(np.diff(f, axis=1))[:-1, :] + np.abs(np.diff(f, axis=0))[:, :-1]).mean(1)
        mid = float(np.median(rows[int(.40 * h):int(.60 * h)]))
        out.append(float(np.median(rows[int(.86 * h):int(.97 * h)])) / (mid + 1e-6))
    return out


def letterboxed(ratios, low=0.2, share=0.6, med=0.18):
    """흐린 위아래 띠(가로 띠 영상)인가 — 프레임 share 이상이 low 아래이고 중앙값도 med 아래일 때. 얕은 초점으로 바닥이 흐린 장면 몇 개로는 걸리지 않는다."""
    if not ratios:
        return False
    return sum(r < low for r in ratios) / len(ratios) >= share and statistics.median(ratios) < med


def dropouts(video, head=0.3, tail=0.8):
    """소리 끊김 — 50ms 창 음량(dBFS)이 (가) -32 아래로 150ms 넘게 있거나 (나) 앞뒤 1초 중앙값보다 18dB 넘게 100ms 넘게 꺼지면 끊김.
    11/01 운영자 "소리가 중간중간 끊기는 것 같다": 10/31 편은 '정적' 구간이 -45~-52dB 로 0.6초, 대사 사이가 -36dB 로 꺼졌다.
    처음 head 초와 끝 tail 초(페이드)는 뺀다. → [(시작초, 길이초, 가장 낮은 dB)]"""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    win = 2400   # 50ms
    n = len(x) // win
    if n == 0:
        return []
    db = 20 * np.log10(np.sqrt((x[:n * win].reshape(n, win).astype(np.float64) ** 2).mean(1) + 1e-12))
    med = np.array([np.median(db[max(0, i - 10):i + 11]) for i in range(n)])
    lo, t_max = int(head / 0.05), n - int(tail / 0.05)
    out = []
    for mask, need in ((db < -32, 3), (db < med - 18, 2)):   # 150ms·100ms
        s0 = None
        for i in range(lo, t_max + 1):
            on = i < t_max and mask[i]
            if on and s0 is None:
                s0 = i
            if not on and s0 is not None:
                if i - s0 >= need:
                    out.append((round(s0 * 0.05, 2), round((i - s0) * 0.05, 2), round(float(db[s0:i].min()), 1)))
                s0 = None
    out.sort()
    merged = []
    for g in out:   # 두 기준이 같은 곳을 잡으면 하나로
        if merged and g[0] <= merged[-1][0] + merged[-1][1]:
            a0, l0, m0 = merged[-1]
            merged[-1] = (a0, round(max(a0 + l0, g[0] + g[1]) - a0, 2), min(m0, g[2]))
        else:
            merged.append(g)
    return merged


# ── 말로 읽는 숫자(대사) — 11/01 Codex: 자막이 맞아도 목소리가 '일조 칠천억'이라 말하면 막아야 한다 ──
_SINO = {"영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_SMALL = {"십": 10, "백": 100, "천": 1000}
_BIG = {"만": 10 ** 4, "억": 10 ** 8, "조": 10 ** 12}
_PIECE = r"\d[\d,]*(?:\.\d+)?|[영공일이삼사오육칠팔구십백천만억조점]"
SPOKEN = re.compile(rf"(?<![가-힣\d.])((?:{_PIECE})(?:\s?(?:{_PIECE}))*)\s?(?:여\s?)?(퍼센트\s?포인트|%p|퍼센트|%|거래일|시간|원|분|명|건|개|배|호|위|년|월|일|시|초|대|종목|가지|군데|곳|번|살|달|채)?")
# 퍼센트(%)와 퍼센트포인트(%p)는 다른 단위다 — 금리 '2.1%p 우대'를 '2.1%'로 쓰면 막는다(11/01 Codex)
UNIT_SAME = {"퍼센트": "%", "퍼센트포인트": "%p", "퍼센트 포인트": "%p", "%포인트": "%p"}
# 브랜드 고정 말(발송 시각 '여덟 시 반' = 08:30) — content 숫자가 아니어도 된다
BRAND_SPOKEN = {(8.0, "시"), (8.0, ""), (30.0, "분"), (30.0, "")}


def korean_number(run):
    """'일조 육천억'·'1조 6천억'·'삼 점 사팔'·'십일'·'5599.42' → 숫자. 읽을 수 없으면 None."""
    total, section, cur, frac = 0.0, 0.0, None, None
    for tok in re.findall(_PIECE, run):
        if tok[0].isdigit():
            cur, frac = float(tok.replace(",", "")), None
        elif tok == "점":
            frac = ""
        elif tok in _SINO:
            if frac is not None:
                frac += str(_SINO[tok])
            else:
                cur = float(_SINO[tok])
        elif tok in _SMALL:
            section += (cur if cur is not None else 1) * _SMALL[tok]
            cur, frac = None, None
        elif tok in _BIG:
            section += cur or 0
            total += (section or 1) * _BIG[tok]
            section, cur, frac = 0.0, None, None
        if frac:
            cur = float(int(cur or 0)) + float("0." + frac)
    value = total + section + (cur or 0)
    return value if (total or section or cur is not None) else None


def _sign_near(text, start, end, words=True):
    """숫자 앞 부호 말(마이너스·플러스·-·+·▲·▼) 또는 (words 면) 뒤 방향 말(내린·빠졌·오른·상승·하락 …) → '-'·'+'·''."""
    before = re.search(r"(마이너스|플러스|[+\-−▲▼])\s?$", text[max(0, start - 6):start])
    if before:
        return "-" if before.group(1) in ("마이너스", "-", "−", "▼") else "+"
    if not words:
        return ""
    tail = text[end:end + 12]
    if re.match(rf"\s*(?:\S{{1,3}}\s+)?(?:{DOWN})", tail):
        return "-"
    if re.match(rf"\s*(?:\S{{1,3}}\s+)?(?:{UP})", tail):
        return "+"
    return ""


_NATIVE_TENS = {"열": 10, "스물": 20, "스무": 20, "서른": 30, "마흔": 40}
_NATIVE_ONES = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "석": 3, "네": 4, "넷": 4, "넉": 4,
                "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
COUNTERS = "종목|가지|군데|시간|개|명|곳|번|살|달|건|장|채|대|마리|권|잔|병|시|주|해"
NATIVE = re.compile(rf"(?<![가-힣])(?:({'|'.join(_NATIVE_TENS)})\s?)?({'|'.join(sorted(_NATIVE_ONES, key=len, reverse=True))})?\s?({COUNTERS})"
                    r"(?=$|[^가-힣]|[에을를이가은는도의로째씩만])")


def native_numbers(text):
    """고유어 수사 + 세는 말 — '두 종목'·'세 곳'·'열두 개'·'여덟 시' → [(위치, (값, 세는 말, 부호))] (11/01 Codex: '두 종목'을 '세 종목'으로 말하면 막는다)."""
    out = []
    for m in NATIVE.finditer(text):
        tens, ones, unit = m.group(1), m.group(2), m.group(3)
        if not tens and not ones:
            continue
        v = float(_NATIVE_TENS.get(tens, 0) + _NATIVE_ONES.get(ones, 0))
        out.append((m.start(), (v, unit, _sign_near(text, m.start(), m.end(), words=False))))
    return out


def spoken_numbers(text):
    """대사·받아쓴 글에서 숫자 → [(값, 단위, 부호)]. 한글 수사만 있는 덩어리는 단위가 붙을 때만 숫자로 본다('사이드카'·'하루 만에'는 숫자가 아니다).
    부호는 앞의 '마이너스·플러스'나 뒤의 '빠졌다·올랐다' 같은 말에서 — 목소리가 등락을 뒤집어 말하면 막는다(11/01 Codex)."""
    out = []
    for m in SPOKEN.finditer(text):
        run, unit = m.group(1).strip(), m.group(2) or ""
        # 날짜·기간의 '일'은 단위다(11/01 Codex): '30일' → 30 일, '삼십 일' → 30 일, '삼십일 일' → 31 일. 붙여 쓴 '삼십일'은 31(단위 없음)
        if not unit and run.endswith("일") and len(run) > 1 and (re.search(r"\d", run[:-1]) or run[:-1].endswith(" ")):
            run, unit = run[:-1].strip(), "일"
        if not re.search(r"\d", run) and not unit:
            continue
        if re.fullmatch(r"[점\s]+", run):
            continue
        v = korean_number(run)
        if v is not None:
            u = UNIT_SAME.get(unit, unit)   # 방향 말(빠졌다·올랐다)은 등락률(%)에만 — 지수·금액 수준에 붙은 말로 잘못 막지 않게
            out.append((m.start(), (round(v, 6), u, _sign_near(text, m.start(), m.end(), words=(u == "%")))))
    return [n for _, n in sorted(out + native_numbers(text), key=lambda x: x[0])]


def _num_match(a, b, strict=False):
    """값·단위·부호 — 단위나 부호는 둘 다 있을 때만 같아야 한다. strict(content 와 대조할 때)면 a 에 부호·단위가 있을 때 b 도 같아야 한다."""
    va, ua, sa = (tuple(a) + ("",))[:3]
    vb, ub, sb = (tuple(b) + ("",))[:3]
    if (ua and ub and ua != ub) or (sa and sb and sa != sb) or (strict and sa and sa != sb):
        return False
    if strict and ua and ua != ub:   # 화면·대사에 단위(%·원·종목 …)가 있으면 content 도 같은 단위 — 날짜의 맨숫자 31 로 '31%'가 통과하면 안 된다(11/01 Codex)
        return False
    if abs(va - vb) <= 1e-6 * max(1.0, abs(vb)):
        return True
    # 단위 없는 맨숫자 5599 ↔ 5599.42 (% 수와는 아니다, '12거래일'처럼 단위가 붙은 수는 정확히 같아야 한다)
    return not ua and float(va).is_integer() and int(va) == int(vb) and not {"%", "%p"} & {ua, ub} and not float(vb).is_integer()


def content_values(corpus):
    """content 의 숫자 → [(값, 단위, 부호)] — 단위는 숫자 뒤 마지막 단위(1조6000억원 → 원), 부호는 화면 숫자 검사와 같은 규칙(corpus_numbers)."""
    out = []
    for body, signs in corpus_numbers(corpus).items():
        unit = re.sub(r"^[\d.,조억만천백]+", "", body)
        v = korean_number(body[: len(body) - len(unit)] if unit else body)
        if v is not None:
            out += [(round(v, 6), UNIT_SAME.get(unit, unit), sg) for sg in signs]
    return out + [n for _, n in native_numbers(corpus)]   # '반도체 두 종목' 같은 고유어 수사


def _say(n):
    return f"{n[2] if len(n) > 2 else ''}{n[0]:g}{n[1]}"


def check_spoken(script_nums, said, allow=()):
    """들린 숫자 ↔ 대사 숫자 — 목소리가 다른 금액·반대 방향을 말했거나(들린 숫자가 대사에 없음) 숫자를 빼먹었으면 실패. → (들린 숫자, 실패 목록)
    allow: 이 영상에서 content 숫자가 아닌 고정 표현 (값, 단위) — 예: '5가지' 브리핑의 (5.0, '가지')."""
    skip = set(BRAND_SPOKEN) | set(allow)
    heard_nums, bad = spoken_numbers(said), []
    for h in heard_nums:
        if h[:2] not in skip and not any(_num_match(h, x) for x in script_nums):
            bad.append(f"목소리 숫자 — 들린 '{_say(h)}' 가 대사에 없다(받아쓰기: {said.strip()[:60]})")
    for x in script_nums:
        if x[:2] not in skip and not any(_num_match(h, x) for h in heard_nums):
            bad.append(f"목소리 숫자 — 대사의 '{_say(x)}' 가 들리지 않는다(받아쓰기: {said.strip()[:60]})")
    return heard_nums, bad


def hangul(s):
    return re.sub(r"[^가-힣]", "", s)


# 11/01 운영자 "패턴이 똑같네? 헉으로 시작하고 멘트가 비슷한 거 아니야?" — 그날 릴스 6편이 모두 '헉…'으로 열고 '~해 보자!'·'그래서 나는?'·같은 끝인사로 닫았다.
# 2026-11-02 부터 릴스마다 훅 종류(hook)를 적고, 같은 날 다른 릴스와 겹치지 않게 한다. 목록·예시는 reviews/2026-11-01-ai-video.md '같은 틀 반복 금지'.
HOOK_RULE_FROM = "2026-11-02"
HOOK_KINDS = ("숫자 먼저", "질문", "반전", "상황", "할 일 먼저", "비교", "대화")


def first_word(ep):
    """첫 대사의 첫 마디('헉… 인텔이' → '헉')."""
    text = ((ep.get("voices") or [{}])[0]).get("text", "")
    m = re.match(r"\s*([^\s,.!?…~]+)", text)
    return m.group(1) if m else ""


def closing_kick(ep):
    """마지막 자막의 머리말(kick) — '그래서 나는?' 같은 것."""
    caps = ep.get("captions") or []
    m = re.search(r'class="kick">(.*?)</div>', caps[-1]["html"]) if caps else None
    return plain(m.group(1)) if m else ""


def sign_off(ep):
    """끝인사(마지막 대사) 원고."""
    voices = ep.get("voices") or []
    return voices[-1].get("text", "").strip() if len(voices) > 1 else ""


def pattern_repeats(epath, ep):
    """같은 날(첫 마디는 전날까지) 다른 릴스와 같은 틀이면 → 실패 목록. 2026-11-02 전 회차는 검사하지 않는다(기록)."""
    if ep.get("date", "") < HOOK_RULE_FROM:
        return []
    fails = []
    if ep.get("hook") not in HOOK_KINDS:
        fails.append(f"hook(훅 종류)이 없거나 목록 밖이다: {ep.get('hook')!r} — {', '.join(HOOK_KINDS)} 중 하나, 같은 날 다른 릴스와 다르게")
    day = dt.date.fromisoformat(ep["date"])
    for d in (day, day - dt.timedelta(days=1)):
        folder = epath.parent.parent / d.isoformat()
        for p in sorted(folder.glob("*.json")):   # episode·extraN·brief 등 그날 릴스 설정 전부(11/01 Codex: brief.json 이 빠졌다)
            if p.resolve() == epath.resolve():
                continue
            try:
                other = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if not isinstance(other, dict) or "voices" not in other:
                continue
            name = f"{d.isoformat()} {p.stem}"
            if first_word(ep) and first_word(ep) == first_word(other):
                fails.append(f"첫 마디 '{first_word(ep)}'가 {name} 와 같다 — 훅을 돌려쓴다")
            if d != day:
                continue
            if ep.get("hook") and ep.get("hook") == other.get("hook"):
                fails.append(f"훅 종류 '{ep['hook']}'가 같은 날 {name} 와 같다")
            if closing_kick(ep) and closing_kick(ep) == closing_kick(other):
                fails.append(f"끝 자막 머리말 '{closing_kick(ep)}'가 같은 날 {name} 와 같다")
            if sign_off(ep) and sign_off(ep) == sign_off(other):
                fails.append(f"끝인사 '{sign_off(ep)[:16]}…'가 같은 날 {name} 와 같다")
    return fails


def covered_item(ep, content):
    """릴스가 다루는 content 항목 — 설정의 "item" 이 big_issue 나 items 의 tag 와 같아야 한다(11/01 Codex: 출처는 그 이슈의 기사와 대조)."""
    tag = (ep.get("item") or "").strip()
    if not tag:
        return None
    big = content.get("big_issue") or {}
    if big.get("tag") == tag:
        return big
    return next((it for it in content.get("items") or [] if it.get("tag") == tag), None)


def brief_series(ep):
    """'오늘 아침 5가지' 브리핑이면 그 숫자 표현(화면 '5가지'·목소리 '다섯 가지')은 content 숫자가 아니다 → (화면 allow, 목소리 allow)."""
    items = ep.get("items") if isinstance(ep.get("items"), list) else []
    if not items:
        return set(), set()
    n = len(items)
    return {f"{n}가지", f"{n}개"}, {(float(n), "가지"), (float(n), "개")}


def brief_source_gaps(ep, content, caption):
    """'오늘 아침 5가지'(2026-11-01 운영자 '메인 5개를 20초 한 편에') — 이슈마다 그 이슈의 원 기사 매체 2곳이 캡션 '출처:' 줄의 한 칸(/ 로 나눔)에 있어야 한다.
    끝 화면에는 10곳을 다 못 쓰니 note 에 '출처'(캡션·뉴스레터에 있다는 말)만 있으면 된다."""
    tags = [str(t).strip() for t in ep.get("items") or []]
    if len(tags) < 2:
        return [f"items(다루는 이슈 tag 목록)가 2개 미만이다: {tags}"]
    fails = []
    note = plain(str((ep.get("end_card") or {}).get("note") or ""))
    if "출처" not in note:
        fails.append("끝 화면 note 에 출처 안내가 없다 — 예: '출처는 캡션·뉴스레터에'")
    src_line = next((ln for ln in caption.splitlines() if ln.strip().startswith("출처")), "")
    cells = [c for c in re.split(r"\s*/\s*", src_line.split(":", 1)[-1]) if c.strip()]
    # 칸은 영상 순서(items 순서)대로 이슈 하나씩 — 칸과 이슈를 순서로 짝지어야 두 이슈의 매체 묶음을 바꿔 적은 것도 잡는다(11/01 Codex)
    if len(cells) != len(tags):
        fails.append(f"reel_ai_caption.txt '출처:' 줄 칸 {len(cells)}개 ≠ 이슈 {len(tags)}개 — 영상 순서대로 이슈마다 한 칸(' / ' 로 나눔)")
    per_item = []
    for tag in tags:
        item = covered_item({"item": tag}, content)
        if item is None:
            fails.append(f"items 의 '{tag}' 가 content(big_issue·items 의 tag)에 없다")
            per_item.append(None)
            continue
        names = {s.get("name") for s in item.get("sources") or [] if s.get("name")}
        if len(names) < 2:
            fails.append(f"이슈 '{tag}' 의 출처가 content 에 2곳 미만이다 — 이 이슈는 브리핑에 넣지 않는다")
        per_item.append(names)
    known = set().union(*[n for n in per_item if n])
    for i, (tag, names) in enumerate(zip(tags, per_item)):
        if not names or len(names) < 2:
            continue
        cell = cells[i] if i < len(cells) else ""
        if sum(n in cell for n in names) < 2:
            fails.append(f"'출처:' {i + 1}번째 칸에 '{tag}' 의 매체 2곳({'·'.join(sorted(names))} 중)이 없다")
        stray = sorted(n for n in known - names if n in cell)
        if stray:
            fails.append(f"'출처:' {i + 1}번째 칸('{tag}')에 다른 이슈의 매체 {'·'.join(stray)} 가 있다")
    return fails


def source_gaps(ep, content, caption):
    """기사·출처 맞춤(11/02~) — 그 릴스가 다루는 이슈(item)의 원 기사 매체 2곳 이상을 sources 에 적고, 그 매체가 끝 화면·캡션 '출처' 줄에 다 있나 → 실패 목록.
    11/01 운영자 "기사 및 소스에 맞춰서 진행해 달라": 대본은 그 이슈의 원 기사(read_article.py)를 읽고 쓴다 — 기사에 없는 말·한 곳에만 있는 사실은 쓰지 않는다.
    매체는 그날 content 전체가 아니라 그 이슈의 sources 안에서만 인정한다(11/01 Codex: 다른 이슈의 매체를 적어도 통과하면 안 된다)."""
    if ep.get("date", "") < HOOK_RULE_FROM:
        return []
    if isinstance(ep.get("items"), list):
        return brief_source_gaps(ep, content, caption)
    item = covered_item(ep, content)
    if item is None:
        return [f"item(다루는 이슈의 tag)이 없거나 content 에 없다: {ep.get('item')!r} — big_issue·items 의 tag 그대로"]
    names = [n.strip() for n in ep.get("sources") or [] if n.strip()]
    if len(set(names)) < 2:
        return [f"sources 에 원 기사 매체가 2곳 이상 없다: {names} — 그 이슈의 원 기사를 read_article.py 로 읽고 적는다"]
    allowed = {s.get("name") for s in item.get("sources") or []}
    note = plain(str((ep.get("end_card") or {}).get("note") or ""))
    src_line = next((ln for ln in caption.splitlines() if ln.strip().startswith("출처")), "")
    fails = []
    for n in names:
        if n not in allowed:
            fails.append(f"출처 '{n}' 이 이 이슈('{item.get('tag')}')의 sources({'·'.join(sorted(a for a in allowed if a))})에 없다 — 그 이슈를 확인한 기사만")
        if n not in note:
            fails.append(f"끝 화면 note 에 출처 '{n}' 이 없다")
        if n not in src_line:
            fails.append(f"reel_ai_caption.txt '출처' 줄에 '{n}' 이 없다")
    return fails

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--no-asr", action="store_true")
    ap.add_argument("--video", help="instagram/{날짜}/reel_ai.mp4 대신 볼 영상(고쳐 본 판)")
    ap.add_argument("--extra", type=int, help="메인 N번 AI 영상(instagram/{날짜}/extra/N/) — 운영자가 앱에서 만든 영상, 만화는 없다")
    a = ap.parse_args()
    epath = Path(a.episode).resolve()
    ep = json.loads(epath.read_text(encoding="utf-8"))
    day = ep["date"]
    folder = ROOT / "instagram" / day / ("extra/%d" % a.extra if a.extra else "")
    content = json.loads((ROOT / "content" / f"{day}.json").read_text(encoding="utf-8"))
    corpus = json.dumps(content, ensure_ascii=False)
    # 출처 날짜(MM.DD)는 화면에서 'M월 D일'로 쓴다 — 그 형태도 확인된 것으로 본다
    for mm, dd in set(re.findall(r'"date":\s*"(\d{1,2})\.(\d{1,2})"', corpus)):
        corpus += f" {int(mm)}월 {int(dd)}일 {int(dd)}일"
    fails, notes = [], []

    # 1·5 숫자 대조
    texts = [(f"자막 {i + 1}", plain(c["html"])) for i, c in enumerate(ep.get("captions", []))]
    if ep.get("comic"):   # card=N 컷(5가지 웹툰, 11/02~)은 그날 카드 글로 채운 뒤 같은 숫자 검사를 받는다
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import comic as comic_mod
        comic_mod.from_cards(ep["comic"], day)
    for i, p in enumerate((ep.get("comic") or {}).get("panels", []), 1):
        texts += [(f"만화 {i} 말풍선", plain(p.get("bubble", ""))), (f"만화 {i} 설명", plain(p.get("box", "")))]
        texts += [(f"만화 {i} {k}", plain(p[k])) for k, _ in (("body", 0), ("take", 0)) if p.get(k)]
        if p.get("number"):   # 두 컷 장(웹툰 3판)의 숫자 스티커 — 손으로 바꿔 쓴 값도 content 숫자여야 한다(기본은 카드 number)
            texts.append((f"만화 {i} 숫자 스티커", plain(str(p["number"]))))
    if ep.get("comic"):
        texts.append(("만화 제목", plain(ep["comic"]["title"])))
    if not (folder / "reel_ai_caption.txt").exists():
        # 없으면 게시 코드가 reel_caption.txt·caption.txt 로 대신 만든다 — 그건 이 검수가 보지 않으므로 반드시 쓴다(11/01 Codex)
        fails.append("reel_ai_caption.txt 가 없다 — AI 릴스 캡션은 따로 써서 검수한다(대체 캡션은 검수 밖)")
    for name in ("reel_ai_caption.txt", "comic_caption.txt"):
        p = folder / name
        if p.exists():
            body = "\n".join(x for x in p.read_text(encoding="utf-8").splitlines() if not x.startswith("#"))
            texts.append((name, body))
            if "AI로 만들" not in body:
                fails.append(f"{name}: 'AI로 만들었어요' 한 줄이 없다")
            tags = re.findall(r"#\S+", p.read_text(encoding="utf-8"))
            if len(tags) > 5:
                fails.append(f"{name}: 해시태그 {len(tags)}개(5개 이하)")
    series_screen, series_spoken = brief_series(ep)
    bad = check_numbers(texts, corpus, allow=series_screen)
    # 끝 화면(영상)·만화 끝 장도 화면에 나간다(11/01 Codex) — 고정 문구 숫자(8시 30분·2030)만 예외
    ends = [(f"끝 화면 {k}", plain(str((ep.get("end_card") or {}).get(k) or ""))) for k in ("line", "sub", "note")]
    ends += [(f"만화 끝 장 {k}", plain(str(((ep.get("comic") or {}).get("end") or {}).get(k) or ""))) for k in ("title", "sub")]
    bad += check_numbers([x for x in ends if x[1]], corpus, allow=BRAND_TOKENS)
    fails += [f"content 에 없는 숫자 — {b}" for b in bad]
    # 대사 원고의 숫자(한글 읽기)도 content 와 같은 값이어야 한다
    cvals = content_values(corpus)
    script_nums = []
    for vline in ep.get("voices", []):
        for sn in spoken_numbers(vline.get("text", "")):
            script_nums.append(sn)
            if sn[1] in COUNTERS.split("|") and sn[0] == 1:   # '한 번·한 달' 같은 관용구는 content 와 대조하지 않는다(받아쓰기 대조는 한다)
                continue
            if sn[:2] not in BRAND_SPOKEN and sn[:2] not in series_spoken and not any(_num_match(sn, c, strict=True) for c in cvals):
                fails.append(f"content 에 없는 숫자 — 대사 '{vline.get('text', '')[:20]}…': {_say(sn)}")
    fails += pattern_repeats(epath, ep)
    cap_path = folder / "reel_ai_caption.txt"
    fails += source_gaps(ep, content, cap_path.read_text(encoding="utf-8") if cap_path.exists() else "")
    if any("AI로 만든 영상" in plain(c["html"]) for c in ep.get("captions", [])):
        fails.append("화면 글자에 'AI로 만든 영상' 표시가 있다(운영자 11/01: 빼기)")

    # 3·4 영상·소리
    video = Path(a.video) if a.video else folder / "reel_ai.mp4"
    if not video.exists():
        fails.append("instagram/{}/reel_ai.mp4 가 없다".format(day))
    else:
        pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                        "-of", "json", str(video)], capture_output=True, text=True).stdout)
        v = next((s for s in pr["streams"] if s["codec_type"] == "video"), {})
        dur = float(pr["format"]["duration"])
        if (v.get("width"), v.get("height")) != (1080, 1920):
            fails.append(f"영상 크기 {v.get('width')}×{v.get('height')}(1080×1920 이어야)")
        if not 8 <= dur <= 30:
            fails.append(f"영상 길이 {dur:.1f}초(8~30초)")
        if not any(s["codec_type"] == "audio" for s in pr["streams"]):
            fails.append("음성 트랙이 없다")
        er = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", er)
        lufs = float(m[-1]) if m else None
        if lufs is None or abs(lufs + 14) > 1.5:
            fails.append(f"음량 {lufs} LUFS(-14±1.5)")
        notes.append(f"영상 {dur:.1f}초 · {lufs} LUFS")
        blacks = black_frames(video)
        if blacks:
            fails.append("검은 화면 " + ", ".join(f"{a:.2f}~{b:.2f}초" for a, b in blacks)
                         + " — 끝 화면은 겹쳐 넘기고(episode.py XFADE), 원본 영상의 검은 컷은 trim 으로 잘라 낸다")
        flashes = dark_flashes(video)
        if flashes:
            fails.append("어둡게 번쩍이는 프레임 " + ", ".join(f"{t:.2f}초(밝기 {y}, 앞뒤 {c})" for t, y, c in flashes[:6]))
        notes.append(f"검은 화면 {len(blacks)}곳 · 번쩍임 {len(flashes)}곳")
        ratios = band_ratios(video, skip_tail=float(ep.get("end_seconds") or 2.5) + 0.5)
        if ratios:
            notes.append(f"아래 띠 선명도 중앙값 {statistics.median(ratios):.2f}(가운데 대비) · 흐린 띠 프레임 {sum(r < 0.2 for r in ratios) / len(ratios):.0%}")
        if letterboxed(ratios):
            fails.append("화면이 꽉 차지 않는다 — 위아래가 흐린 띠인 가로 띠 영상(11/01 운영자 'H PICK 처럼 꽉 차게'). "
                         "프롬프트에 'FULL-BLEED VERTICAL FRAMING'·NEGATIVE 'no letterboxing, no blurred bars' 를 넣어 다시 만든다(brief_prompt.txt)")
        gaps = dropouts(video)
        if gaps:
            fails.append("소리 끊김 " + ", ".join(f"{a:.2f}초부터 {b:.2f}초({m}dB)" for a, b, m in gaps)
                         + " — 곡 사이를 비우지 말고 낮게 깔기·덕킹 약하게(episode.json music·duck)")

        # 2 대사
        if not a.no_asr and ep.get("voices"):
            from faster_whisper import WhisperModel
            segs, _ = WhisperModel("small", device="cpu", compute_type="int8").transcribe(str(video), language="ko", beam_size=5)
            said = " ".join(s.text for s in segs)
            heard = hangul(said)
            heard_nums, bad_nums = check_spoken(script_nums, said, allow=series_spoken)
            fails += bad_nums
            notes.append(f"들린 숫자 {', '.join(_say(n) for n in heard_nums) or '없음'}")
            for vline in ep["voices"]:
                want = hangul(re.sub(r"[일이삼사오육칠팔구십백천만억조점퍼센트]+(?=\s|$|[,.!?…])", "", vline.get("text", "")))
                if len(want) < 4:
                    continue
                sm = difflib.SequenceMatcher(None, want, heard)
                got = sum(b.size for b in sm.get_matching_blocks()) / len(want)
                (notes if got >= 0.6 else fails).append(f"대사 '{vline.get('text', '')[:24]}…' 들림 {got:.0%}")

    # 6 만화
    comic = sorted((folder / "comic").glob("c*.jpg"))
    if ep.get("comic"):
        if not 3 <= len(comic) <= 10:
            fails.append(f"만화 {len(comic)}장(3~10장)")
        for c in comic:
            pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "json", str(c)],
                                           capture_output=True, text=True).stdout)["streams"][0]
            if (pr["width"], pr["height"]) != (1080, 1350):
                fails.append(f"{c.name} 크기 {pr['width']}×{pr['height']}")
        if not (folder / "comic_caption.txt").exists():
            fails.append("comic_caption.txt 가 없다")

    for n in notes:
        print("  ·", n)
    if fails:
        print("✗ 검수 실패 — 올리지 않는다")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print(f"✓ 검수 통과 ({day}) — 프레임 캡처로 실존 인물·로고·글자 깨짐을 한 번 더 본 뒤 올린다")


if __name__ == "__main__":
    main()
