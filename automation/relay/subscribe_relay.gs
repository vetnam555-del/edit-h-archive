/**
 * EDIT H 구독 즉시 반영 — 운영자 Gmail 에서 도는 Google Apps Script(2026-10-09).
 *
 * 구독 페이지(Formspree)에 이메일을 적으면 Formspree 가 운영자 Gmail 로 '[EDIT H] 신규 구독 신청' 알림을 보낸다.
 * 이 스크립트가 1분마다 그 알림을 찾아, GitHub 의 'Sync EDIT H subscribers' 작업을 바로 실행시킨다.
 * 그 작업이 명단(Secret)에 넣고 환영 메일 + 가장 최근 호를 보낸다 — 신청 뒤 보통 2~3분.
 * 수신 거부 알림도 같은 식으로 바로 반영한다.
 *
 * 이 스크립트는 메일을 읽고 '읽음 표시' 대신 라벨(edith-relayed)만 붙인다. 주소는 어디에도 보내지 않는다
 * (GitHub 작업이 Gmail 에서 직접 읽는다). 비밀값은 코드에 없다 — 스크립트 속성 GH_TOKEN 에만 넣는다.
 *
 * 설정(10분, automation/OWNER_TODO.md '구독 즉시 반영'):
 *   1. https://script.google.com → 새 프로젝트 → 이 파일 내용을 그대로 붙여넣고 저장.
 *   2. GitHub → Settings → Developer settings → Fine-grained tokens → 새 토큰:
 *      저장소 edit-h-archive 만, 권한 Actions: Read and write 만. 만료일은 1년.
 *   3. Apps Script 왼쪽 ⚙ 프로젝트 설정 → 스크립트 속성 → GH_TOKEN = (2의 토큰). 채팅에 붙여넣지 말 것.
 *   4. 편집기에서 relay 함수를 한 번 실행 → Gmail 권한 허용.
 *   5. 왼쪽 ⏰ 트리거 → 트리거 추가 → relay, 시간 기반, 분 단위 타이머, 1분마다.
 */
const REPO = 'vetnam555-del/edit-h-archive';
const WORKFLOW = 'sync-subscribers.yml';
const QUERY = '(subject:"[EDIT H] 신규 구독 신청" OR subject:"[EDIT H] 수신 거부 신청") newer_than:2d';
const LABEL = 'edith-relayed';

function relay() {
  const label = GmailApp.getUserLabelByName(LABEL) || GmailApp.createLabel(LABEL);
  const threads = GmailApp.search(QUERY + ' -label:' + LABEL, 0, 20);
  if (!threads.length) return;
  const token = PropertiesService.getScriptProperties().getProperty('GH_TOKEN');
  if (!token) throw new Error('스크립트 속성 GH_TOKEN 이 없습니다 — 설정 3단계');
  const res = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: {Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json'},
    payload: JSON.stringify({ref: 'main', inputs: {dry_run: 'false'}}),
  });
  if (res.getResponseCode() !== 204) {
    // 실패하면 라벨을 붙이지 않아 1분 뒤 다시 시도한다(매시간 예비 실행도 있다). 실패 알림은 Apps Script 가 메일로 보낸다.
    throw new Error('GitHub 실행 요청 실패: HTTP ' + res.getResponseCode());
  }
  threads.forEach(function (t) { t.addLabel(label); });
}
