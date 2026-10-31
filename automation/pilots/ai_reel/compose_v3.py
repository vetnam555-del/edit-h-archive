#!/usr/bin/env python3
"""AI 릴스 3판(대사·목소리·배경음악) 편집 — 2026-11-01 운영자 "목소리랑 대사가 없잖아 … 노래나 배경음도 전혀 없네".

레퍼런스(힉스필드 장면 분석: 스튜디오 스틸컷 'AI 병맛 로판' EP.2, 'AI 숏 드라마 랜턴 공작' EP.1)는 1~3초마다 대사·속마음이 나오고,
배경음악이 장면 감정에 따라 바뀌며(긴장 → 추격 → 정적 → 반전), 반전 직전에 음악을 끊는다. 1·2판은 대사 0·음악 거의 0이었다.

소리 구성(17.1초):
- 목소리: H = Qwen Audio TTS 'Hana'(지시문으로 감정), 로봇 경찰 = ElevenLabs v4 'Knox' + 금속 울림. 음성 인식으로 대사가 그대로 들리는지 확인했다.
- 배경음악: 추격곡(0~5.9초) → 사이드카 정지 순간 음악을 끊고 사이렌·시계 소리만(5.9~9.1초) → 차분한 아침곡(9.1초~끝).
  음악은 Seedance 2.5 로 소리만 쓰려고 만든 짧은 영상에서 뽑았다(악기만, 말소리 없음 확인).
- 효과음: 원래 AI 영상의 소리(폰 진동·엔진·사이렌·시계)를 줄여서 깐다. 목소리가 나오면 음악이 자동으로 작아진다(사이드체인).
사용: python3 automation/pilots/ai_reel/compose_v3.py <AI 영상 1080p 원본.mp4> <글자 PNG 폴더> <출력.mp4>
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "2026-10-31" / "stems"
SRC, OV, OUT = sys.argv[1], Path(sys.argv[2]), sys.argv[3]

TRIM0 = 0.4            # 평온한 첫 0.4초를 자른다(충격 장면으로 바로 시작)
MAIN = 15.04 - TRIM0   # 14.64초
END = 2.5              # 끝 화면
TOTAL = MAIN + END
CAPS = [("a_hook.png", 0.0, 2.64), ("b_sell.png", 2.64, 5.9), ("c_sidecar.png", 5.9, 9.14), ("d_check.png", 9.14, MAIN)]
# (파일, 시작 초, 빠르기, 로봇 효과) — 각 줄이 장면 길이에 맞게 빠르기를 정했다(1.10~1.25배, 쇼츠 대사 속도)
VOICES = [("v1_h_shock.mp3", 0.05, 1.25, False), ("v2_h_sell.mp3", 2.80, 1.15, False), ("v3_robot_stop.mp3", 5.95, 1.18, True),
          ("v4_h_check.mp3", 9.35, 1.10, False), ("v5_h_bye.mp3", 14.80, 1.25, False)]
MUSIC = [("m1_chase.m4a", 0.0, 5.9, 0.0, 0.25), ("m2_morning.m4a", 9.14, TOTAL - 9.14, 0.4, 0.7)]  # (파일, 시작, 길이, 페이드인, 페이드아웃)

inputs = ["-i", SRC] + sum((["-i", str(OV / c[0])] for c in CAPS), []) + ["-loop", "1", "-t", str(END), "-framerate", "30", "-i", str(OV / "z_end.png")]
vi = len(CAPS) + 2
inputs += sum((["-i", str(HERE / v[0])] for v in VOICES), [])
mi = vi + len(VOICES)
inputs += sum((["-i", str(HERE / m[0])] for m in MUSIC), [])

f = [f"[0:v]trim={TRIM0}:15.04,setpts=PTS-STARTPTS,fps=30,setsar=1[v0]"]
last = "v0"
for k, (_, a, b) in enumerate(CAPS):
    f.append(f"[{last}][{k + 1}:v]overlay=0:0:enable='between(t,{a},{b})'[vc{k}]")
    last = f"vc{k}"
f.append(f"[{last}]trim=0:{MAIN},setpts=PTS-STARTPTS[vm]")
f.append(f"[{len(CAPS) + 1}:v]fps=30,format=yuv420p,setsar=1,fade=t=in:st=0:d=0.25[ve]")
f.append("[vm][ve]concat=n=2:v=1:a=0[v]")
# 효과음(원래 AI 영상 소리): 로봇 대사(5.9~9.1초)는 사이렌에 묻히지 않게, 마지막 장면(9.1초~)은 아침곡과 겹치지 않게 줄인다
f.append(f"[0:a]atrim={TRIM0}:15.0,asetpts=PTS-STARTPTS,aresample=48000,volume='if(lt(t,5.9),0.55,if(lt(t,9.14),0.22,0.25))':eval=frame,"
         f"apad=whole_dur={TOTAL},atrim=0:{TOTAL}[sfx]")
vl = []
for k, (_, start, tempo, robot) in enumerate(VOICES):
    chain = (f"[{vi + k}:a]aresample=48000,aformat=channel_layouts=stereo,"
             "silenceremove=start_periods=1:start_threshold=-40dB,areverse,silenceremove=start_periods=1:start_threshold=-40dB,areverse,"
             f"atempo={tempo},highpass=f=80,acompressor=threshold=0.1:ratio=3:attack=5:release=80,loudnorm=I=-15:TP=-2")
    if robot:
        chain += ",aecho=0.5:0.3:7:0.15,highpass=f=120,lowpass=f=7500,volume=1.6"  # 금속 울림은 살짝만(대사가 묻히지 않게)
    f.append(chain + f",adelay={int(start * 1000)}:all=1[vo{k}]")
    vl.append(f"[vo{k}]")
f.append(f"{''.join(vl)}amix=inputs={len(vl)}:normalize=0,apad=whole_dur={TOTAL},atrim=0:{TOTAL},asplit=2[voice][key]")
ml = []
for k, (_, start, dur, fin, fout) in enumerate(MUSIC):
    fade = (f",afade=t=in:st=0:d={fin}" if fin else "") + f",afade=t=out:st={dur - fout:.2f}:d={fout}"
    f.append(f"[{mi + k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{dur},asetpts=PTS-STARTPTS,"
             f"loudnorm=I=-20:TP=-3{fade},adelay={int(start * 1000)}:all=1[mu{k}]")
    ml.append(f"[mu{k}]")
f.append(f"{''.join(ml)}amix=inputs={len(ml)}:normalize=0,apad=whole_dur={TOTAL},atrim=0:{TOTAL}[music]")
f.append("[music][key]sidechaincompress=threshold=0.04:ratio=5:attack=15:release=350:makeup=1[ducked]")
f.append("[voice][ducked][sfx]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")

cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{TOTAL}", OUT]
subprocess.run(cmd, check=True)
print("ok", OUT, f"{TOTAL:.2f}s")
