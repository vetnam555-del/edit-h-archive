#!/usr/bin/env python3
"""AI 릴스·H 극장 만화 검수 — 올리기 전에 반드시 돌린다(2026-11-01 운영자 "검수도 잘해주고").

사용: python3 automation/pilots/ai_reel/qa.py <episode.json> [--no-asr]
검사(하나라도 ✗ 면 올리지 않는다):
 1. 숫자 대조 — 화면 글자·말풍선·설명·캡션에 나온 숫자가 그날 content/{날짜}.json 에 그대로 있나(확인된 숫자만).
 2. 대사 — 완성본을 음성 인식(faster-whisper small)으로 받아 적어, 대사 줄마다 낱말이 충분히 들리나.
 3. 소리 — 통합 음량 -14±1.5 LUFS, 음성 트랙이 있다.
 4. 영상 — 1080×1920, 길이 8~30초.
 5. 캡션 — reel_ai_caption.txt·comic_caption.txt 에 'AI로 만들' 한 줄, 해시태그 5개 이하, 같은 숫자 대조.
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
# 큰 금액은 한 덩어리로 — "1조6000억원"을 "1조"·"6000억"으로 쪼개 따로 찾으면 content 가 "1조5000억원과 6000억원"일 때도 통과한다(11/01 Codex)
# 등락 부호도 숫자의 일부 — "+7.08%"가 content 의 "-7.08%"로 통과하면 안 된다(11/01 Codex). 낱말 사이 '-'(2026-11-01)는 부호가 아니다
NUM = re.compile(r"(?:(?<![\w.])[+\-−▲▼]\s?)?\d[\d,]*(?:\.\d+)?(?:\s*(?:조|억|만)\s*\d[\d,]*(?:\.\d+)?)*\s*(?:조|억|만)?\s*"
                 r"(?:%|원|명|건|분|초|시|일|개|배|p|bp|달러|위|호|거래일|년|월|평|장)?")
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


def check_numbers(texts, corpus):
    """숫자는 낱말 단위로 content 의 숫자와 맞춘다(content 전체 글자를 이어 붙여 찾으면 '5599.42, 3만 명'이 '5599.423만명'이 되어
    앞뒤 숫자가 섞인다 — 11/01). 단위가 있으면 content 에 같은 덩어리가 있어야 한다('1조7000억원'·'1조'는 '1조6000억원'으로 통과 못 함,
    '6000억'은 '6000억원'으로 통과). 단위 없는 맨숫자는 같은 수이거나 그 수의 소수(5599 ↔ 5599.42)면 통과, % 수와는 맞추지 않는다.
    부호: 화면 숫자에 +·-가 있으면 content 의 같은 수도 그 부호여야 한다('-7.08%' 또는 '7.08% 내린'). 부호 없는 화면 숫자는 따지지 않는다."""
    have = corpus_numbers(corpus)
    signs_ok = lambda sign, got: not sign or sign in got  # noqa: E731
    bad = []
    for label, text in texts:
        for t in numbers(text):
            sign, body = (t[0], t[1:]) if t[0] in "+-" else ("", t)
            if re.fullmatch(r"[\d.]+", body):
                ok = any((m := re.match(r"[\d.]+", c)) and (m.group(0) == body or m.group(0).startswith(body + "."))
                         and not c[m.end():].startswith("%") and signs_ok(sign, got) for c, got in have.items())
            else:
                ok = any(k in have and signs_ok(sign, have[k]) for k in (body, body + "원"))
            if not ok:
                bad.append(f"{label}: '{t}'")
    return bad


def hangul(s):
    return re.sub(r"[^가-힣]", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--no-asr", action="store_true")
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
    fails += [f"content 에 없는 숫자 — {b}" for b in bad]
    if any("AI로 만든 영상" in plain(c["html"]) for c in ep.get("captions", [])):
        fails.append("화면 글자에 'AI로 만든 영상' 표시가 있다(운영자 11/01: 빼기)")

    # 3·4 영상·소리
    video = folder / "reel_ai.mp4"
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

        # 2 대사
        if not a.no_asr and ep.get("voices"):
            from faster_whisper import WhisperModel
            segs, _ = WhisperModel("small", device="cpu", compute_type="int8").transcribe(str(video), language="ko", beam_size=5)
            heard = hangul("".join(s.text for s in segs))
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
