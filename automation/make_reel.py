#!/usr/bin/env python3
"""카드뉴스 → 인스타그램 릴스 영상(1080×1920, 음악 포함). post-instagram.yml 이 게시 직전에 만든다(영상은 저장소에 두지 않는다).

카드(4:5)를 세로 화면 가운데보다 조금 위에 두고(아래는 릴스 캡션·버튼이 덮는 자리), 배경은 같은 카드를 흐리게 깔아 채운다.
데일리 릴스는 10장을 다 넣지 않고 표지·H PICK·이슈 4장·마무리 7장만 약 20초로 보여준다(REEL_PARTS — 2026-10-01:
릴스는 시청 시간·완주율이 도달을 가르는데, 글자가 많은 요약·심층·노트 카드를 3.8초씩 넘기던 32초 영상은 9/29 부터 도달이 한 자리로 떨어졌다).
장마다 아주 천천히 확대하고(정지 화면 슬라이드쇼로 보이지 않게) 옆으로 밀어 넘긴다(캐러셀을 넘기는 느낌). 음악은 assets/music/tracks.json 의 곡을 날짜마다 돌려 쓰고
영상 길이에 맞춰 자르고 끝을 서서히 줄인다. 인스타 음악 라이브러리 곡은 API 로 넣을 수 없어서,
재배포가 허용된 CC0·CC BY 곡만 쓴다. CC BY 곡의 출처(곡·작가·라이선스)는 캡션이 아니라 영상 위쪽에 작게 넣는다
(2026-09-25 요청 — 캡션에서 출처 문구를 뺐다). Pillow·글꼴이 없어 못 넣으면 post_instagram.py 가 릴스 댓글로 단다.

  python3 automation/make_reel.py 2026-09-24                 # instagram/2026-09-24/reel.mp4 (커밋하지 않는다)
  python3 automation/make_reel.py 2026-09-25-weekly --out /tmp/r.mp4 --ffmpeg /path/to/ffmpeg
"""
import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import INSTAGRAM_DIR, ROOT, load_config  # noqa: E402

MUSIC_DIR = ROOT / "assets" / "music"
W, H, FPS = 1080, 1920, 30
DEFAULT_TIMING = {"first": 2.2, "card": 3.4, "last": 2.5, "fade": 0.35, "lift": 60, "zoom": 0.035,
                  "transition": "slideleft"}
REEL_PARTS = ("cover", "pick", "issue", "cta")   # 데일리 릴스에 넣을 카드(파일 이름 끝) — 없으면 전부
# 세로 전용 프레임(build_issue.py → instagram/{날짜}/reel_frames/r1_hook.jpg …, edith/reel_frames.py)이 있으면 그걸 쓴다
# (2026-10-03~, 성장 검토: 질문 훅 → 숫자 → 결론 → 에디터 H, 약 10초). 없으면 위 카드 방식.
VERTICAL_TIMING = {"first": 2.4, "card": 3.0, "last": 2.6, "fade": 0.3, "lift": 0, "zoom": 0.025, "transition": "slideleft"}
CARD_H = 1350          # 카드 1080×1350 을 가로 1080 에 맞춰 올린다
CREDIT_H = 60          # 음악 출처 띠 높이(카드 바로 위, 흐린 배경 위)
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


