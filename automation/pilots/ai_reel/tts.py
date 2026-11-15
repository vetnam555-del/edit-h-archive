#!/usr/bin/env python3
"""AI 릴스 대사 녹음 — 무료 edge-tts 로 만든다(2026-11-15, 힉스필드 대체).

2026-11-14 운영자 "앞으로는 힉스필드가 아니라 드롭샷" — 영상·그림은 드롭샷으로 옮겼지만 드롭샷 연결에 목소리 도구가 없어
릴스 대사(Hana·Knox)만 힉스필드에 남아 있었다(하루 약 0.5크레딧). 힉스필드 구독을 끊으면 그날부터 영상 릴스를 못 만든다.
이 스크립트는 그 자리를 **마이크로소프트 읽기(edge-tts, 무료·계정 없음)** 로 바꾼다 — 힉스필드 구독·크레딧과 상관없이 매일 돌아간다.

사용:
  python3 automation/pilots/ai_reel/tts.py automation/pilots/ai_reel/{오늘}/brief.json
      brief.json 의 "voices" 를 그대로 녹음해 각 줄의 "file"(예 stems/i1_scarf.mp3)에 쓴다. 이미 있는 파일은 건너뛴다(같은 줄을 두 번 녹음하지 않는다).
  … --force                 이미 있어도 다시 녹음한다(받아쓰기가 낮아 원고를 바꾼 줄만 다시 녹음할 때: --only i4 --force)
  … --only i4,i_bye_save    그 줄만(파일 이름에 든 말로 고른다)
  … --check                 녹음하지 않고 원고·목소리·파일 이름만 점검한다(네트워크 없음 — 자동 점검·CI 가 쓴다)
  … --list                  쓸 수 있는 목소리·말투 이름
  python3 automation/pilots/ai_reel/tts.py --samples "오늘 아침 5가지, 시작합니다!" --out /tmp/voice_samples
      목소리 고르기(한 번) — 같은 문장을 목소리별로 만들어 나란히 들어 본다.

brief.json 의 voices 칸(episode.py 와 같은 칸에 셋을 더한다):
  {"file": "stems/i1_scarf.mp3", "start": 0.05, "tempo": 1.0,
   "text": "'사지 마' 가게, 온라인 열자 품절입니다!",     ← 화면·검수용 원고(content 숫자 그대로)
   "tts": "사지 마 가게, 온라인 열자 품절입니다!",       ← 실제로 읽을 말(숫자·영문은 소리 나는 대로 한글, qa 가 요구)
   "who": "knox", "style": "open"}                        ← 목소리·말투(아래 VOICES·STYLES). 없으면 첫 줄 knox·나머지 hana,
                                                            이름에 'bye' 가 든 줄(끝인사)은 hello.
  "who" 에는 hana·knox 말고도 sunhi·injoon·vivienne(대안 목소리)이나 edge-tts 목소리 이름(ko-KR-…)을 그대로 적어도 된다.

기존 릴스 목소리와의 관계(2026-11-15): Hana·Knox 는 힉스필드 목소리였고, 이 스크립트의 기본값은 **기존 녹음 79개를 재서
음높이·말 속도·성대(포먼트)를 가장 비슷하게 맞춘 값**이다(자세한 수치는 아래 VOICES 주석). 힉스필드와 사람이 다르므로
완전히 같지는 않다 — `--samples` 로 들어 보고 다르면 brief 의 `who`·`style` 만 바꾸면 된다.

만들어지는 파일(지금까지 힉스필드가 주던 것과 같은 모양 — episode.py·qa.py 를 고치지 않는다):
  mp3 · 24kHz · 모노 · 96kbps, 앞뒤 무음을 -40dB 기준으로 잘라 냄(qa.TRIM_AF 와 같은 필터). tempo 는 brief 값으로 episode.py 가 건다.
  길이가 장면 칸보다 길면 무엇을 할지(대사를 줄이거나 tempo) 표에 적어 준다.

처음 한 번: pip install -q edge-tts   (새 작업 세션엔 없다 — RUNBOOK_REEL '새 세션 준비')
ffmpeg·ffprobe 는 episode.py 가 이미 쓰는 것을 그대로 쓴다.
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# 앞뒤 무음 자르기 — qa.py 의 TRIM_AF 와 같은 필터(녹음 길이를 재는 쪽과 같은 기준이어야 싱크가 맞는다)
TRIM_AF = ("silenceremove=start_periods=1:start_threshold=-40dB,areverse,"
           "silenceremove=start_periods=1:start_threshold=-40dB,areverse")
SPEC = {"channels": 1, "sample_rate": 24000, "codec": "mp3"}   # 힉스필드 녹음과 같은 모양
BITRATE = "96k"

# edge-tts 목록에 한국어를 읽을 수 있는 목소리는 여섯이다(2026-11-15 확인: SunHi·InJoon·HyunsuMultilingual / Ava·Emma·Brian·Vivienne 다국어).
# HyunsuMultilingual 은 무료 읽기 서버가 소리를 주지 않는다('No audio received').
#
# **기존 릴스 목소리(Hana·Knox — 힉스필드)와 가장 비슷하게 맞춘 값이다(2026-11-15 분석).**
# 기존 녹음 79개를 재 보니 — Hana: F0(음높이) 205~215Hz · 여자 성대(F3 2,800~3,000Hz) · 초당 5.0~5.5음절.
#   Knox: F0 240~262Hz(들뜬 남자 — 높은 톤으로 또박또박) · 남자 성대(F3 2,500Hz) · 초당 5.3음절.
# 그래서 Hana 는 Emma(+15% 속도·음높이 그대로)로 F0 216·초당 5.2음절, Knox 는 Brian 을 +100Hz 로 올려 F0 222·초당 5.3음절에 맞췄다
# (Brian 은 +100Hz 위로는 서비스가 음을 더 못 올린다 — 기존 Knox 보다 40Hz 낮은 것이 이 서비스의 한계).
# 한국어 발음은 base 받아쓰기로 네 줄 평균 — Emma 97% · Brian 96% · SunHi(맨소리) 89%.
VOICES = {
    "hana": {"edge": "en-US-EmmaMultilingualNeural", "rate": "+15%", "pitch": "+0Hz",
             "note": "여자 · 만화 캐릭터 톤(기존 Hana 와 같은 높이)"},
    "knox": {"edge": "en-US-BrianMultilingualNeural", "rate": "+20%", "pitch": "+100Hz",
             "note": "남자 · 높고 들뜬 중계 톤(기존 Knox 와 같은 성대, 음은 40Hz 낮음)"},
    # 대안 — 받아쓰기가 낮은 날·다른 톤을 고를 때 who 에 이 이름을 적는다
    "sunhi": {"edge": "ko-KR-SunHiNeural", "rate": "+0%", "pitch": "+0Hz",
              "note": "한국어 원어민 여자 · 차분한 진행자"},
    "injoon": {"edge": "ko-KR-InJoonNeural", "rate": "+4%", "pitch": "+40Hz",
               "note": "한국어 원어민 남자 · 조금 높인 아나운서"},
    "vivienne": {"edge": "fr-FR-VivienneMultilingualNeural", "rate": "+10%", "pitch": "+20Hz",
                 "note": "여자 · 살짝 낮은 톤(기존 Hana 와 비슷한 높이, 발음 97%)"},
}

# 말투 — 목소리의 기본값에 **아주 조금만** 더한다(rate %·pitch Hz).
# 위에서 맞춘 값이 기준이라 말투는 0 근처로 두고, 세기는 대사·자막·편집으로 낸다.
# 11/15 시험: 음을 크게 올리면(예 pitch +34Hz·rate +10%) 받아쓰기가 10~20%p 떨어졌다('네이버가'→'대숨을').
STYLES = {
    "open":    {"rate": "+0", "pitch": "+0", "note": "0초 여는 한 마디(기준)"},
    "excited": {"rate": "+2", "pitch": "+1", "note": "신나서 들뜬"},
    "urgent":  {"rate": "+4", "pitch": "+0", "note": "다급하게 또박또박"},
    "bright":  {"rate": "+0", "pitch": "+0", "note": "밝게 또박또박(주제 줄 기본)"},
    "calm":    {"rate": "-3", "pitch": "-1", "note": "여유 있고 다정하게(‘나’에게 닿는 줄)"},
    "hello":   {"rate": "+1", "pitch": "+2", "note": "경쾌한 끝인사"},
}
DEFAULT_STYLE = {"first": "open", "bye": "hello", "rest": "bright"}

TAG = re.compile(r"\[[^\]]*\]")          # qa.py 와 같은 표시 '[excited]' — 소리로 읽히지 않게 지운다
ROUGH = re.compile(r"[0-9A-Za-z%]")      # qa 가 tts 칸에서 막는 것(숫자·영문)


def strip_tags(t):
    """'[excited] 사지 마…' → '사지 마…' — edge-tts 는 표시를 그대로 읽으므로 지운다(qa 의 tts 칸은 표시가 있어도 된다)."""
    return re.sub(r"\s{2,}", " ", TAG.sub(" ", t or "")).strip()


def _num(v, unit):
    """'+30Hz'·'-4%' → 30·-4."""
    s = str(v or "0").strip().replace(unit, "").replace("+", "")
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def _shift(base, delta, unit):
    """기본값에 말투를 더한다 — '+30Hz' + '+4' → '+34Hz', '+6%' + '-4' → '+2%'."""
    v = _num(base, unit) + int(delta)
    return f"{'+' if v >= 0 else ''}{v}{unit}"


def resolve(entry, i, total):
    """voices 한 줄 → (who, style, edge 목소리, rate, pitch). 적은 것만 쓰고 나머지는 기본값."""
    who = str(entry.get("who") or "").strip()
    named = who.lower()
    if not named or named not in VOICES:
        if who.startswith("ko-KR-"):                     # edge-tts 목소리 이름을 그대로 적은 줄
            preset = {"edge": who, "rate": "+0%", "pitch": "+0Hz"}
        else:
            fname = str(entry.get("file") or "").lower()
            named = "knox" if i == 0 else "hana"
            preset = VOICES[named]
    else:
        preset = VOICES[named]
    style = str(entry.get("style") or "").strip().lower()
    if not style:
        fname = str(entry.get("file") or "").lower()
        style = DEFAULT_STYLE["first"] if i == 0 else (DEFAULT_STYLE["bye"] if "bye" in fname else DEFAULT_STYLE["rest"])
    if style not in STYLES:
        style = DEFAULT_STYLE["rest"]
    st = STYLES[style]
    return (named or preset["edge"], style, preset["edge"],
            _shift(preset.get("rate"), st["rate"], "%"), _shift(preset.get("pitch"), st["pitch"], "Hz"))


def caption_slot(brief, i):
    """그 줄이 말하는 동안의 장면 칸 길이(초) — 자막 start~end. 없으면 None."""
    caps = brief.get("captions") or []
    if 0 <= i < len(caps):
        try:
            return round(float(caps[i]["end"]) - float(caps[i]["start"]), 2)
        except (KeyError, TypeError, ValueError):
            return None
    return None


def load_lines(brief_path):
    """brief.json → 줄 목록. 경로는 전부 brief.json 이 있는 폴더 기준(episode.py·qa.py 와 같다)."""
    brief_path = Path(brief_path)
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    base = brief_path.parent
    voices = brief.get("voices") or []
    lines = []
    for i, v in enumerate(voices):
        who, style, edge, rate, pitch = resolve(v, i, len(voices))
        say = strip_tags(v.get("tts") or v.get("text") or "")
        lines.append({
            "i": i, "file": str(v.get("file") or ""), "path": base / str(v.get("file") or ""),
            "who": who, "style": style, "edge": edge, "rate": rate, "pitch": pitch,
            "say": say, "text": str(v.get("text") or ""), "slot": caption_slot(brief, i),
            "tempo": v.get("tempo", 1.0),
        })
    return brief, base, lines


def problems(base, lines):
    """녹음 전에 막아야 할 것 — 파일 이름이 폴더 밖을 가리키거나, 원고가 비었거나, tts 에 숫자·영문이 남은 줄."""
    out = []
    if not lines:
        out.append("voices 칸이 없다 — brief.json 에 대사 줄을 적어야 녹음한다")
    for L in lines:
        n = L["i"] + 1
        if not L["file"]:
            out.append(f"대사 {n}: file 칸이 없다(예 stems/i1_scarf.mp3)")
            continue
        try:
            L["path"].resolve().relative_to(base.resolve())
        except ValueError:
            out.append(f"대사 {n}: file '{L['file']}' 이 brief.json 폴더 밖이다 — stems/ 안에 쓴다")
        if not L["say"]:
            out.append(f"대사 {n}: text·tts 가 비었다")
        elif ROUGH.search(L["say"]):
            out.append(f"대사 {n}: tts '{L['say'][:24]}' 에 숫자·영문이 있다 — 소리 나는 대로 한글만"
                       "(예 '63억 달러' → '육십삼억 달러', 'AI' → '에이아이')")
        if not str(L["file"]).lower().endswith((".mp3", ".wav", ".m4a")):
            out.append(f"대사 {n}: file '{L['file']}' 확장자가 오디오가 아니다")
    return out


def has_ffmpeg():
    """ffmpeg·ffprobe 가 있는지 — episode.py 가 이미 쓰므로 보통은 있다."""
    from shutil import which
    return bool(which("ffmpeg"))


def probe(path):
    """(길이 초, 채널, 샘플레이트) — ffprobe 로 잰다. 못 재면 (None, None, None)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                            "-show_entries", "stream=channels,sample_rate", "-show_entries", "format=duration",
                            "-of", "json", str(path)], capture_output=True, text=True, check=True)
        d = json.loads(r.stdout or "{}")
        st = (d.get("streams") or [{}])[0]
        return (round(float(d.get("format", {}).get("duration") or 0), 3),
                st.get("channels"), int(st.get("sample_rate") or 0) or None)
    except (OSError, ValueError, subprocess.CalledProcessError, IndexError):
        return (None, None, None)


