"""카드 렌더링용 폰트 준비.

컨테이너에는 한글 폰트가 없어서, npm 레지스트리(클라우드 환경에서 항상 열려 있음)에서 받아
~/.cache/edit-h-fonts 에 풀어 둔다. 저장소에 수 MB 바이너리를 넣지 않기 위해서다.
- Pretendard Variable: 카드 전체 (OFL). 최신 양식(VOL.092)은 Pretendard 하나만 쓴다.
"""
import os
import re
import subprocess
import tarfile
from pathlib import Path

CACHE = Path(os.environ.get("EDITH_FONT_CACHE", Path.home() / ".cache" / "edit-h-fonts"))
PRETENDARD = ("pretendard", "1.3.9")
NOTO_SERIF = ("@fontsource/noto-serif-kr", "5.3.0")
SERIF_WEIGHTS = ("700", "900")


def _pack(name, version, dest):
    dest.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(
        ["npm", "pack", f"{name}@{version}", "--pack-destination", str(dest), "--silent"],
        check=True, capture_output=True, text=True,
    )
    return dest / out.stdout.strip().splitlines()[-1]


def _ensure_pretendard():
    target = CACHE / "PretendardVariable.woff2"
    if not target.exists():
        tgz = _pack(*PRETENDARD, CACHE / "tmp")
        with tarfile.open(tgz) as tf:
            member = tf.getmember("package/dist/web/variable/woff2/PretendardVariable.woff2")
            target.write_bytes(tf.extractfile(member).read())
        tgz.unlink()  # 70MB 짜리 원본 패키지는 필요한 파일만 꺼내고 지운다
    return target


def _ensure_serif():
    base = CACHE / "noto-serif-kr"
    if not (base / f"{SERIF_WEIGHTS[-1]}.css").exists():
        tgz = _pack(*NOTO_SERIF, CACHE / "tmp")
        (base / "files").mkdir(parents=True, exist_ok=True)
        with tarfile.open(tgz) as tf:
            for m in tf.getmembers():
                name = m.name.removeprefix("package/")
                keep_css = name in {f"{w}.css" for w in SERIF_WEIGHTS}
                keep_font = name.startswith("files/") and name.endswith(".woff2") and any(
                    f"-{w}-normal" in name for w in SERIF_WEIGHTS)
                if keep_css or keep_font:
                    (base / name).write_bytes(tf.extractfile(m).read())
        tgz.unlink()
    return base


def font_css(serif=False):
    """카드 HTML 에 그대로 넣을 @font-face 블록(file:// 절대경로). serif=True 면 Noto Serif KR 도 넣는다."""
    pre = _ensure_pretendard()
    css = [
        "@font-face{font-family:'Pretendard';font-weight:45 920;font-style:normal;"
        f"src:url('{pre.as_uri()}') format('woff2-variations'),url('{pre.as_uri()}') format('woff2');}}"
    ]
    if not serif:
        return "\n".join(css)
    base = _ensure_serif()
    for w in SERIF_WEIGHTS:
        text = (base / f"{w}.css").read_text(encoding="utf-8")
        # woff 대체 소스는 풀지 않았으므로 woff2 만 남기고, 상대경로를 절대 file:// 로 바꾼다
        text = text.replace("url(./files/", f"url({(base / 'files').as_uri()}/")
        text = re.sub(r",\s*url\([^)]*\.woff\) format\('woff'\)", "", text)
        css.append(text)
    return "\n".join(css)
