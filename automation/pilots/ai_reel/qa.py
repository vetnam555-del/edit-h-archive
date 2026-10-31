#!/usr/bin/env python3
"""AI 릴스·H 극장 만화 검수 — 올리기 전에 반드시 돌린다(2026-11-01 운영자 "검수도 잘해주고").

사용: python3 automation/pilots/ai_reel/qa.py <episode.json> [--no-asr] [--video 다른 영상.mp4]
검사(하나라도 ✗ 면 올리지 않는다):
 1. 숫자 대조 — 화면 글자·말풍선·설명·캡션에 나온 숫자가 그날 content/{날짜}.json 에 그대로 있나(확인된 숫자만).
 2. 대사 — 완성본을 음성 인식(faster-whisper small)으로 받아 적어, 대사 줄마다 낱말이 충분히 들리나.
    대사 원고의 숫자(한글 읽기)는 content 와, 들린 숫자는 대사 숫자와 같은 값이어야 한다(11/01 Codex — 목소리가 틀린 금액을 말하면 막는다).
 3. 소리 — 통합 음량 -14±1.5 LUFS, 음성 트랙이 있다, 중간에 끊기는 곳이 없다(11/01 운영자 "소리가 중간중간 끊긴다").
 4. 영상 — 1080×1920, 길이 8~30초.
 5. 캡션 — reel_ai_caption.txt·comic_caption.txt 에 'AI로 만들' 한 줄, 해시태그 5개 이하, 같은 숫자 대조(끝 화면·만화 끝 장 문구도).
 6. 만화 — comic/ JPEG 3~10장, 1080×1350.
 7. 금지 — 화면 글자에 'AI로 만든 영상' 표시 없음(운영자 11/01), 실존 인물·회사 로고는 사람이 프레임 캡처로 한 번 더 본다(자동 아님).
"""
import argparse
import difflib
import html as htmlmod
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# 큰 금액은 한 덩어리로('3천억원'·'3백억원'·'5천6백만원'·'2만5천명'도 — 11/01 Codex) — "1조6000억원"을 "1조"·"6000억"으로 쪼개 따로 찾으면 content 가 "1조5000억원과 6000억원"일 때도 통과한다(11/01 Codex)
# 등락 부호도 숫자의 일부 — "+7.08%"가 content 의 "-7.08%"로 통과하면 안 된다(11/01 Codex). 낱말 사이 '-'(2026-11-01)는 부호가 아니다
NUM = re.compile(r"(?:(?<![\w.])[+\-−▲▼]\s?)?\d[\d,]*(?:\.\d+)?(?:\s*[조억만천백]+\s*\d[\d,]*(?:\.\d+)?)*[조억만천백]*\s*"
                 r"(?:%|원|명|건|분|초|시간|시|일|개|배|p|bp|달러|위|호|거래일|년|월|평|장|종목|가지|군데|곳|번|살|달|채|대|마리|권|잔|병)?")
SIGN = str.maketrans({"−": "-", "▲": "+", "▼": "-"})
# content 는 부호 대신 말로 쓰기도 한다 — "3.02% 내린", "3.0% 늘어", "7% 넘게 내렸어요"
DOWN = "내리|내린|내려|내렸|하락|떨어|빠진|빠졌|빠지|감소|줄어|줄었|급락|밀려|밀린|밀렸"
UP = "오른|올라|올랐|오르|상승|늘어|늘었|증가|급등|뛰었|뛴|뛰어"


def plain(s):
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def norm_num(tok):
    return re.sub(r"[\s,]", "", tok).translate(SIGN)


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
            if not sign and body.endswith(("%", "%p", "p")):
                sign = _sign_near(text, m.start(), m.end(), words=True)   # '3.48% 상승'·'빠졌다고' — 등락률만 말로 방향을 읽는다(11/01 Codex)
            unit = re.sub(r"^[\d.,조억만천백]+", "", body)
            v = korean_number(body[: len(body) - len(unit)] if unit else body)
            if v is None or not any(_num_match((round(v, 6), unit, sign), c, strict=True) for c in cvals):
                bad.append(f"{label}: '{t}'")
        # 화면의 고유어 수사 + 세는 말('반도체 세 종목') — '한 번·한 달' 같은 관용구(1)는 뺀다(11/01 Codex)
        for _, n in native_numbers(text):
            if n[0] != 1 and not any(_num_match(n, c, strict=True) for c in cvals):
                bad.append(f"{label}: '{_say(n)}'")
    return bad


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
SPOKEN = re.compile(rf"(?<![가-힣\d.])((?:{_PIECE})(?:\s?(?:{_PIECE}))*)\s?(퍼센트|%|거래일|원|분|명|건|개|배|호|위|년|월|일|시|초)?")
UNIT_SAME = {"퍼센트": "%"}
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
    return not ua and float(va).is_integer() and int(va) == int(vb) and "%" not in (ua, ub) and not float(vb).is_integer()


