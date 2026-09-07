/** 독도 코리아 스쿨 — 시트 코드 v2
 *
 *  바뀐 것
 *   · 주간 명예의 전당 (월요일 0시 기준, 한국 시간)
 *   · 명예의 전당 — 이번 주 참여자를 최대 60명까지, 이름·국기·학교와 함께
 *   · 실시간 흐름 — ?live=1 로 방금 푼 사람 스무 명 (live.html 이 씁니다)
 *   · 학교 1·2·3등 — 초등·중등·고등, 해외는 참여가 생기면 나타납니다
 *   · 방금 다녀간 세 사람 — 이름과 국기를 상단 띠에 보냅니다
 *   · 진도 백업 — 별명#번호로 다른 기기에서 이어받습니다
 *   · 주간 자동 백업 — 기록은 지워지지 않고 탭으로 보관됩니다
 *
 *  올리는 법
 *   기존 Code.gs 내용을 전부 지우고 이것을 붙여넣습니다.
 *   배포 → 배포 관리 → 연필 → 버전 '새 버전' → 배포.
 *   주소는 그대로입니다. '새 배포'를 누르면 주소가 바뀌니 주의하십시오.
 */

const LOG   = '기록';
const PROG  = '진도';
const TZ    = 'Asia/Seoul';     // 월요일 0시를 한국 시간으로 자릅니다
const TOP_N  = 3;    // 학교 순위·최근 참여자
const ROLL_N = 60;   // 명예의 전당에 싣는 사람 수. 이름이 오르는 것 자체가 상입니다.

/* ───────────────────────── 받기 ───────────────────────── */

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.t === 'save') return saveProgress_(d);      // 진도 저장
    sheet_().appendRow([
      new Date(),
      String(d.nick || '').slice(0, 24),
      String(d.flag || ''),
      String(d.grade || ''),
      Number(d.qid) || 0,
      Number(d.ok) || 0,
      Number(d.run) || 0,
      Number(d.best) || 0,
      String(d.mode || ''),
      String(d.school || '').slice(0, 60),          // 학교 이름
      String(d.schoolCode || ''),                    // 학교 코드 · 집계의 열쇠
      String(d.schoolCat || '')                      // E 초등 · M 중등 · H 고등 · W 해외
    ]);
  } catch (err) { /* 한 줄이 실패해도 앱은 그대로 돌아갑니다 */ }
  return ContentService.createTextOutput('ok');
}

/* ───────────────────────── 보내기 ───────────────────────── */

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.load) return json_(loadProgress_(p.load));     // 진도 불러오기
  if (p.live) {                                        // 실시간 흐름 (live.html)
    const lc = CacheService.getScriptCache();
    const lh = lc.get('live1');
    if (lh && !p.fresh) return json_(JSON.parse(lh));
    const lo = live_();
    lc.put('live1', JSON.stringify(lo), 10);           // 10초 재사용
    return json_(lo);
  }
  const c = CacheService.getScriptCache();
  const hit = c.get('feed2');
  if (hit && !p.fresh) return json_(JSON.parse(hit));
  const out = build_();
  c.put('feed2', JSON.stringify(out), 60);            // 1분 재사용
  return json_(out);
}

/* 이번 주의 시작 — 월요일 0시 (한국 시간) */
function weekStart_() {
  const now = new Date();
  const day = Number(Utilities.formatDate(now, TZ, 'u'));   // 월=1 … 일=7
  const ymd = Utilities.formatDate(now, TZ, 'yyyy-MM-dd');
  const midnight = new Date(ymd + 'T00:00:00+09:00');
  return new Date(midnight.getTime() - (day - 1) * 86400000);
}

