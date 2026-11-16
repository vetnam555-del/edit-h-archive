"""AI 릴스 대사 녹음 — 무료 CosyVoice 3 로 지금까지의 Hana 목소리를 그대로 따라 한다(2026-11-16~).

운영자 11/15 밤: "깃허브에 있는 무료 목소리로 하는데 그동안 했던 목소리랑 똑같이" → 시안 2차(같은 날 녹음 3줄을 참고로 들려준 것)를 듣고
"첫 번째 목소리(Hana)는 똑같네, 이걸로 릴스 절차에 넣어 줘" → 11/16 낮 Knox 시안을 듣고 "Knox 도 똑같네, 무료 복제로 바꿔 줘"(CLONE_WHO).

어떻게: CosyVoice 3(Apache-2.0, 그래픽카드 없이 CPU)로 참고 녹음(REFS — 저장소에 이미 있는 지난 릴스 녹음)을 들려주고 대사를 읽힌다.
모델을 다시 학습시키지 않는다(참고만 — 힉스필드 약관은 '생성물로 AI 모델을 학습·미세조정하지 말 것'). 한 줄마다 후보 N개를 만들어
① 받아쓰기(qa.py 의 heard_ratio, 95% 이상) ② 참고 녹음과 목소리가 얼마나 같은가(campplus 화자 임베딩 코사인)로 가장 나은 것을 고른다.
11/16 시험: 원래 Hana 녹음끼리 0.78~0.84, 고른 복제 0.85 — 숫자로는 같은 사람.

사용:
  python3 automation/pilots/ai_reel/clone_voice.py setup                 # 처음 한 번(새 세션마다) — 5~10분, ~/.cache/edith-voice
  python3 automation/pilots/ai_reel/clone_voice.py <brief.json>          # Hana·Knox 줄을 녹음(이미 있는 줄은 건너뜀)
  python3 automation/pilots/ai_reel/clone_voice.py <brief.json> --only i4 --force   # 한 줄만 다시
  python3 automation/pilots/ai_reel/clone_voice.py <brief.json> --check  # 무엇을 녹음할지·준비됐는지만
녹음 결과 모양은 tts.py·힉스필드 녹음과 같다(mp3 24kHz 모노, 앞뒤 무음 자름) — episode.py·qa.py 는 그대로.
"""
import argparse
import re
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tts  # noqa: E402  (load_lines·_polish·probe·tempo_hint·fmt_table — 줄 배정 규칙을 같이 쓴다)

HOME = Path(os.environ.get("EDITH_VOICE_HOME") or Path.home() / ".cache" / "edith-voice")
COSY_REPO = "https://github.com/FunAudioLLM/CosyVoice.git"
COSY_COMMIT = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"      # 11/16 시험한 판
MODEL_ID = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"            # Apache-2.0
MODEL_FILES = ["cosyvoice3.yaml", "config.json", "configuration.json", "campplus.onnx", "hift.pt", "flow.pt", "llm.pt",
               "speech_tokenizer_v3.onnx", "CosyVoice-BlankEN/*"]   # 쓰지 않는 batch·trt·rl 파일은 받지 않는다(약 5GB)
REQ = HERE / "voice_clone_requirements.txt"
PROMPT = "You are a helpful assistant.<|endofprompt|>"

