/**
 * HFK 게더링 — Google Sheets 저장용 Apps Script Web App
 *
 * 설치:
 * 1. https://sheets.google.com 에서 새 스프레드시트 생성
 * 2. 확장 프로그램 → Apps Script → 이 파일 전체 붙여넣기
 * 3. 프로젝트 설정 → 스크립트 속성 →
 *    - 속성명: ADMIN_TOKEN
 *    - 값: 임의의 문자열 32자 이상 권장 (예: openssl rand -hex 24)
 *    - 이 토큰을 아는 사람만 관리자 조회·수정 가능
 * 4. 저장 → 배포 → 새 배포
 *    - 유형: 웹 앱
 *    - 다음 사용자로 실행: 나
 *    - 액세스 권한: 모든 사용자
 * 5. 발급된 웹 앱 URL을 복사 (https://script.google.com/macros/s/.../exec)
 * 6. HFK 게더링 웹페이지 → 관리자 → Google Drive 연동에
 *    URL과 ADMIN_TOKEN을 붙여넣기
 *
 * 인증 정책:
 *  - application(신청 접수), ping: 토큰 불필요 (일반 사용자용)
 *  - fetchApplications, syncAll, session: 토큰 필수 (관리자용)
 *
 * 시트 구조:
 *  - "신청": 개별 신청 append 로그
 *  - "게더링": 세션 정보 스냅샷
 */

const APPLICATIONS_SHEET = "신청";
const SESSION_SHEET = "게더링";

const APPLICATION_HEADERS = [
  "신청 ID", "세션 ID", "세션명", "이름", "이메일", "소속",
  "연차", "현재 직무", "매칭 기준",
  "희망 연차", "희망 직무", "관심 주제",
  "고민", "공유 경험", "공개 정보",
  "신청 일시", "수신 일시"
];

const SESSION_HEADERS = [
  "게더링 ID", "게더링명", "날짜", "시간", "장소",
  "목표 인원", "최소 인원", "최대 인원",
  "신청 마감", "확정 예정", "마지막 갱신"
];

const ADMIN_ONLY_TYPES = ["fetchApplications", "syncAll", "session"];

function getAdminToken() {
  return PropertiesService.getScriptProperties().getProperty("ADMIN_TOKEN") || "";
}

function checkAdmin(data) {
  const expected = getAdminToken();
  if (!expected) return { ok: false, error: "서버에 ADMIN_TOKEN이 설정돼 있지 않습니다. Apps Script 프로젝트 설정 → 스크립트 속성에서 ADMIN_TOKEN을 지정하세요." };
  const provided = data.adminToken || "";
  if (provided !== expected) return { ok: false, error: "관리자 토큰이 올바르지 않습니다." };
  return null;
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);

    // 관리자 전용 작업은 토큰 검증
    if (ADMIN_ONLY_TYPES.indexOf(data.type) >= 0) {
      const err = checkAdmin(data);
      if (err) return json(err);
    }

    let result;
    if (data.type === "application") {
      result = appendApplication(data.payload);
    } else if (data.type === "syncAll") {
      const sessions = data.sessions || (data.session ? [data.session] : []);
      result = syncAll(data.applications, sessions);
    } else if (data.type === "session") {
      result = upsertSession(data.payload);
    } else if (data.type === "fetchApplications") {
      result = fetchApplications();
    } else if (data.type === "ping") {
      result = { ok: true, message: "연결됨", adminTokenConfigured: !!getAdminToken() };
    } else {
      result = { ok: false, error: "unknown type: " + data.type };
    }
    return json(result);
  } catch (err) {
    return json({ ok: false, error: err.message });
  }
}

function doGet() {
  return ContentService
    .createTextOutput(JSON.stringify({
      ok: true,
      message: "HFK 게더링 Web App is running. POST JSON payloads here."
    }))
    .setMimeType(ContentService.MimeType.JSON);
}

function getOrCreateSheet(name, headers) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold");
    sheet.setFrozenRows(1);
  } else if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold");
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function applicationRow(app) {
  return [
    app.id,
    app.sessionId || "",
    app.sessionName || "",
    app.name || "",
    app.email || "",
    app.company || "",
    app.seniority,
    app.currentJob || "",
    labelCriterion(app.criterion),
    app.desiredSeniority || "",
    (app.desiredJobs || []).join(", "),
    (app.topics || []).join(", "),
    app.concern || "",
    app.experience || "",
    (app.disclose || []).join(", "),
    app.createdAt || "",
    new Date().toISOString()
  ];
}

function labelCriterion(c) {
  return { seniority: "연차", job: "직무", topic: "주제" }[c] || c;
}

function unlabelCriterion(label) {
  return { "연차": "seniority", "직무": "job", "주제": "topic" }[label] || label;
}

