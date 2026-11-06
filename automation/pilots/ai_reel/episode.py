#!/usr/bin/env python3
"""AI 영상 릴스 한 편 만들기 — 하루치 설정(episode.json) 하나로 글자·끝 화면·대사·배경음악·효과음을 얹는다.

2026-11-01 운영자 "오늘자 발행하면 이것도 영상으로 만들어서 바로 진행해줘 … 최대한 많이".
이 도구는 10/31 시험판(compose_v3.py·overlays.py)을 날마다 쓸 수 있게 묶은 것이다(레퍼런스 분석: automation/reviews/2026-11-01-ai-video.md).

사용:
  python3 automation/pilots/ai_reel/episode.py <episode.json> <힉스필드 영상.mp4> [--out instagram/{날짜}/reel_ai.mp4]

episode.json (경로는 이 파일 기준 상대경로):
  trim        [시작, 끝]           AI 영상에서 쓸 구간(초)
  end_seconds 2.5                  끝 화면 길이
  captions    [{start, end, top, size, html}]   화면 글자(대사와 같은 말 + 확인된 숫자를 <span class="hl">로)
  end_card    {line, sub, note}    끝 화면 문구
  voices      [{file, start, tempo, robot, text, tts}]   대사 파일(음성 인식으로 확인한 것) — text 는 화면·검수용 원고,
              tts 는 실제로 녹음한 말(숫자·영문을 한글 읽기로: '63억' → '육십삼억', 'G마켓' → '지마켓', 2026-11-04~ qa 가 요구)
              자막 시작은 그 줄 목소리 0~0.6초 앞(장면 경계), 끝은 목소리가 끝난 뒤 — 한 줄 말하는 동안 자막은 한 장(qa.sync_gaps)
  music       [{file, start, dur, fade_in, fade_out, offset, lufs, lowpass}]   곡 사이에 빈 구간을 두지 않는다 —
              '정적'은 무음이 아니라 같은 곡을 낮고 먹먹하게(lowpass·lufs -30 안팎) 깐다(11/01 "소리가 끊긴다")
  duck        {threshold, ratio, attack, release, mix}   대사 밑 음악 줄이기(기본 0.05·3·20·650·0.75)
  sfx         [[시작, 끝, 볼륨], …]  원래 AI 영상 소리(효과음)의 구간별 볼륨
규칙(분석 문서 '지켜야 할 선'): 숫자·이름은 AI 화면에 그리지 않고 여기 글자로만, 실존 인물·로고·실제 장소 없음, 주인공은 마스코트 H.
화면 속 'AI로 만든 영상' 표시는 없다(11/01 운영자) — 게시할 때 인스타 'AI 정보' 라벨과 캡션 한 줄로 밝힌다(post_instagram.py).
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
from edith.fonts import font_css  # noqa: E402

SHOT = ROOT / "automation" / "screenshot.cjs"
FACE = (ROOT / "assets" / "mascot" / "profile.png").as_uri()

# 대사 속 긴 쉼 줄이기(2026-11-07 회차~) — 11/06 운영자 "릴스 보니까 중간에 목소리 끊기는 것 같은데":
# 11/06 코인 줄 녹음은 '코인 세금,' 뒤 0.54초가 비어(-80dB) 영상 한가운데(11.35초)에서 소리가 말소리보다 19dB 꺼졌다.
# 쉼표마다 0.2~0.54초 쉬는 녹음이 배경(효과음 0.2·덕킹한 음악)이 얇은 장면에서 '끊김'으로 들린다.
# 말소리 최고보다 30dB 넘게 낮은 구간이 0.25초를 넘으면 0.2초만 남긴다 — 쉼표의 짧은 쉼(0.2초 안팎)·받침·숨은 말맛이라 그대로 둔다.
# 쉼이 줄면 낱말이 앞당겨져 그 장면 효과음과 겹칠 수 있다 — 완성본 받아쓰기(qa mix_heard)가 85% 아래면 그 줄만 다시 맞춘다.
PAUSE_CAP_FROM = "2026-11-07"
PAUSE_MIN, PAUSE_KEEP, PAUSE_DB, PAUSE_HOP = 0.25, 0.2, 30, 0.01


def pause_cap_on(ep):
    """이 회차에 대사 속 쉼 줄이기를 쓰나 — 설정의 "pause_cap"(true/false)이 먼저, 없으면 날짜(11/07~). 지난 회차는 만든 그대로 잰다."""
    if "pause_cap" in ep:
        return bool(ep["pause_cap"])
    return str(ep.get("date", "")) >= PAUSE_CAP_FROM


def pause_cuts(db, hop=PAUSE_HOP):
    """10ms 창 음량(dB) 목록 → 지울 구간 [(시작초, 끝초)]. 앞뒤 무음은 두고(뒤 silenceremove 가 자른다) 말 사이 긴 쉼만,
    쉼 가운데를 지우고 앞뒤로 PAUSE_KEEP/2 씩 남긴다."""
    if not len(db):
        return []
    peak = max(db)
    quiet = [d < peak - PAUSE_DB for d in db]
    voiced = [i for i, q in enumerate(quiet) if not q]
    cuts, i, last = [], voiced[0], voiced[-1]
    while i <= last:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j <= last and quiet[j]:
            j += 1
        if (j - i) * hop > PAUSE_MIN + 1e-9:
            cuts.append((round(i * hop + PAUSE_KEEP / 2, 4), round(j * hop - PAUSE_KEEP / 2, 4)))
        i = j
    return cuts


def cap_pauses(src, dst, sr=48000):
    """녹음 src 의 긴 쉼(pause_cuts)을 줄여 dst(48kHz 스테레오 wav)에 쓴다 → (dst, 줄인 초). 이음매는 5ms 씩 줄였다 키운다(딸깍 소리 막기)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
    hop = int(sr * PAUSE_HOP)
    n = len(x) // hop
    db = (20 * np.log10(np.sqrt((x[:n * hop].mean(1).reshape(n, hop).astype(np.float64) ** 2).mean(1)) + 1e-9)).tolist() if n else []
    cuts = pause_cuts(db)
    edges = [0] + [int(t * sr) for ab in cuts for t in ab] + [len(x)]
    fade = int(sr * 0.005)
    parts = []
    for k in range(0, len(edges), 2):
        seg = x[edges[k]:edges[k + 1]].copy()
        if len(seg) > 2 * fade:
            if k > 0:
                seg[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)[:, None]
            if k + 2 < len(edges):
                seg[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
        parts.append(seg)
    y = np.concatenate(parts) if parts else x
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "-", str(dst)],
                   input=np.ascontiguousarray(y, dtype=np.float32).tobytes(), check=True)
    return Path(dst), round(sum(b - a for a, b in cuts), 3)