# 참고 녹음 — 운영자가 '똑같다'고 한 시안(11/16 1시)이 쓴 것. 바꾸면 운영자에게 다시 들려준다.
REFS = {
    "hana": [("2026-11-13", "stems/i3_glasses.mp3"), ("2026-11-13", "stems/i4_chicken.mp3"), ("2026-11-13", "stems/i5_map.mp3")],
    # Knox — 11/16 운영자 'Knox 도 똑같네'. 5줄 조합이 두 시험 문장 모두에서 가장 고르게 나았다(받아쓰기 97·100%, 같음 0.82·0.73 —
    # 힉스필드 Knox 녹음끼리도 날마다 0.59~0.79 로 흔들린다).
    "knox": [("2026-11-03", "stems/i3_binance.mp3"), ("2026-11-04", "stems/i1_coupang.mp3"), ("2026-11-06", "stems/i1_nasdaq.mp3"),
             ("2026-11-08", "stems/i1_hack.mp3"), ("2026-11-12", "stems/i1_med.mp3")],
}
CLONE_WHO = ("hana", "knox")   # 둘 다 복제(Hana 11/16 새벽, Knox 11/16 낮 운영자 '똑같네') — 힉스필드 목소리는 복제 준비가 안 된 날의 대체
N_CANDIDATES = 3
HEARD_MIN = 0.95          # qa.py STEM_MIN 과 같다
# 억양 폭(줄 안 음높이 변화 — 반음, 10~90 백분위) 하한. 11/16 운영자 '높낮이·강조·악센트로 진짜 아나운서처럼 생생하게'.
# 원래 힉스필드 녹음: Hana 6~18·Knox 7~13반음(11/12·11/13·11/16 측정) — 그보다 좁으면 단조롭다.
RANGE_MIN = {"hana": 8.0, "knox": 7.0}
EMPH = re.compile(r"</?strong>")   # 강세 표시 — tts 칸에서 가장 센 낱말을 <strong>…</strong> 로 감싼다(CosyVoice 가 그 낱말을 세게 읽는다)
DEFAULT_LEN = 20.0                 # 목소리 트랙 길이 기본값(영상 20초)


def plain(say):
    """강세 표시를 지운 원고 — 받아쓰기·숫자 검사용."""
    return re.sub(r"\s{2,}", " ", EMPH.sub("", say or "")).strip()


def venv_python():
    return HOME / "venv" / "bin" / "python"


def ready():
    """setup 이 끝났나 — (True/False, 이유)."""
    if not (HOME / "READY").exists():
        return False, f"준비 안 됨 — `python3 {Path(__file__).relative_to(HERE.parents[2])} setup` 먼저(5~10분)"
    return True, (HOME / "READY").read_text().strip()


def ref_items(who):
    """참고 녹음 [(경로, 원고)] — 원고는 그날 brief 의 tts(없으면 text), '[excited]' 표시를 지운다."""
    out = []
    for day, f in REFS[who]:
        brief = json.loads((HERE / day / "brief.json").read_text(encoding="utf-8"))
        v = next((v for v in brief.get("voices") or [] if v.get("file") == f), None)
        if v is None:
            raise SystemExit(f"참고 녹음 {day}/{f} 가 그날 brief.json voices 에 없다")
        out.append((str(HERE / day / f), tts.strip_tags(v.get("tts") or v.get("text") or "")))
    return out


def pick(cands, heard_min=HEARD_MIN, range_min=0.0):
    """후보 [{'path','heard','cos','range'}] → 고른 것.
    ① 받아쓰기 기준을 넘고 억양 폭도 하한을 넘는 것 중 목소리가 가장 같은 것
    ② 없으면 받아쓰기만 넘는 것 중 억양 폭이 가장 넓은 것(생생함 먼저 — 11/16 운영자)
    ③ 그것도 없으면 받아쓰기가 가장 나은 것(같으면 목소리)."""
    ok = [c for c in cands if c["heard"] >= heard_min]
    lively = [c for c in ok if c.get("range", 99) >= range_min]
    if lively:
        return max(lively, key=lambda c: (c["cos"], c["heard"]))
    if ok:
        return max(ok, key=lambda c: (c.get("range", 0), c["cos"]))
    return max(cands, key=lambda c: (c["heard"], c["cos"]))


def track_voices(brief, base, tmp, cap=None):
    """목소리 트랙에 쓸 줄 목록 — 완성본(episode.py compose)과 똑같이 대사 속 0.25초 넘는 쉼을 0.2초로 줄인 파일로 바꾼다
    (11/16 Codex: 줄이지 않으면 쉼 뒤의 말이 완성본에서 0.3초쯤 먼저 나와 트랙에 맞춘 입 모양과 어긋난다). cap 은 시험용(파일 → 줄인 파일)."""
    import episode
    voices = [dict(v) for v in brief.get("voices") or []]
    if not episode.pause_cap_on(brief):
        return voices
    cap = cap or (lambda src, dst: episode.cap_pauses(src, dst)[0])
    for k, v in enumerate(voices):
        v["file"] = str(cap(Path(base) / v["file"], Path(tmp) / f"track_voice{k}.wav"))
    return voices