async def _speak(text, voice, rate, pitch, dst, tries=3):
    """edge-tts 로 한 줄 읽어 dst(mp3)에 쓴다 — 실패하면 조금 기다렸다 다시(3번)."""
    from edge_tts import Communicate
    last = None
    for attempt in range(1, tries + 1):
        try:
            # boundary 는 WordBoundary 로 부른다 — 기본값(SentenceBoundary)으로는 오디오가 오지 않는 경우가 있었다(11/15 확인).
            # 받아쓰기용 낱말 시각은 쓰지 않는다.
            await Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary").save(str(dst))
            if dst.exists() and dst.stat().st_size > 2000:
                return
            last = RuntimeError("오디오가 비었다(0바이트)")
        except Exception as e:      # 네트워크·서비스 오류 — 같은 줄만 다시
            last = e
        await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(f"녹음 실패({tries}번): {last}")


def _polish(src, dst_tmp):
    """앞뒤 무음을 자르고 mp3 24kHz 모노 96k 로 고른다(힉스필드 녹음과 같은 모양)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", TRIM_AF,
                    "-ac", str(SPEC["channels"]), "-ar", str(SPEC["sample_rate"]),
                    "-c:a", "libmp3lame", "-b:a", BITRATE, str(dst_tmp)], check=True)


def synth(line, force=False):
    """한 줄 녹음 → line['path']. 이미 있고 force 가 아니면 건너뛴다. (했다면 True, 길이 초).
    임시 파일은 목적지와 같은 폴더에 만든다(/tmp 가 다른 장치인 환경에서도 마지막에 그대로 옮겨 놓을 수 있게)."""
    dst = line["path"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not force:
        return False, probe(dst)[0]
    with tempfile.TemporaryDirectory(dir=dst.parent) as tmp:
        raw, done = Path(tmp) / "raw.mp3", Path(tmp) / "out.mp3"
        asyncio.run(_speak(line["say"], line["edge"], line["rate"], line["pitch"], raw))
        _polish(raw, done)
        sec, ch, sr = probe(done)
        if sec is None or sec < 0.3:
            raise RuntimeError(f"'{line['say'][:20]}' 녹음이 비었다({sec}초) — 말이 너무 짧거나 서비스가 막았다")
        if (ch is not None and ch != SPEC["channels"]) or (sr is not None and sr != SPEC["sample_rate"]):
            raise RuntimeError(f"만들어진 소리가 {ch}ch·{sr}Hz 다(기대 {SPEC['channels']}ch·{SPEC['sample_rate']}Hz)")
        os.replace(done, dst)      # 다 만든 뒤에 바꾼다 — 실패해도 앞의 좋은 녹음이 남는다
    return True, probe(dst)[0]


def tempo_hint(sec, slot, tempo=1.0):
    """장면 칸에 들어가는지 → (권할 tempo 또는 None, 한 줄 설명)."""
    if not sec:
        return None, "길이를 못 쟀다(ffprobe 없음) — 눈으로 들어 보고 판단한다"
    if not slot:
        return None, "장면 칸을 몰라 길이만 본다"
    now = sec / max(tempo, 0.01)
    if now <= slot:
        return None, f"칸 {slot:.2f}초에 들어간다"
    need = round(min(now / slot, 1.99) * 20) / 20
    if need <= 1.2:
        return need, f"칸 {slot:.2f}초보다 {now - slot:.2f}초 길다 — tempo {need:.2f} 로 줄인다(brief 에 적는다)"
    return None, f"칸 {slot:.2f}초보다 {now - slot:.2f}초 길다 — tempo 1.2 로도 안 들어간다: 대사를 줄여 다시 녹음"


def fmt_table(rows):
    """사람이 읽는 표 — 줄·목소리·말투·길이·칸·할 일."""
    head = f"{'줄':<14}{'목소리':<7}{'말투':<9}{'길이':>6}  {'칸':>5}  할 일"
    out = [head]
    for r in rows:
        sec = f"{r['sec']:.2f}초" if r["sec"] else "-"
        slot = f"{r['slot']:.2f}" if r["slot"] else "-"
        out.append(f"{r['file'].split('/')[-1]:<14}{r['who']:<7}{r['style']:<9}{sec:>6}  {slot:>5}  {r['how']}")
    return "\n".join(out)


def samples(text, out_dir):
    """목소리 고르기 — 같은 문장을 목소리·말투별로 만들어 나란히 들어 볼 수 있게 한다."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for name, p in VOICES.items():
        for style in ("open", "calm"):
            st = STYLES[style]
            rate = _shift(p.get("rate"), st["rate"], "%")
            pitch = _shift(p.get("pitch"), st["pitch"], "Hz")
            dst = out / f"{name}_{style}.mp3"
            synth({"say": strip_tags(text), "edge": p["edge"], "rate": rate, "pitch": pitch,
                   "path": dst, "i": 0, "file": dst.name, "who": name, "style": style}, force=True)
            made.append((dst, f"{name}({p['edge']}) · {style} · {p['note']}"))
    for dst, why in made:
        print(f"  {dst}  — {why}")
    return made


