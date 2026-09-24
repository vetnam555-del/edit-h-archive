"""경로·설정·날짜·인라인 마크업 등 모든 모듈이 같이 쓰는 것들."""
import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION = ROOT / "automation"
CONTENT_DIR = ROOT / "content"
INSTAGRAM_DIR = ROOT / "instagram"
MANIFEST = ROOT / "manifest.json"
INDEX = ROOT / "index.html"

KST = dt.timezone(dt.timedelta(hours=9))
WEEKDAYS = "월화수목금토일"
WEEKDAYS_EN = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def image_size(path):
    """JPEG·PNG 의 (가로, 세로) 픽셀 — 이미지 라이브러리 없이 파일 머리만 읽는다. 모르는 형식이면 None."""
    b = Path(path).read_bytes()
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
    if b[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    return None


def cover_photo_problem(rel_path):
    """표지 사진이 1080×1350 을 꽉 채울 때 10% 넘게 늘어나면(흐려지면) 이유를 돌려준다. 문제 없으면 None."""
    size = image_size(ROOT / rel_path)
    if not size:
        return f"{rel_path}: JPEG·PNG 가 아니거나 크기를 읽을 수 없습니다"
    w, h = size
    scale = max(1080 / w, 1350 / h)
    if scale > 1.1:
        return (f"{rel_path}: {w}×{h} 라서 표지(1080×1350)를 채우려면 {scale:.2f}배로 늘려야 해 흐려집니다 — "
                f"세로 1350px·가로 1080px 이상인 사진을 쓰세요(fetch_photo.py 는 이 기준으로 고릅니다)")
    return None


def load_config():
    return json.loads((AUTOMATION / "config.json").read_text(encoding="utf-8"))


def send_time_ko(t):
    """'09:00' → '오전 9시', '08:30' → '오전 8시 30분' (뉴스레터·카드 문구용)."""
    h, m = map(int, t.split(":"))
    ampm, h12 = ("오전", h) if h < 12 else ("오후", h - 12 if h > 12 else 12)
    return f"{ampm} {h12}시" + (f" {m}분" if m else "")


def now_kst():
    return dt.datetime.now(KST)


def parse_date(s):
    return dt.date.fromisoformat(s)


def weekday_ko(d):
    return WEEKDAYS[d.weekday()]


def esc(s):
    return html.escape(str(s), quote=True)


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ACCENT = re.compile(r"==(.+?)==")


def md(text, bold_style="", accent_style=""):
    """본문용 최소 마크업: **굵게**, ==강조색==, 줄바꿈(\\n).

    HTML 은 먼저 이스케이프하므로 JSON 에 태그를 직접 넣어도 그대로 글자로 보인다.
    """
    out = esc(text)
    b_attr = f' style="{bold_style}"' if bold_style else ""
    a_attr = f' style="{accent_style}"' if accent_style else ""
    out = _BOLD.sub(lambda m: f"<b{b_attr}>{m.group(1)}</b>", out)
    out = _ACCENT.sub(lambda m: f"<span{a_attr}>{m.group(1)}</span>", out)
    return out.replace("\n", "<br>")


def plain(text):
    """마크업 기호를 떼어낸 순수 텍스트(메타 태그·캡션용)."""
    text = _BOLD.sub(r"\1", str(text))
    text = _ACCENT.sub(r"\1", text)
    return text.replace("\n", " ")


def source_label(sources):
    """'세계일보·올리브영 09.14' 형태. 날짜는 마지막 출처 기준."""
    names = "⁠·⁠".join(s["name"] for s in sources)
    date = sources[-1].get("date", "") if sources else ""
    return f"{names} {date}".strip()