def track_cmd(voices, base, out, total=DEFAULT_LEN):
    """목소리 트랙(립싱크용 — 영상 생성에 reference_audio 로 준다) ffmpeg 명령. voices 는 brief 의 voices(file·start·tempo).
    줄마다 tempo 를 적용하고 start 초에 놓아 total 초 모노 24kHz mp3 로 — episode.py 가 완성본에 놓는 자리와 같다."""
    if not voices:
        raise ValueError("voices 가 비었다")
    ins, fc = [], []
    for k, v in enumerate(voices):
        ins += ["-i", str(Path(base) / v["file"])]
        fc.append(f"[{k}:a]aresample=24000,aformat=channel_layouts=mono,atempo={float(v.get('tempo', 1.0))},"
                  f"adelay={int(round(float(v['start']) * 1000))}:all=1[v{k}]")
    fc.append("".join(f"[v{k}]" for k in range(len(voices))) +
              f"amix=inputs={len(voices)}:normalize=0,apad=whole_dur={total},atrim=0:{total}")
    return ["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-ac", "1", "-ar", "24000",
            "-c:a", "libmp3lame", "-b:a", "128k", str(out)]


def targets(lines, only=None, force=False, who=CLONE_WHO):
    """녹음할 줄 — 목소리가 who 에 들고, 이미 파일이 있으면 force 일 때만. only 는 파일 이름에 든 말(쉼표로 여럿)."""
    keys = [k.strip() for k in (only or "").split(",") if k.strip()]
    out = []
    for ln in lines:
        if ln["who"] not in who:
            continue
        if keys and not any(k in ln["file"] for k in keys):
            continue
        if ln["path"].exists() and not (force or keys):
            continue
        out.append(ln)
    return out


# ---------------------------------------------------------------- setup (system python)

def _run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd)[:160], flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def setup():
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
    if not Path(uv).exists():
        _run([sys.executable, "-m", "pip", "install", "-q", "uv"])
        uv = shutil.which("uv") or uv
    HOME.mkdir(parents=True, exist_ok=True)
    repo = HOME / "CosyVoice"
    if not (repo / ".git").exists():
        _run(["git", "clone", "-q", COSY_REPO, repo])
    _run(["git", "-C", repo, "checkout", "-q", COSY_COMMIT])
    _run(["git", "-C", repo, "submodule", "update", "-q", "--init", "--recursive"])
    py = venv_python()
    if not py.exists():
        _run([uv, "venv", "-q", "-p", "3.10", HOME / "venv"])
    pip = [uv, "pip", "install", "-q", "-p", py]
    _run(pip + ["torch==2.3.1", "torchaudio==2.3.1", "--index-url", "https://download.pytorch.org/whl/cpu"])
    _run(pip + ["-r", REQ])
    _run(pip + ["setuptools<70", "wheel"])                        # openai-whisper 빌드가 pkg_resources 를 찾는다
    _run(pip + ["--no-build-isolation", "openai-whisper==20231117"])
    _run([py, "-c", "from huggingface_hub import snapshot_download as s; "
          f"s({MODEL_ID!r}, local_dir={str(HOME / 'model')!r}, allow_patterns={MODEL_FILES!r})"])
    _run([py, "-c", "from faster_whisper import WhisperModel as W; W('small', device='cpu', compute_type='int8')"])
    (HOME / "READY").write_text(f"CosyVoice {COSY_COMMIT[:7]} · {MODEL_ID}\n")
    print("✓ 목소리 복제 준비 끝:", HOME)


# ---------------------------------------------------------------- worker (venv python)