CAPTION = """<!doctype html><html><head><meta charset="utf-8"><style>
{fonts}
html,body{{margin:0;width:1080px;height:1920px;background:transparent;font-family:'Pretendard',sans-serif;word-break:keep-all}}
.shade{{position:absolute;left:0;right:0;top:0;height:1000px;background:linear-gradient(180deg,rgba(0,0,0,.50) 0%,rgba(0,0,0,.30) 55%,rgba(0,0,0,0) 100%)}}
.top{{position:absolute;left:0;right:0;top:118px;text-align:center}}
.mark{{display:inline-flex;align-items:center;font-weight:850;font-size:40px;letter-spacing:-1px;color:#fff;text-shadow:0 2px 14px rgba(0,0,0,.55)}}
.mark .dot{{color:#FF5233}}
.cap{{position:absolute;left:70px;right:150px;top:{top}px}}
.kick{{display:inline-block;font-weight:700;font-size:34px;color:#fff;background:rgba(0,0,0,.55);padding:8px 18px;border-radius:12px;margin-bottom:18px}}
.main{{font-weight:850;font-size:{size}px;line-height:1.22;letter-spacing:-2px;color:#fff;text-shadow:0 4px 18px rgba(0,0,0,.75),0 0 3px rgba(0,0,0,.9)}}
.hl{{background:#FF5233;color:#111;padding:0 12px;border-radius:12px;text-shadow:none;box-decoration-break:clone;-webkit-box-decoration-break:clone}}
.sub{{margin-top:20px;font-weight:650;font-size:38px;line-height:1.4;color:#fff;text-shadow:0 3px 14px rgba(0,0,0,.8),0 0 3px rgba(0,0,0,.9)}}
</style></head><body>
<div class="shade"></div>
<div class="top"><span class="mark">EDIT H<span class="dot">.</span></span></div>
<div class="cap">{html}</div>
</body></html>"""

