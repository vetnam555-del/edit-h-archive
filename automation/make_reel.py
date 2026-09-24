#!/usr/bin/env python3
"""카드뉴스 → 인스타그램 릴스 영상(1080×1920, 음악 포함). post-instagram.yml 이 게시 직전에 만든다(영상은 저장소에 두지 않는다).

카드(4:5)를 세로 화면 가운데보다 조금 위에 두고(아래는 릴스 캡션·버튼이 덮는 자리), 배경은 같은 카드를 흐리게 깔아 채운다.
장마다 정해진 시간만큼 보여주고 짧게 겹쳐 넘긴다. 음악은 assets/music/tracks.json 의 곡을 날짜마다 돌려 쓰고
영상 길이에 맞춰 자르고 끝을 서서히 줄인다. 인스타 음악 라이브러리 곡은 API 로 넣을 수 없어서,
재배포가 허용된 CC0·CC BY 곡만 쓴다(CC BY 는 릴스 캡션에 출처가 자동으로 붙는다 — post_instagram.py).

  python3 automation/make_reel.py 2026-09-24                 # instagram/2026-09-24/reel.mp4 (커밋하지 않는다)
  python3 automation/make_reel.py 2026-09-25-weekly --out /tmp/r.mp4 --ffmpeg /path/to/ffmpeg
"""
import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from edith.common import INSTAGRAM_DIR, ROOT, load_config  # noqa: E402

MUSIC_DIR = ROOT / "assets" / "music"
W, H, FPS = 1080, 1920, 30
DEFAULT_TIMING = {"first": 2.5, "card": 3.8, "last": 3.0, "fade": 0.4, "lift": 60}


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


def build(cards, out, track, ffmpeg="ffmpeg", timing=None):
    t = {**DEFAULT_TIMING, **(timing or {})}
    n = len(cards)
    durs = [t["first"]] + [t["card"]] * (n - 2) + [t["last"]] if n > 1 else [t["first"]]
    fade = t["fade"]
    total = sum(durs) - fade * (n - 1)

    cmd = [ffmpeg, "-y", "-loglevel", "error"]
    for c, d in zip(cards, durs):
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(c)]
    cmd += ["-i", str(MUSIC_DIR / track["file"])]

    parts = []
    for i in range(n):
        parts.append(
            f"[{i}:v]split[a{i}][b{i}];"
            f"[a{i}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=160:steps=2,eq=brightness=-0.03[bg{i}];"
            f"[b{i}]scale={W}:-2[fg{i}];"
            f"[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2-{t['lift']},fps={FPS},format=yuv420p,setsar=1[v{i}]")
    prev, offset = "v0", 0.0
    for i in range(1, n):
        offset += durs[i - 1] - fade
        parts.append(f"[{prev}][v{i}]xfade=transition=fade:duration={fade}:offset={offset:.3f}[x{i}]")
        prev = f"x{i}"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="instagram/ 아래 폴더 이름 (YYYY-MM-DD 또는 YYYY-MM-DD-weekly)")
    ap.add_argument("--out")
    ap.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    args = ap.parse_args()
    folder = INSTAGRAM_DIR / args.key
    cards = sorted(folder.glob("[0-9][0-9]_edit_h_*.png"))
    if not cards:
        sys.exit(f"✗ {folder} 에 카드 PNG 가 없습니다")
    track = pick_track(args.key)
    if not track:
        print("✗ assets/music/tracks.json 에 쓸 곡이 없습니다 — 릴스는 건너뜁니다(카드 게시는 그대로)")
        sys.exit(3)
    out = Path(args.out) if args.out else folder / "reel.mp4"
    timing = (load_config().get("instagram") or {}).get("reel_timing")
    total = build(cards, out, track, args.ffmpeg, timing)
    print(f"✓ {out} ({total:.1f}초, {out.stat().st_size // 1024}KB) — 음악: {track['title']} / {track['artist']} ({track['license']})")
    print(json.dumps({"reel": str(out), "track": track}, ensure_ascii=False))


if __name__ == "__main__":
    main()