def worker(job_path):
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    sys.path[:0] = [str(HOME / "CosyVoice"), str(HOME / "CosyVoice" / "third_party" / "Matcha-TTS")]
    import logging
    logging.disable(logging.WARNING)
    import numpy as np
    import torch
    import torchaudio
    from cosyvoice.cli.cosyvoice import AutoModel
    from faster_whisper import WhisperModel
    import qa
    import librosa
    torch.set_num_threads(os.cpu_count() or 4)
    cv = AutoModel(model_dir=str(HOME / "model"))
    asr = WhisperModel("small", device="cpu", compute_type="int8")

    def pitch_range(p):
        """줄 안 음높이 변화(반음, 10~90 백분위) — 클수록 높낮이가 살아 있다."""
        y, sr = librosa.load(p, sr=16000)
        f, _, _ = librosa.pyin(y, fmin=70, fmax=600, sr=sr)
        f = f[~np.isnan(f)]
        if len(f) < 5:
            return 0.0
        st = 12 * np.log2(f / np.median(f))
        return round(float(np.percentile(st, 90) - np.percentile(st, 10)), 1)

    def emb(p):
        e = cv.frontend._extract_spk_embedding(p).flatten().numpy()
        return e / np.linalg.norm(e)

    tmp = Path(job["tmp"])
    refs = {}
    for who, items in job["refs"].items():
        ins, fc = [], []
        for i, (p, _) in enumerate(items):
            ins += ["-i", p]
            fc.append(f"[{i}:a]aresample=24000,aformat=channel_layouts=mono,apad=pad_dur=0.25[a{i}]")
        fc.append("".join(f"[a{i}]" for i in range(len(items))) + f"concat=n={len(items)}:v=0:a=1")
        wav = tmp / f"ref_{who}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), str(wav)], check=True)
        mean = np.mean([emb(p) for p, _ in items], axis=0)
        refs[who] = (str(wav), " ".join(t for _, t in items), mean / np.linalg.norm(mean))
    results = []
    for ln in job["lines"]:
        wav, ptxt, ref_e = refs[ln["who"]]
        cands = []
        for s in range(1, job["n"] + 1):
            torch.manual_seed(s)
            out = [j["tts_speech"] for j in cv.inference_zero_shot(ln["say"], PROMPT + ptxt, wav, stream=False)]
            p = tmp / f"{Path(ln['file']).stem}_c{s}.wav"
            torchaudio.save(str(p), torch.cat(out, dim=1), cv.sample_rate)
            segs, _ = asr.transcribe(str(p), language="ko", beam_size=5)
            said = " ".join(x.text for x in segs).strip()
            cands.append({"path": str(p), "seed": s, "said": said, "range": pitch_range(str(p)),
                          "heard": round(qa.heard_ratio(plain(ln["say"]), said), 3), "cos": round(float(emb(str(p)) @ ref_e), 3)})
            c = cands[-1]
            print(f"  {ln['file']} 후보 {s}: 받아쓰기 {c['heard']:.0%} · 목소리 {c['cos']:.3f} · 억양 폭 {c['range']}반음 · '{said}'", flush=True)
        best = pick(cands, job["heard_min"], RANGE_MIN.get(ln["who"], 0.0))
        results.append({"file": ln["file"], "best": best, "cands": cands})
    Path(job["out"]).write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- main (system python)