def credit_image(track, path):
    """CC BY 곡 출처를 넣을 투명 PNG(가로 1080). CC0 이거나 Pillow·글꼴이 없으면 None."""
    if track.get("license", "").upper() == "CC0":
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    font_path = next((f for f in FONTS if Path(f).exists()), None)
    if not font_path:
        return None
    text = f"\u266a {track['title']} \u00b7 {track['artist']} \u00b7 {track['license']}"
    font = ImageFont.truetype(font_path, 26)
    img = Image.new("RGBA", (W, CREDIT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tw = draw.textlength(text, font=font)
    x = (W - tw) / 2
    # 밝은 카드(흰 배경)에서도 읽히게 반투명 검은 알약 위에 흰 글자
    draw.rounded_rectangle((x - 18, 8, x + tw + 18, CREDIT_H - 8), radius=(CREDIT_H - 16) // 2, fill=(0, 0, 0, 105))
    draw.text((x, 15), text, font=font, fill=(255, 255, 255, 235))
    img.save(path)
    return Path(path)


def pick_track(key):
    """날짜(또는 호 키)로 곡을 돌려 쓴다. 곡이 없으면 None."""
    path = MUSIC_DIR / "tracks.json"
    if not path.exists():
        return None
    tracks = [t for t in json.loads(path.read_text(encoding="utf-8")) if (MUSIC_DIR / t["file"]).exists()]
    if not tracks:
        return None
    day = dt.date.fromisoformat(key[:10])
    return tracks[(day.toordinal() + key.endswith("-weekly")) % len(tracks)]  # 같은 날 주간 특집은 다른 곡


def reel_cards(cards):
    """데일리 호면 REEL_PARTS 카드만(순서 유지), 그 밖(주간 특집·옛 형식)이나 3장이 안 되면 전부."""
    part = lambda c: c.stem.rsplit("_", 1)[-1].rstrip("0123456789")  # noqa: E731 — 'issue2' → 'issue'
    picked = [c for c in cards if part(c) in REEL_PARTS]
    return picked if len(picked) >= 3 and part(picked[0]) == "cover" else cards


def build(cards, out, track, ffmpeg="ffmpeg", timing=None, credit=None, full=False):
    """full=True: 이미 1080×1920 인 세로 프레임(흐린 배경 없이 그대로 채운다)."""
    t = {**(VERTICAL_TIMING if full else DEFAULT_TIMING), **(timing or {})}
    n = len(cards)
    durs = [t["first"]] + [t["card"]] * (n - 2) + [t["last"]] if n > 1 else [t["first"]]
    fade = t["fade"]
    total = sum(durs) - fade * (n - 1)

    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for c, d in zip(cards, durs):
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(c)]
    cmd += ["-i", str(MUSIC_DIR / track["file"])]
    if credit:
        cmd += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(credit)]

    parts = []
    zoom = float(t.get("zoom") or 0)
    punch, punch_s = float(t.get("punch") or 0), float(t.get("punch_s") or 0.5)
    for i in range(n):
        # 합성한 화면을 장이 넘어가는 동안 zoom 만큼 천천히 키우고 가운데를 잘라 1080×1920 을 유지한다.
        # punch(E8, 2026-10-13~): 첫 장은 punch 만큼 크게 시작해 punch_s 초 만에 제자리로 — 0초부터 화면이 움직여 넘기기 전에 눈이 멈추게
        hit = i == 0 and punch
        k = f"1+{zoom}*t/{durs[i]:.3f}" + (f"+{punch}*max(0,1-t/{punch_s})" if hit else "")
        # 확 다가오는 첫 장은 위쪽(워드마크·음악 출처 띠)을 고정하고 아래로 커지게 — 가운데 기준이면 워드마크가 출처 띠와 겹친다
        crop = f"crop={W}:{H}:(iw-{W})/2:(ih-{H})*0.1" if hit else f"crop={W}:{H}"
        grow = (f",scale=w='trunc({W}*({k})/2)*2':h='trunc({H}*({k})/2)*2'"
                f":eval=frame,{crop}") if zoom or hit else ""
        if full:
            parts.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}{grow},format=yuv420p,setsar=1[v{i}]")
            continue
        parts.append(
            f"[{i}:v]split[a{i}][b{i}];"
            f"[a{i}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=160:steps=2,eq=brightness=-0.03[bg{i}];"
            f"[b{i}]scale={W}:-2[fg{i}];"
            f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2-{t['lift']},fps={FPS}{grow},format=yuv420p,setsar=1[v{i}]")
    prev, offset = "v0", 0.0
    for i in range(1, n):
        offset += durs[i - 1] - fade
        parts.append(f"[{prev}][v{i}]xfade=transition={t.get('transition') or 'fade'}:duration={fade}:offset={offset:.3f}[x{i}]")
        prev = f"x{i}"
    if credit:   # 카드 위쪽 흐린 배경에 음악 출처를 영상 내내 작게(세로 프레임은 맨 위 워드마크 위)
        y = 104 if full else (H - CARD_H) // 2 - t["lift"] - CREDIT_H - 8
        parts.append(f"[{prev}][{n + 1}:v]overlay=0:{y}:format=auto,format=yuv420p[vout]")
        prev = "vout"
    start = float(track.get("start", 0))
    parts.append(f"[{n}:a]atrim=start={start}:duration={total:.3f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d=0.6,afade=t=out:st={max(total - 1.8, 0):.3f}:d=1.8,"
                 f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aout]")
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{prev}]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    return total