END = """<!doctype html><html><head><meta charset="utf-8"><style>
{fonts}
html,body{{margin:0;width:1080px;height:1920px;background:#F5F1E8;font-family:'Pretendard',sans-serif;word-break:keep-all;color:#111}}
.wrap{{position:absolute;left:90px;right:90px;top:520px;text-align:center}}
img{{width:240px;height:240px;border-radius:50%;display:block;margin:0 auto}}
.name{{margin-top:34px;font-weight:900;font-size:74px;letter-spacing:-2px}}
.name .dot{{color:#FF5233}}
.line{{margin-top:18px;font-weight:700;font-size:46px;letter-spacing:-1px}}
.sub{{margin-top:14px;font-weight:500;font-size:36px;color:#57534C;line-height:1.45}}
.btn{{display:inline-block;margin-top:54px;background:#111;color:#fff;font-weight:800;font-size:44px;padding:30px 64px;border-radius:999px}}
.note{{position:absolute;left:90px;right:90px;bottom:330px;text-align:center;font-weight:500;font-size:28px;color:#8A857C;line-height:1.5}}
</style></head><body>
<div class="wrap">
  <img src="{face}" alt="">
  <div class="name">EDIT H<span class="dot">.</span></div>
  <div class="line">{line}</div>
  <div class="sub">{sub}</div>
  <div class="btn">팔로우하고 내일 아침에 받기</div>
</div>
<div class="note">{note}</div>
</body></html>"""


def shot(html, out, transparent):
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "p.html"
        page.write_text(html, encoding="utf-8")
        r = subprocess.run(["node", str(SHOT), str(page), str(out), "1080", "1920"] + (["--transparent"] if transparent else []),
                           check=True, capture_output=True, text=True)
    info = json.loads(r.stdout.strip().splitlines()[-1])
    if "Pretendard" not in info["fonts"]:
        raise SystemExit(f"Pretendard 없이 그렸다(한글이 깨진다): {info['fonts']}")


XFADE = 0.3   # 본편 → 끝 화면 겹침(초) — 검은 프레임 없이 넘어간다

# 2026-11-02 운영자 '영상 중간에 끊기는 부분 없는지 점검해봐': 11/02 편은 프레임·소리가 빠진 곳은 없었지만 두 가지가 '끊기는' 느낌을 줬다.
# ① 24fps AI 원본을 30fps 로 내면서 다섯 프레임마다 한 프레임이 겹쳐(4:1) 휙 넘김·이동이 미세하게 덜컥인다 → 이날 설정부터 원본 fps 그대로 낸다.
# ② Seedance 가 장면 끝에 자세를 1초 가까이 멈춰 화면이 정지한 것처럼 보인다(11/02 도시 12.8~13.8초) → 설정의 "push": [[시작, 끝], …] 구간을
#    천천히 다가가게(1 → 1+push_zoom) 해 움직임을 살린다. 끝은 장면 경계(휙 넘김)에 맞춘다 — 거기서 원래 크기로 돌아가는 게 가려진다. qa.py 가 1초 넘게 멈춘 구간을 막는다.
SRC_RATE_FROM = "2026-11-03"


def out_rate(ep, src):
    """완성본 fps — SRC_RATE_FROM 설정부터 원본 fps(23~61 밖이면 30), 그 전 설정은 30(지난 편을 다시 렌더해도 같게)."""
    if str(ep.get("date", "")) < SRC_RATE_FROM:
        return 30
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0",
                            str(src)], capture_output=True, text=True).stdout.strip()
        num, den = r.split("/")
        fps = float(num) / float(den)
    except (OSError, ValueError, ZeroDivisionError):   # ffprobe 가 없거나(자동 점검 러너) 원본을 못 읽으면 30
        return 30
    return round(fps) if 23 <= fps <= 61 else 30