def main():
    ap = argparse.ArgumentParser(description="AI 릴스 대사 녹음(edge-tts, 무료)")
    ap.add_argument("episode", nargs="?", help="brief.json (voices 칸이 든 것)")
    ap.add_argument("--force", action="store_true", help="이미 있어도 다시 녹음")
    ap.add_argument("--only", help="그 줄만 — 파일 이름에 든 말(쉼표로 여럿: i4,i_bye_save)")
    ap.add_argument("--check", action="store_true", help="녹음하지 않고 점검만(네트워크 없음)")
    ap.add_argument("--list", action="store_true", help="목소리·말투 이름 보기")
    ap.add_argument("--samples", metavar="문장", help="그 문장을 목소리별로 만들어 들어 보기")
    ap.add_argument("--out", default="voice_samples", help="--samples 결과 폴더(기본 voice_samples)")
    a = ap.parse_args()

    if a.list:
        print("목소리(who):")
        for k, v in VOICES.items():
            print(f"  {k:<8} {v['edge']:<32} rate {v['rate']:>5} pitch {v['pitch']:>6}  {v['note']}")
        print("말투(style):")
        for k, v in STYLES.items():
            print(f"  {k:<8} rate {v['rate']:>4} pitch {v['pitch']:>4}  {v['note']}")
        print("기본값: 첫 줄 open · 끝인사(이름에 bye) hello · 나머지 bright / who: 첫 줄 knox · 나머지 hana")
        return 0

    if a.samples:
        if not has_ffmpeg():
            print("✗ ffmpeg 가 없다 — episode.py 가 쓰는 것과 같은 것을 찾는다", file=sys.stderr)
            return 1
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            print("✗ edge-tts 가 없다 — pip install -q edge-tts", file=sys.stderr)
            return 1
        samples(a.samples, a.out)
        print(f"ok {a.out} — 들어 보고 고른 이름을 brief.json 의 who·style 에 적는다")
        return 0

    if not a.episode:
        ap.error("brief.json 이 필요하다(--check·--samples·--list 말고)")

    brief, base, lines = load_lines(a.episode)
    bad = problems(base, lines)
    if bad:
        print("✗ 녹음할 수 없다")
        for b in bad:
            print("  -", b)
        return 1

    print(f"{len(lines)}줄 · brief {Path(a.episode).name}")
    if a.check:
        for L in lines:
            print(f"  {L['i'] + 1}. {L['file']:<22} {L['who']:<7} {L['style']:<9} {L['edge']:<32} "
                  f"rate {L['rate']:>5} pitch {L['pitch']:>6}  '{L['say']}'")
        print("✓ 원고·목소리·파일 이름 점검 통과(녹음은 하지 않았다)")
        return 0

    if not has_ffmpeg():
        print("✗ ffmpeg 가 없다 — episode.py 가 쓰는 것과 같은 것을 찾는다", file=sys.stderr)
        return 1
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("✗ edge-tts 가 없다 — 새 작업 세션엔 없다: pip install -q edge-tts", file=sys.stderr)
        return 1

    want = [w.strip() for w in a.only.split(",")] if a.only else None
    picked = [L for L in lines if not want or any(w and w in L["file"] for w in want)]
    if want and not picked:
        print(f"✗ --only {a.only} 에 맞는 줄이 없다(파일 이름으로 고른다)", file=sys.stderr)
        return 1

    rows, fails = [], []
    for L in picked:
        made, blocked = True, ""
        try:
            made, sec = synth(L, force=a.force)
        except Exception as e:
            fails.append(f"{L['file']}: {e}")
            sec, made, blocked = probe(L["path"])[0], True, f"녹음 실패(앞의 파일 그대로) — {e}"
        need, how = tempo_hint(sec, L["slot"], float(L["tempo"] or 1.0))
        if blocked:
            how = blocked
        elif not made:
            how = "이미 있다(그대로 씀) — " + how
        rows.append({**L, "sec": sec, "how": how, "tempo_need": need})

    print(fmt_table(rows))
    for r in rows:
        if r["tempo_need"]:
            print(f"  · {r['file'].split('/')[-1]}: brief.json 의 tempo 를 {r['tempo_need']:.2f} 로")
    if fails:
        print("✗ 녹음 실패")
        for f in fails:
            print("  -", f)
        return 1
    done = [r for r in rows if r["sec"]]
    print(f"\nok {len(rows)}줄 · {sum(r['sec'] for r in done):.2f}초 · "
          f"{SPEC['sample_rate'] // 1000}kHz 모노 mp3 → {base / 'stems'} (없는 줄은 --force 로 다시)")
    print("다음: python3 automation/pilots/ai_reel/qa.py <brief.json> --stems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