def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "_worker":
        return worker(sys.argv[2])
    ap = argparse.ArgumentParser(description="AI 릴스 Hana 대사 녹음 — 무료 CosyVoice 3 로 원래 목소리를 따라 한다")
    ap.add_argument("episode", help="brief.json 또는 setup")
    ap.add_argument("--only", help="그 줄만 — 파일 이름에 든 말(쉼표로 여럿)")
    ap.add_argument("--force", action="store_true", help="이미 있어도 다시 녹음")
    ap.add_argument("--n", type=int, default=N_CANDIDATES, help=f"줄마다 후보 수(기본 {N_CANDIDATES})")
    ap.add_argument("--check", action="store_true", help="녹음하지 않고 무엇을 할지·준비됐는지만")
    ap.add_argument("--track", metavar="OUT.mp3", help="녹음을 다 한 뒤 목소리 트랙(립싱크용 reference_audio)을 만든다 — 녹음은 하지 않는다")
    a = ap.parse_args()
    if a.episode == "setup":
        return setup()
    if a.track:
        brief = json.loads(Path(a.episode).read_text(encoding="utf-8"))
        base = Path(a.episode).parent
        missing = [v["file"] for v in brief.get("voices") or [] if not (base / v["file"]).exists()]
        if missing:
            raise SystemExit("× 아직 녹음 안 된 줄: " + ", ".join(missing))
        trim = brief.get("trim")
        total = float(trim[1]) - float(trim[0]) if trim else DEFAULT_LEN
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(track_cmd(track_voices(brief, base, tmp), base, a.track, total), check=True)
        print(f"✓ 목소리 트랙 {a.track} — {total:.1f}초, 줄 {len(brief['voices'])}개(시작 초: "
              + ", ".join(f"{v['start']}" for v in brief["voices"]) + ")")
        return
    brief, base, lines = tts.load_lines(a.episode)
    todo = targets(lines, a.only, a.force)
    ok, why = ready()
    print(f"복제 준비: {'○' if ok else '×'} {why}")
    for who in CLONE_WHO:
        for p, t in ref_items(who):
            print(f"  참고({who}) {Path(p).relative_to(HERE)} — '{t}'")
    print(f"녹음할 줄 {len(todo)}개:", ", ".join(ln["file"] for ln in todo) or "없음")
    others = [ln["file"] for ln in lines if ln["who"] not in CLONE_WHO]
    if others:
        print("복제하지 않는 줄(힉스필드로):", ", ".join(others))
    if a.check or not todo:
        return
    if not ok:
        raise SystemExit("× " + why)
    for ln in todo:
        if tts.ROUGH.search(plain(ln["say"])):
            raise SystemExit(f"× {ln['file']} 원고에 숫자·영문이 남았다 — tts 칸에 한글 읽기로: '{ln['say']}'")
    with tempfile.TemporaryDirectory() as tmp:
        job = {"tmp": tmp, "out": str(Path(tmp) / "out.json"), "n": a.n, "heard_min": HEARD_MIN,
               "refs": {w: ref_items(w) for w in {ln["who"] for ln in todo}},
               "lines": [{"file": ln["file"], "who": ln["who"], "say": ln["say"]} for ln in todo]}
        Path(tmp, "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        subprocess.run([str(venv_python()), str(Path(__file__).resolve()), "_worker", str(Path(tmp, "job.json"))],
                       check=True, cwd=str(HERE))
        results = json.loads(Path(job["out"]).read_text(encoding="utf-8"))
        rows = []
        for ln, r in zip(todo, results):
            b = r["best"]
            ln["path"].parent.mkdir(parents=True, exist_ok=True)
            done = Path(tmp) / f"{Path(ln['file']).stem}_done.mp3"
            tts._polish(Path(b["path"]), done)
            shutil.move(str(done), str(ln["path"]))   # 다 만든 뒤에 바꾼다 — 실패해도 앞의 녹음이 남는다
            sec = tts.probe(ln["path"])[0]
            flag = "" if b["heard"] >= HEARD_MIN else " ← 받아쓰기 95% 미만: 말을 더 흔한 말로 바꿔 --only 로 다시"
            if b.get("range", 99) < RANGE_MIN.get(ln["who"], 0.0):
                flag += f" ← 억양 폭 {b.get('range')}반음 — 단조롭다: 가장 센 낱말을 <strong>…</strong> 로 감싸 --only 로 다시"
            rows.append((ln["file"], f"{sec:.2f}s" if sec else "?", f"{b['heard']:.0%}", f"{b['cos']:.3f}", f"{b.get('range')}반음",
                         tts.tempo_hint(sec, ln["slot"], ln.get("tempo", 1.0))[1] + flag))
        print("\n줄 · 길이 · 받아쓰기 · 목소리 같음(1에 가까울수록) · 억양 폭 · 칸")
        for r in rows:
            print("  " + " · ".join(str(x) for x in r))


if __name__ == "__main__":
    main()