def push_filter(ep, rate):
    """"push" 구간마다 천천히 다가가는 zoompan(없으면 빈 문자열) — 1080×1920·rate 로 낸다. 시각은 trim 뒤 본편 기준."""
    spans = [(float(a), float(b)) for a, b in ep.get("push") or [] if float(b) > float(a)]
    if not spans:
        return ""
    z = float(ep.get("push_zoom", 0.06))
    expr = "1"
    for a, b in reversed(spans):
        expr = f"if(between(it\\,{a}\\,{b})\\,1+{z}*(it-{a})/{b - a:.3f}\\,{expr})"
    return f",zoompan=z='{expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps={rate}"

def render_cards(ep, work):
    fonts = font_css()
    paths = []
    for i, c in enumerate(ep["captions"]):
        p = work / f"cap{i}.png"
        shot(CAPTION.format(fonts=fonts, top=c.get("top", 300), size=c.get("size", 82), html=c["html"]), p, True)
        paths.append(p)
    e = ep.get("end_card") or {}
    end = work / "end.png"
    shot(END.format(fonts=fonts, face=FACE, line=e.get("line", "내일 아침 8시 30분에 또 만나요!"),
                    sub=e.get("sub", "2030의 아침을 편집합니다 · 경제부터 트렌드까지<br>숫자·출처 전문은 프로필 링크 뉴스레터에서"),
                    note=e.get("note", "숫자는 기사 2곳 이상에서 확인했어요")), end, False)
    return paths, end


