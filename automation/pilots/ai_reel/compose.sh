#!/bin/bash
# AI 릴스 시험판 편집(2판) — AI 영상(15초)에서 평온한 첫 0.5초와 마지막 장면의 늘어지는 2초(11~13초)를 잘라
# 충격 장면으로 바로 시작하고, 글자 4장(시간대별)·끝 화면 2초를 얹고, 소리 크기를 -14 LUFS 로 맞춘다.
# 1판(17초)은 바이럴 예측에서 훅 33(일반 릴스 36)·지속 96(90) — 첫 0.5초가 평온해 훅이 약했고, 11~12초에 딴생각 지표가 올랐다.
# 사용: compose.sh <ai_video.mp4> <overlay_dir> <out.mp4>  (컷 위치는 10/31 영상 기준: 3.04·7.33·9.54초)
set -euo pipefail
IN="$1"; OV="$2"; OUT="$3"
ffmpeg -v error -y -i "$IN" -i "$OV/a_hook.png" -i "$OV/b_sell.png" -i "$OV/c_sidecar.png" -i "$OV/d_check.png" \
  -loop 1 -t 2.0 -framerate 30 -i "$OV/z_end.png" -f lavfi -t 2.0 -i "anullsrc=r=48000:cl=stereo" \
  -filter_complex "\
[0:v]split[va][vb];\
[va]trim=0.5:11.0,setpts=PTS-STARTPTS,scale=1080:1920:flags=lanczos,setsar=1[s1];\
[vb]trim=13.0:15.0,setpts=PTS-STARTPTS,scale=1166:2074:flags=lanczos,crop=1080:1920,setsar=1[s2];\
[s1][s2]concat=n=2:v=1:a=0,fps=30[v0];\
[v0][1:v]overlay=0:0:enable='between(t,0,2.54)'[v1];\
[v1][2:v]overlay=0:0:enable='between(t,2.54,5.8)'[v2];\
[v2][3:v]overlay=0:0:enable='between(t,5.8,9.04)'[v3];\
[v3][4:v]overlay=0:0:enable='between(t,9.04,12.5)'[vm];\
[5:v]fps=30,format=yuv420p,setsar=1,fade=t=in:st=0:d=0.25[ve];\
[0:a]asplit[aa][ab];\
[aa]atrim=0.5:11.0,asetpts=PTS-STARTPTS,afade=t=out:st=10.46:d=0.04[a1];\
[ab]atrim=13.0:14.97,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.04[a2];\
[a1][a2]concat=n=2:v=0:a=1,aresample=48000,loudnorm=I=-14:TP=-1.5:LRA=11,apad=whole_dur=12.5,atrim=0:12.5,afade=t=out:st=12.0:d=0.5[am];\
[6:a]aformat=sample_rates=48000:channel_layouts=stereo[ae];\
[vm]trim=0:12.5,setpts=PTS-STARTPTS[vmt];\
[vmt][am][ve][ae]concat=n=2:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -profile:v high -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$OUT"