function appendApplication(app) {
  const sheet = getOrCreateSheet(APPLICATIONS_SHEET, APPLICATION_HEADERS);
  // 같은 신청 ID가 이미 있으면 그 행을 덮어쓰기 (수정 반영)
  const ids = sheet.getRange(2, 1, Math.max(sheet.getLastRow() - 1, 0), 1).getValues().flat();
  const idx = ids.indexOf(app.id);
  const row = applicationRow(app);
  if (idx >= 0) {
    sheet.getRange(idx + 2, 1, 1, row.length).setValues([row]);
    return { ok: true, action: "updated", id: app.id };
  }
  sheet.appendRow(row);
  return { ok: true, action: "appended", id: app.id };
}

function syncAll(applications, sessions) {
  const appSheet = getOrCreateSheet(APPLICATIONS_SHEET, APPLICATION_HEADERS);
  if (appSheet.getLastRow() > 1) {
    appSheet.getRange(2, 1, appSheet.getLastRow() - 1, APPLICATION_HEADERS.length).clearContent();
  }
  if (applications.length) {
    const rows = applications.map(applicationRow);
    appSheet.getRange(2, 1, rows.length, APPLICATION_HEADERS.length).setValues(rows);
  }

  const sessionSheet = getOrCreateSheet(SESSION_SHEET, SESSION_HEADERS);
  if (sessionSheet.getLastRow() > 1) {
    sessionSheet.getRange(2, 1, sessionSheet.getLastRow() - 1, SESSION_HEADERS.length).clearContent();
  }
  if (sessions && sessions.length) {
    const rows = sessions.map(sessionRow);
    sessionSheet.getRange(2, 1, rows.length, SESSION_HEADERS.length).setValues(rows);
  }

  return {
    ok: true,
    appCount: applications.length,
    sessionCount: sessions ? sessions.length : 0
  };
}

function sessionRow(session) {
  return [
    session.id, session.name, session.date, session.time, session.location,
    session.targetGroupSize, session.minGroupSize, session.maxGroupSize,
    session.applyDeadline, session.confirmDate, new Date().toISOString()
  ];
}

function fetchApplications() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const appSheet = ss.getSheetByName(APPLICATIONS_SHEET);
  const sessionSheet = ss.getSheetByName(SESSION_SHEET);

  const applications = [];
  if (appSheet && appSheet.getLastRow() > 1) {
    const rows = appSheet.getRange(2, 1, appSheet.getLastRow() - 1, APPLICATION_HEADERS.length).getValues();
    for (const row of rows) {
      if (!row[0]) continue;
      applications.push({
        id: String(row[0]),
        sessionId: String(row[1] || ""),
        applicantName: String(row[3] || ""),
        applicantEmail: String(row[4] || ""),
        applicantCompany: String(row[5] || ""),
        seniority: Number(row[6]) || 0,
        currentJob: String(row[7] || ""),
        criterion: unlabelCriterion(String(row[8] || "")),
        desiredSeniority: String(row[9] || "") || null,
        desiredJobs: splitList(row[10]),
        topics: splitList(row[11]),
        concern: String(row[12] || ""),
        experience: String(row[13] || ""),
        disclose: splitList(row[14]),
        createdAt: row[15] ? toIsoString(row[15]) : ""
      });
    }
  }

  const sessions = [];
  if (sessionSheet && sessionSheet.getLastRow() > 1) {
    const rows = sessionSheet.getRange(2, 1, sessionSheet.getLastRow() - 1, SESSION_HEADERS.length).getValues();
    for (const row of rows) {
      if (!row[0]) continue;
      sessions.push({
        id: String(row[0]),
        name: String(row[1] || ""),
        date: toDateString(row[2]),
        time: String(row[3] || ""),
        location: String(row[4] || ""),
        targetGroupSize: Number(row[5]) || 5,
        minGroupSize: Number(row[6]) || 4,
        maxGroupSize: Number(row[7]) || 6,
        applyDeadline: toDateString(row[8]),
        confirmDate: toDateString(row[9]),
      });
    }
  }
  return { ok: true, applications: applications, sessions: sessions };
}

function splitList(v) {
  return String(v || "").split(",").map(s => s.trim()).filter(Boolean);
}
function toIsoString(v) {
  if (v instanceof Date) return v.toISOString();
  return String(v);
}
function toDateString(v) {
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), "yyyy-MM-dd");
  return String(v || "");
}

function upsertSession(session) {
  const sheet = getOrCreateSheet(SESSION_SHEET, SESSION_HEADERS);
  const row = sessionRow(session);
  const ids = sheet.getRange(2, 1, Math.max(sheet.getLastRow() - 1, 0), 1).getValues().flat();
  const idx = ids.indexOf(session.id);
  if (idx >= 0) {
    sheet.getRange(idx + 2, 1, 1, row.length).setValues([row]);
    return { action: "updated" };
  }
  sheet.appendRow(row);
  return { action: "appended" };
}