def hook_on(ig, key):
    """E8 릴스 첫 장 훅(짧게 + 확 다가오기)을 쓰는 날인가 — config.instagram.reel_hook_from 부터(2026-10-13~)."""
    start = ig.get("reel_hook_from")
    return bool(start and str(key)[:10] >= start)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="instagram/ 아래 폴더 이름 (YYYY-MM-DD 또는 YYYY-MM-DD-weekly)")
    ap.add_argument("--out")
    ap.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    ap.add_argument("--cards", action="store_true", help="세로 프레임이 있어도 예전 카드 방식으로")
    args = ap.parse_args()
    folder = INSTAGRAM_DIR / args.key
    frames = sorted((folder / "reel_frames").glob("r[0-9]_*.jpg"))
    full = len(frames) >= 3 and not args.cards
    cards = frames if full else reel_cards(sorted(folder.glob("[0-9][0-9]_edit_h_*.png")))
    if not cards:
        sys.exit(f"✗ {folder} 에 카드 PNG 가 없습니다")
    track = pick_track(args.key)
    if not track:
        print("✗ assets/music/tracks.json 에 쓸 곡이 없습니다 — 릴스는 건너뜁니다(카드 게시는 그대로)")
        sys.exit(3)
    out = Path(args.out) if args.out else folder / "reel.mp4"
    ig = load_config().get("instagram") or {}
    timing = ig.get("reel_vertical_timing") if full else ig.get("reel_timing")
    hook = hook_on(ig, args.key) and full
    if hook:   # E8: 첫 장을 짧게(평균 시청 1.5~2.8초 — 넘기기 전에 다음 장) + 첫 장 확 다가오기
        timing = {**(timing or {}), **(ig.get("reel_hook_timing") or {})}
    with tempfile.TemporaryDirectory() as tmp:
        credit = credit_image(track, Path(tmp) / "credit.png")
        try:
            total = build(cards, out, track, args.ffmpeg, timing, credit, full)
        except subprocess.CalledProcessError:
            # 오래된 ffmpeg 는 scale 의 t 변수·slideleft 를 모를 수 있다 — 움직임 없이(예전 방식) 한 번 더
            print("  ↘ 확대·밀기 효과로 만들지 못해 효과 없이 다시 만듭니다", flush=True)
            total = build(cards, out, track, args.ffmpeg, {**(timing or {}), "zoom": 0, "punch": 0, "transition": "fade"}, credit, full)
            hook = False
    style = "vertical" if full else "cards"
    print(f"✓ {out} ({'세로 프레임' if full else '카드'} {len(cards)}장 {total:.1f}초, {out.stat().st_size // 1024}KB)"
          f" — 음악: {track['title']} / {track['artist']} ({track['license']})" + (" · 영상에 출처 표시" if credit else ""))
    print(json.dumps({"reel": str(out), "track": track, "credit_in_video": bool(credit), "style": style,
                      "seconds": round(total, 1), "hook": hook}, ensure_ascii=False))


if __name__ == "__main__":
    main()