function build_() {
  const sh = sheet_();
  const last = sh.getLastRow();
  const base = { today: 0, people: 0, top: null, week: [], schools: {}, recent: [], weekOf: '' };
  if (last < 2) return base;

  /* 최근 2만 줄만 봅니다. 한 주치는 넉넉히 들어갑니다. */
  const from = Math.max(2, last - 19999);
  const rows = sh.getRange(from, 1, last - from + 1, 12).getValues();

  const wk = weekStart_();
  const today = Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd');
  base.weekOf = Utilities.formatDate(wk, TZ, 'yyyy-MM-dd');

  const person = {};   // 사람별 이번 주 맞힌 수
  const school = {};   // 학교별 맞힌 수
  const whoToday = {};
  let todayN = 0;

  rows.forEach(function (r) {
    const t = r[0];
    if (!(t instanceof Date)) return;

    if (Utilities.formatDate(t, TZ, 'yyyy-MM-dd') === today) {
      todayN++;
      const nk = String(r[1] || '').trim();
      if (nk) whoToday[nk] = 1;
    }
    if (t < wk) return;                               // 이번 주가 아니면 여기까지

    const nick = String(r[1] || '').trim();
    const run  = Number(r[6]) || 0;
    if (nick) {
      /* 순위는 이번 주에 맞힌 문제 수로 셉니다.
         최고 연속은 하루만 잘 풀면 그 주 내내 그대로라 매일 올 이유가 없습니다.
         누적은 오는 만큼 올라갑니다. 연속은 동점을 가르는 데만 씁니다. */
      const p = person[nick] ||
        (person[nick] = { nick: nick, correct: 0, run: 0, flag: '', school: '', days: {} });
      if (Number(r[5]) === 1) p.correct++;
      if (run > p.run) p.run = run;
      const fg = String(r[2] || '').trim();     // 국가 — 가장 최근 것을 씁니다
      if (fg) p.flag = fg;
      const sc = String(r[9] || '').trim();     // 학교 — 고른 사람만 이름 뒤에 붙습니다
      if (sc) p.school = sc;
      p.days[Utilities.formatDate(t, TZ, 'yyyy-MM-dd')] = 1;
    }

    const code = String(r[10] || '').trim();
    const cat  = String(r[11] || '').trim();
    if (code && cat && Number(r[5]) === 1) {          // 맞힌 것만 셉니다
      const k = cat + '|' + code;
      if (!school[k]) school[k] = { name: String(r[9] || '').trim(), cat: cat, correct: 0, who: {} };
      school[k].correct++;
      if (nick) school[k].who[nick] = 1;
    }
  });

  base.today  = todayN;
  base.people = Object.keys(whoToday).length;

  /* 방금 다녀간 세 사람 — 시트 아래쪽부터 거슬러 올라가며 서로 다른 별명을 셋 모읍니다.
     이번 주가 아니어도 됩니다. '지금 누가 하고 있다'를 보여 주는 줄이라 최신순이면 충분합니다. */
  const seenR = {};
  for (let i = rows.length - 1; i >= 0 && base.recent.length < TOP_N; i--) {
    const r = rows[i];
    if (!(r[0] instanceof Date)) continue;
    const nk = String(r[1] || '').trim();
    if (!nk || seenR[nk]) continue;
    seenR[nk] = 1;
    base.recent.push({ nick: nk, flag: String(r[2] || '').trim(),
                       min: Math.max(0, Math.round((Date.now() - r[0].getTime()) / 60000)) });
  }

  /* 이번 주 참여자 명단 — 맞힌 문제 수 순. 같은 별명은 한 번만.
     세 명만 싣던 것을 최대 60명까지 늘렸습니다. 순위표가 아니라 명단입니다. */
  base.week = Object.keys(person).map(function (k) {
      const p = person[k];
      return { nick: p.nick, flag: p.flag, school: p.school,
               correct: p.correct, run: p.run, days: Object.keys(p.days).length };
    })
    .filter(function (p) { return p.correct > 0; })
    .sort(function (a, b) { return b.correct - a.correct || b.days - a.days || b.run - a.run; })
    .slice(0, ROLL_N);
  base.people_week = base.week.length;
  base.top = base.week[0] || null;                    // 흐르는 띠는 1등만

  /* 학교 1·2·3등 — 부문별. 참여가 없는 부문은 아예 내보내지 않습니다 */
  const byCat = {};
  Object.keys(school).forEach(function (k) {
    const s = school[k];
    (byCat[s.cat] = byCat[s.cat] || []).push(
      { name: s.name, correct: s.correct, people: Object.keys(s.who).length });
  });
  Object.keys(byCat).forEach(function (c) {
    byCat[c].sort(function (a, b) { return b.correct - a.correct || b.people - a.people; });
    base.schools[c] = byCat[c].slice(0, TOP_N);
  });
  return base;
}

/* ─────────────────── 누적 참여자 ─────────────────── */
/* 예전에는 최근 80줄에서 '바로 앞줄과 같은 사람이면 합친다'는 방식이었습니다.
   두 사람이 번갈아 풀면 합쳐지지 않아 같은 이름이 반복해서 찍혔습니다
   (9to9 · Trina · 9to9 · 이준영 · 9to9 ...).
   사람을 열쇠로 하는 표를 만들어 전체 기간에서 한 번에 합칩니다.
   사람마다 줄이 하나뿐이라 반복 자체가 생길 수 없습니다. */