def compose(ep, base, src, out, work):
    caps, end = render_cards(ep, work)
    t0, t1 = ep["trim"]
    main = round(t1 - t0, 3)
    endsec = ep.get("end_seconds", 2.5)
    total = main + endsec
    # 끝 화면은 본편 마지막 XFADE 초와 겹쳐 녹아들게 넣는다 — 검은색에서 밝아지게(fade in) 넣으면 넘어가는 순간 2프레임이 검게 튄다
    # (11/01 운영자 "영상 중간중간에 검은색으로 끊기는 것 같다" — 10/31·11/01 릴스 6편 모두 본편→끝 화면 사이 0.07초 검은 화면)
    rate = out_rate(ep, src)
    inputs = ["-i", str(src)] + sum((["-i", str(p)] for p in caps), []) + ["-loop", "1", "-t", f"{endsec + XFADE:.3f}", "-framerate", str(rate), "-i", str(end)]
    vi = len(caps) + 2
    voices, music = ep.get("voices", []), ep.get("music", [])
    vfiles = [base / v["file"] for v in voices]
    if vfiles and pause_cap_on(ep):   # 대사 속 0.25초 넘는 쉼을 0.2초로(11/07~ — 11/06 '중간에 목소리 끊김')
        vfiles = [cap_pauses(p, work / f"voice{k}.wav")[0] for k, p in enumerate(vfiles)]
    inputs += sum((["-i", str(p)] for p in vfiles), [])
    mi = vi + len(voices)
    inputs += sum((["-i", str(base / m["file"])] for m in music), [])

    f = [f"[0:v]trim={t0}:{t1},setpts=PTS-STARTPTS,scale=1080:1920:flags=lanczos,fps={rate}{push_filter(ep, rate)},setsar=1[v0]"]
    last = "v0"
    for k, c in enumerate(ep["captions"]):
        f.append(f"[{last}][{k + 1}:v]overlay=0:0:enable='between(t,{c['start']},{c['end']})'[vc{k}]")
        last = f"vc{k}"
    f.append(f"[{last}]trim=0:{main},setpts=PTS-STARTPTS,format=yuv420p,setsar=1,settb=1/{rate}[vm]")
    f.append(f"[{len(caps) + 1}:v]fps={rate},format=yuv420p,setsar=1,settb=1/{rate}[ve]")
    f.append(f"[vm][ve]xfade=transition=fade:duration={XFADE}:offset={main - XFADE:.3f}[v]")   # 길이는 그대로(main + endsec)
    # 효과음(원래 AI 영상 소리) — 구간별 볼륨
    expr = "0.3"
    for a, b, vol in reversed(ep.get("sfx", [[0, 999, 0.4]])):
        expr = f"if(between(t,{a},{b}),{vol},{expr})"
    f.append(f"[0:a]atrim={t0}:{t1},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
             f"volume='{expr}':eval=frame,apad=whole_dur={total},atrim=0:{total}[sfx]")
    vl = []
    for k, v in enumerate(voices):
        chain = (f"[{vi + k}:a]aresample=48000,aformat=channel_layouts=stereo,"
                 "silenceremove=start_periods=1:start_threshold=-40dB,areverse,silenceremove=start_periods=1:start_threshold=-40dB,areverse,"
                 f"atempo={v.get('tempo', 1.0)},highpass=f=80,acompressor=threshold=0.1:ratio=3:attack=5:release=80,loudnorm=I=-15:TP=-2")
        if v.get("robot"):
            chain += ",aecho=0.5:0.3:7:0.15,highpass=f=120,lowpass=f=7500,volume=1.6"
        f.append(chain + f",adelay={int(v['start'] * 1000)}:all=1[vo{k}]")
        vl.append(f"[vo{k}]")
    if vl:
        f.append(f"{''.join(vl)}amix=inputs={len(vl)}:normalize=0,apad=whole_dur={total},atrim=0:{total}" + (",asplit=2[voice][key]" if music else "[voice]"))
    ml = []
    for k, m in enumerate(music):
        fade = (f",afade=t=in:st=0:d={m['fade_in']}" if m.get("fade_in") else "") + \
               (f",afade=t=out:st={m['dur'] - m['fade_out']:.2f}:d={m['fade_out']}" if m.get("fade_out") else "")
        off = m.get("offset", 0)   # 곡의 어디서부터 쓸지(초) — 같은 곡의 뒷부분을 '정적' 바닥으로 다시 쓸 때
        lp = f",lowpass=f={m['lowpass']}" if m.get("lowpass") else ""   # 먹먹하게(시간이 멈춘 느낌) — 소리를 끊지 않고 낮춘다
        f.append(f"[{mi + k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim={off}:{off + m['dur']},asetpts=PTS-STARTPTS{lp},"
                 f"loudnorm=I={m.get('lufs', -20)}:TP=-3{fade},adelay={int(m['start'] * 1000)}:all=1[mu{k}]")
        ml.append(f"[mu{k}]")
    if ml:
        f.append(f"{''.join(ml)}amix=inputs={len(ml)}:normalize=0,apad=whole_dur={total},atrim=0:{total}[music]")
    if vl and ml:
        # 대사 밑 음악 줄이기 — 11/01 운영자 "소리가 중간중간 끊기는 것 같다": ratio 5·release 350ms 로 세게 줄이면
        # 낱말 사이 숨에서 음악이 늦게 돌아와 0.1~0.3초씩 15~20dB 꺼졌다 → 덜 깊게(mix)·천천히 돌아오게(release)
        d = {"threshold": 0.05, "ratio": 3, "attack": 20, "release": 650, "mix": 0.75, **(ep.get("duck") or {})}
        f.append(f"[music][key]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}:attack={d['attack']}:"
                 f"release={d['release']}:makeup=1:mix={d['mix']}[ducked]")
        f.append("[voice][ducked][sfx]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    elif vl:
        f.append("[voice][sfx]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    elif ml:
        f.append("[music][sfx]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    else:
        f.append("[sfx]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total}", str(out)], check=True)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("video", help="힉스필드에서 받은 AI 영상(소리 포함)")
    ap.add_argument("--out")
    a = ap.parse_args()
    epath = Path(a.episode).resolve()
    ep = json.loads(epath.read_text(encoding="utf-8"))
    out = Path(a.out) if a.out else ROOT / "instagram" / ep["date"] / "reel_ai.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        total = compose(ep, epath.parent, Path(a.video), out, Path(tmp))
    print(f"ok {out} {total:.2f}s")


if __name__ == "__main__":
    main()
