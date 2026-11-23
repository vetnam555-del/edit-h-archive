# 3D 아이콘 — 카드 소식 그림(2026-11-25 호~, `cards.CARDS_V4_FROM`)

운영자 11/23 '카드뉴스 소스 퀄리티가 낮다' → '클로드로만 실행은 못 해?' — 힉스필드(크레딧) 없이, 소식마다 3D 아이콘 2~3개 + 우리 3D H 로 장면을 만든다.

- 출처: Microsoft **Fluent Emoji** 3D (https://github.com/microsoft/fluentui-emoji) — **MIT 라이선스**(상업적 사용·수정 가능, 저작권 표시: Copyright (c) Microsoft Corporation).
- 파일: `{이름}_3d.png`(256px). `index.json` = 이름 → 고를 때 쓰는 한국어 주제어.
- 쓰는 법: `content/{날짜}.json` 의 `cards.issues[i].icons` 에 이름 2~3개(첫째가 가장 크게, '5가지 한눈에' 줄 아이콘도 첫째). RUNBOOK `cards.issues` 칸.
- 더하기: 같은 저장소의 `assets/{Name}/3D/{name}_3d.png` 를 받아 여기에 두고 index.json 에 한 줄. 사람 얼굴 이모지·국기·상표 모양은 넣지 않는다.