function live_() {
  const sh = sheet_();
  const last = sh.getLastRow();
  if (last < 2) return { live: [], at: '' };
  const from = Math.max(2, last - 19999);         // 이제까지 전체를 봅니다
  const rows = sh.getRange(from, 1, last - from + 1, 12).getValues();
  const person = {};                               // 별명 → 누적 기록
  const order = [];                                // 처음 등장한 순서(최신이 위로 오도록 뒤집습니다)
  rows.forEach(function (r) {
    if (!(r[0] instanceof Date)) return;
    const nk = String(r[1] || '').trim();
    if (!nk) return;
    if (!person[nk]) { person[nk] = { nick: nk, flag: '', school: '', n: 0, last: r[0] }; order.push(nk); }
    const p = person[nk];
    if (Number(r[5]) === 1) p.n++;                 // 맞힌 것만 셉니다
    const fg = String(r[2] || '').trim(); if (fg) p.flag = fg;
    const sc = String(r[9] || '').trim(); if (sc) p.school = sc;
    if (r[0] > p.last) p.last = r[0];
  });
  const now = Date.now();
  const out = order.reverse().map(function (nk) {
    const p = person[nk];
    return { k: nk, nick: p.nick, flag: p.flag, school: p.school, n: p.n,
             min: Math.max(0, Math.round((now - p.last.getTime()) / 60000)) };
  }).filter(function (p) { return p.n > 0; })
    .sort(function (a, b) { return b.n - a.n; });   // 맞힌 문제 수 순 · 누적 명단이므로
  return { live: out, at: Utilities.formatDate(new Date(), TZ, 'HH:mm') };
}

/* ───────────────────── 진도 백업 ───────────────────── */

function saveProgress_(d) {
  const key = String(d.key || '').trim();
  if (!key) return ContentService.createTextOutput('no key');
  const sh = progSheet_();
  const ids = sh.getRange(2, 1, Math.max(1, sh.getLastRow() - 1), 1).getValues();
  let row = 0;
  for (let i = 0; i < ids.length; i++) if (String(ids[i][0]) === key) { row = i + 2; break; }
  const rec = [key, new Date(), String(d.nick || ''), String(d.grade || ''),
               String(d.payload || '').slice(0, 45000)];
  if (row) sh.getRange(row, 1, 1, 5).setValues([rec]);
  else sh.appendRow(rec);
  return ContentService.createTextOutput('saved');
}

function loadProgress_(key) {
  const sh = progSheet_();
  const last = sh.getLastRow();
  if (last < 2) return { found: false };
  const rows = sh.getRange(2, 1, last - 1, 5).getValues();
  for (let i = rows.length - 1; i >= 0; i--) {
    if (String(rows[i][0]) === String(key)) {
      return { found: true, nick: rows[i][2], grade: rows[i][3], payload: rows[i][4] };
    }
  }
  return { found: false };
}

/* ─────────────────── 주간 자동 백업 ─────────────────── */
/* 도구 → 트리거 → 트리거 추가 → weeklyBackup · 주 단위 · 월요일 오전 1~2시 */

function weeklyBackup() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = sheet_();
  const last = sh.getLastRow();
  if (last < 2) return;
  const tag = Utilities.formatDate(new Date(), TZ, 'yyyyMMdd');
  const name = '백업_' + tag;
  if (ss.getSheetByName(name)) return;                // 이미 있으면 그대로 둡니다
  const copy = sh.copyTo(ss).setName(name);
  copy.hideSheet();
  /* 원본은 지우지 않습니다. 기록은 계속 쌓입니다. */
  Logger.log('백업 완료 — %s (%s줄)', name, last - 1);
}

/* ───────────────────────── 도구 ───────────────────────── */

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(LOG);
  if (!sh) {
    sh = ss.insertSheet(LOG);
    sh.appendRow(['시각', '별명', '국가', '학년', '문항번호', '정답',
                  '연속', '최고연속', '모드', '학교', '학교코드', '학교부문']);
    sh.setFrozenRows(1);
  }
  /* 예전 9칸 시트에 학교 칸 세 개를 덧붙입니다. 기존 줄은 그대로 둡니다. */
  if (sh.getLastColumn() < 12) {
    sh.getRange(1, 10, 1, 3).setValues([['학교', '학교코드', '학교부문']]);
  }
  return sh;
}

function progSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(PROG);
  if (!sh) {
    sh = ss.insertSheet(PROG);
    sh.appendRow(['열쇠', '저장 시각', '별명', '학년', '진도']);
    sh.setFrozenRows(1);
    sh.hideSheet();
  }
  return sh;
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o))
    .setMimeType(ContentService.MimeType.JSON);
}
