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


def load_config():
    return json.loads((AUTOMATION / "config.json").read_text(encoding="utf-8"))


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
