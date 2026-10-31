"""AI 릴스 시험판(2026-11-01, 10/31 호) — 영상 위에 얹을 글자(투명 PNG)와 끝 화면.

AI 영상에는 글자·숫자를 그리게 하지 않고(틀리게 그린다), 확인된 숫자는 여기서 우리 글꼴로 얹는다.
숫자는 content/2026-10-31.json(출처 3곳)에서 그대로 옮겼다. 사용: python3 automation/pilots/ai_reel/overlays.py <출력 폴더>
정규 파이프라인이 아니다 — E19(references.md 다음 실험 후보)가 승인되면 build 단계로 옮긴다."""
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
from edith.fonts import font_css  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
SHOT = ROOT / "automation" / "screenshot.cjs"
FACE = (ROOT / "assets" / "mascot" / "profile.png").as_uri()

BASE = """<!doctype html><html><head><meta charset="utf-8"><style>
{fonts}
html,body{{margin:0;width:1080px;height:1920px;background:transparent;font-family:'Pretendard',sans-serif;word-break:keep-all}}
.shade{{position:absolute;left:0;right:0;top:0;height:1000px;background:linear-gradient(180deg,rgba(0,0,0,.50) 0%,rgba(0,0,0,.30) 55%,rgba(0,0,0,0) 100%)}}
.top{{position:absolute;left:0;right:0;top:118px;text-align:center}}
.mark{{display:inline-flex;align-items:center;gap:14px;font-weight:850;font-size:40px;letter-spacing:-1px;color:#fff;
  text-shadow:0 2px 14px rgba(0,0,0,.55)}}
.mark .dot{{color:#FF5233}}
.ai{{font-weight:700;font-size:24px;letter-spacing:0;color:#fff;background:rgba(0,0,0,.42);border:1.5px solid rgba(255,255,255,.55);
  padding:6px 14px;border-radius:999px;text-shadow:none}}
.cap{{position:absolute;left:70px;right:150px;top:{top}px}}
.kick{{display:inline-block;font-weight:700;font-size:34px;color:#fff;background:rgba(0,0,0,.55);padding:8px 18px;border-radius:12px;margin-bottom:18px}}
.main{{font-weight:850;font-size:{size}px;line-height:1.22;letter-spacing:-2px;color:#fff;
  text-shadow:0 4px 18px rgba(0,0,0,.75),0 0 3px rgba(0,0,0,.9)}}
.hl{{background:#FF5233;color:#111;padding:0 12px;border-radius:12px;text-shadow:none;box-decoration-break:clone;-webkit-box-decoration-break:clone}}
.sub{{margin-top:20px;font-weight:650;font-size:38px;line-height:1.4;color:#fff;text-shadow:0 3px 14px rgba(0,0,0,.8),0 0 3px rgba(0,0,0,.9)}}
</style></head><body>
<div class="shade"></div>
<div class="top"><span class="mark"><span>EDIT H<span class="dot">.</span></span><span class="ai">AI로 만든 영상</span></span></div>
{body}
</body></html>"""

CAPS = {
    "a_hook": dict(top=300, size=96, body='<div class="kick">10월 30일 코스피</div><div class="main"><span class="hl">3.48%</span> 급락,<br>사이드카<br>또 울렸다고?</div>'),
    "b_sell": dict(top=300, size=84, body='<div class="main">외국인이 하루에<br><span class="hl">1조6000억원</span><br>넘게 팔았어요</div><div class="sub">장중 5599까지 · SK하이닉스 -7.08%</div>'),
    "c_sidecar": dict(top=300, size=84, body='<div class="main"><span class="hl">사이드카</span> =<br>프로그램 매도<br>5분 멈춤</div><div class="sub">오전 10시 4분 발동 · 11거래일 만</div>'),
    "d_check": dict(top=300, size=80, body='<div class="kick">그래서 나는?</div><div class="main">팔기 전에,<br>내 계좌가 <span class="hl">반도체 두 종목</span>에<br>얼마나 몰려 있는지부터</div>'),
}

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
  <div class="line">2030의 아침을 편집합니다</div>
  <div class="sub">경제부터 트렌드까지, 매일 아침 8시 30분<br>숫자·출처 전문은 프로필 링크 뉴스레터에서</div>
  <div class="btn">팔로우하고 내일 아침에 받기</div>
</div>
<div class="note">AI로 만든 영상이에요. 숫자는 기사 2곳 이상에서 확인했어요<br>(10월 30일 한국거래소 마감 기준)</div>
</body></html>"""


def shot(html, out, transparent):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "p.html"
        p.write_text(html, encoding="utf-8")
        r = subprocess.run(["node", str(SHOT), str(p), str(out), "1080", "1920"] + (["--transparent"] if transparent else []),
                           check=True, capture_output=True, text=True)
    info = json.loads(r.stdout.strip().splitlines()[-1])
    assert "Pretendard" in info["fonts"], info
    print("  ✓", out.name)


fonts = font_css()
for name, c in CAPS.items():
    shot(BASE.format(fonts=fonts, top=c["top"], size=c["size"], body=f'<div class="cap" style="top:{c["top"]}px">{c["body"]}</div>'),
         OUT / f"{name}.png", True)
shot(END.format(fonts=fonts, face=FACE), OUT / "z_end.png", False)