def content_values(corpus):
    """content 의 숫자 → [(값, 단위, 부호)] — 단위는 숫자 뒤 마지막 단위(1조6000억원 → 원), 부호는 화면 숫자 검사와 같은 규칙(corpus_numbers)."""
    out = []
    for body, signs in corpus_numbers(corpus).items():
        unit = re.sub(r"^[\d.,조억만천백]+", "", body)
        v = korean_number(body[: len(body) - len(unit)] if unit else body)
        if v is not None:
            out += [(round(v, 6), unit, sg) for sg in signs]
    return out + [n for _, n in native_numbers(corpus)]   # '반도체 두 종목' 같은 고유어 수사


def _say(n):
    return f"{n[2] if len(n) > 2 else ''}{n[0]:g}{n[1]}"


def check_spoken(script_nums, said):
    """들린 숫자 ↔ 대사 숫자 — 목소리가 다른 금액·반대 방향을 말했거나(들린 숫자가 대사에 없음) 숫자를 빼먹었으면 실패. → (들린 숫자, 실패 목록)"""
    heard_nums, bad = spoken_numbers(said), []
    for h in heard_nums:
        if h[:2] not in BRAND_SPOKEN and not any(_num_match(h, x) for x in script_nums):
            bad.append(f"목소리 숫자 — 들린 '{_say(h)}' 가 대사에 없다(받아쓰기: {said.strip()[:60]})")
    for x in script_nums:
        if x[:2] not in BRAND_SPOKEN and not any(_num_match(h, x) for h in heard_nums):
            bad.append(f"목소리 숫자 — 대사의 '{_say(x)}' 가 들리지 않는다(받아쓰기: {said.strip()[:60]})")
    return heard_nums, bad


def hangul(s):
    return re.sub(r"[^가-힣]", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--no-asr", action="store_true")
    ap.add_argument("--video", help="instagram/{날짜}/reel_ai.mp4 대신 볼 영상(고쳐 본 판)")
    a = ap.parse_args()
    epath = Path(a.episode).resolve()
    ep = json.loads(epath.read_text(encoding="utf-8"))
    day = ep["date"]
    folder = ROOT / "instagram" / day
    content = json.loads((ROOT / "content" / f"{day}.json").read_text(encoding="utf-8"))
    corpus = json.dumps(content, ensure_ascii=False)
    # 출처 날짜(MM.DD)는 화면에서 'M월 D일'로 쓴다 — 그 형태도 확인된 것으로 본다
    for mm, dd in set(re.findall(r'"date":\s*"(\d{1,2})\.(\d{1,2})"', corpus)):
        corpus += f" {int(mm)}월 {int(dd)}일 {int(dd)}일"
    fails, notes = [], []

    # 1·5 숫자 대조
    texts = [(f"자막 {i + 1}", plain(c["html"])) for i, c in enumerate(ep.get("captions", []))]
    for i, p in enumerate((ep.get("comic") or {}).get("panels", []), 1):
        texts += [(f"만화 {i} 말풍선", plain(p["bubble"])), (f"만화 {i} 설명", plain(p.get("box", "")))]
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
    bad = check_numbers(texts, corpus)
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
            if sn[:2] not in BRAND_SPOKEN and not any(_num_match(sn, c, strict=True) for c in cvals):
                fails.append(f"content 에 없는 숫자 — 대사 '{vline.get('text', '')[:20]}…': {_say(sn)}")
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
            heard_nums, bad_nums = check_spoken(script_nums, said)
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
