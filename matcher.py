"""HFK 게더링 자동 배정 프로토타입.

요구서 6장(자동 그룹 배정) + 6.5(매칭 점수) + 6.4 방식 C(우선 분리 후 잔여 통합) 구현.

실행: python matcher.py
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Literal

Criterion = Literal["seniority", "job", "topic"]


@dataclass
class Participant:
    id: str
    name: str
    seniority: int                       # 연차 (년)
    current_job: str
    date_id: str                         # 참가 희망 날짜
    criterion: Criterion                 # 선택한 매칭 기준
    desired_seniority: tuple[int, int] | None = None   # (min, max) 원하는 연차 범위
    desired_jobs: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    concern: str = ""
    experience: str = ""


@dataclass
class Session:
    id: str
    date: str
    target_group_size: int = 5
    min_group_size: int = 4
    max_group_size: int = 6


@dataclass
class Group:
    id: str
    session_id: str
    members: list[Participant] = field(default_factory=list)
    # 생성 방식: "criterion:<name>" 또는 "mixed"
    origin: str = ""

    @property
    def size(self) -> int:
        return len(self.members)


# ---------------------------------------------------------------------------
# 도메인 상수
# ---------------------------------------------------------------------------

# 직무 그룹 (요구서 4.6 예시 기반)
JOB_GROUPS: list[set[str]] = [
    {"경영기획", "전략", "사업기획", "사업개발"},
    {"마케팅", "브랜드"},
    {"제품", "서비스 기획"},
    {"데이터", "개발"},
    {"인사", "조직문화"},
    {"재무", "회계"},
    {"영업", "운영"},
    {"디자인"},
    {"창업"},
]

# 주제 유사 관계 (요구서 4.7 예시)
TOPIC_CLUSTERS: list[set[str]] = [
    {"리더십", "팀 관리", "조직문화"},
    {"커리어 전환", "독립과 창업", "사이드 프로젝트"},
    {"AI 활용", "기획력", "새로운 사업"},
    {"브랜딩", "마케팅"},
    {"투자와 자산", "일과 삶"},
    {"관계와 네트워크"},
]

# 연차 구간
SENIORITY_BUCKETS: list[tuple[int, int]] = [
    (1, 3), (4, 6), (7, 9), (10, 12), (13, 15), (16, 99),
]


# ---------------------------------------------------------------------------
# 매칭 점수 (6.5)
# ---------------------------------------------------------------------------
# 총 100점: 기준 30 + 세부 30 + 연차 15 + 직무 15 + 주제 20 + 고민-경험 10
# = 120점을 100점 환산 (단순 합산 후 min(100, x)로 캡)

def _seniority_bucket(years: int) -> tuple[int, int]:
    for lo, hi in SENIORITY_BUCKETS:
        if lo <= years <= hi:
            return (lo, hi)
    return SENIORITY_BUCKETS[-1]


def _in_range(value: int, r: tuple[int, int] | None) -> bool:
    if r is None:
        return False
    return r[0] <= value <= r[1]


def score_pair(a: Participant, b: Participant) -> float:
    """두 신청자 간 매칭 점수 (0~100)."""
    if a.date_id != b.date_id:
        return 0.0  # 6.1 필수 조건

    total = 0.0

    # 1. 기준 일치 (30)
    if a.criterion == b.criterion:
        total += 30

    # 2. 세부 선호 (30) — 기준별로 다르게 계산
    total += _sub_preference_score(a, b)

    # 3. 연차 유사도 (15)
    diff = abs(a.seniority - b.seniority)
    if diff == 0:
        total += 15
    elif diff <= 2:
        total += 12
    elif diff <= 4:
        total += 8
    elif diff <= 6:
        total += 4

    # 4. 직무 연관성 (15)
    total += _job_relation_score(a.current_job, b.current_job)

    # 5. 주제 유사도 (20)
    total += _topic_similarity_score(a.topics, b.topics)

    # 6. 고민-경험 연관성 (10) — 양방향 키워드 겹침
    total += _concern_experience_score(a, b)

    return min(100.0, total)


def _sub_preference_score(a: Participant, b: Participant) -> float:
    """세부 선호 30점. 양방향 일치 30, 편도 15, 없음 0."""
    if a.criterion == "seniority" and b.criterion == "seniority":
        a_wants_b = _in_range(b.seniority, a.desired_seniority)
        b_wants_a = _in_range(a.seniority, b.desired_seniority)
        return 30 if (a_wants_b and b_wants_a) else 15 if (a_wants_b or b_wants_a) else 0

    if a.criterion == "job" and b.criterion == "job":
        a_wants_b = b.current_job in a.desired_jobs
        b_wants_a = a.current_job in b.desired_jobs
        return 30 if (a_wants_b and b_wants_a) else 15 if (a_wants_b or b_wants_a) else 0

    if a.criterion == "topic" and b.criterion == "topic":
        shared = set(a.topics) & set(b.topics)
        if len(shared) >= 2:
            return 30
        if len(shared) == 1:
            return 20
        # 같은 주제 없음 — 유사 클러스터 확인
        for cluster in TOPIC_CLUSTERS:
            if (set(a.topics) & cluster) and (set(b.topics) & cluster):
                return 10
        return 0

    # 기준이 서로 다름 — 세부 선호는 계산하지 않음
    return 0


def _job_relation_score(job_a: str, job_b: str) -> float:
    if job_a == job_b:
        return 15
    for group in JOB_GROUPS:
        if job_a in group and job_b in group:
            return 10
    return 0


def _topic_similarity_score(topics_a: list[str], topics_b: list[str]) -> float:
    shared = set(topics_a) & set(topics_b)
    if len(shared) >= 3:
        return 20
    if len(shared) == 2:
        return 14
    if len(shared) == 1:
        return 8
    for cluster in TOPIC_CLUSTERS:
        if (set(topics_a) & cluster) and (set(topics_b) & cluster):
            return 4
    return 0


def _tokenize(text: str) -> set[str]:
    # 최소 2글자 이상 토큰만
    return {t for t in text.replace(",", " ").replace(".", " ").split() if len(t) >= 2}


def _concern_experience_score(a: Participant, b: Participant) -> float:
    """A의 고민 ↔ B의 경험, B의 고민 ↔ A의 경험 양방향 매칭."""
    score = 0.0
    a_concern = _tokenize(a.concern)
    b_concern = _tokenize(b.concern)
    a_exp = _tokenize(a.experience)
    b_exp = _tokenize(b.experience)

    for concern, exp in [(a_concern, b_exp), (b_concern, a_exp)]:
        if not concern:
            continue
        overlap = len(concern & exp)
        if overlap >= 2:
            score += 5
        elif overlap == 1:
            score += 3
    return min(10.0, score)


# ---------------------------------------------------------------------------
# 그룹 형성 (그리디)
# ---------------------------------------------------------------------------

def _avg_score_to_group(candidate: Participant, group: list[Participant],
                        score_cache: dict[tuple[str, str], float]) -> float:
    if not group:
        return 0.0
    total = sum(score_cache[_key(candidate.id, m.id)] for m in group)
    return total / len(group)


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _build_score_cache(participants: list[Participant]) -> dict[tuple[str, str], float]:
    cache = {}
    for a, b in itertools.combinations(participants, 2):
        cache[_key(a.id, b.id)] = score_pair(a, b)
    return cache


def _form_groups(
    pool: list[Participant],
    session: Session,
    origin: str,
    group_counter: itertools.count,
    score_cache: dict[tuple[str, str], float],
) -> tuple[list[Group], list[Participant]]:
    """풀에서 그리디로 그룹을 만들고, 남은 인원(<min)을 반환."""
    remaining = list(pool)
    groups: list[Group] = []

    while len(remaining) >= session.min_group_size:
        # 시드: 나머지와의 평균 점수가 가장 높은 사람
        seed = max(
            remaining,
            key=lambda p: sum(score_cache[_key(p.id, q.id)] for q in remaining if q.id != p.id)
        )
        group = [seed]
        remaining.remove(seed)

        # 목표 인원까지 채우기 — 매 스텝 avg 점수 최대 인원 추가
        while len(group) < session.target_group_size and remaining:
            best = max(remaining, key=lambda p: _avg_score_to_group(p, group, score_cache))
            group.append(best)
            remaining.remove(best)

        groups.append(Group(
            id=f"G{next(group_counter):03d}",
            session_id=session.id,
            members=group,
            origin=origin,
        ))

    return groups, remaining


def assign_session(
    participants: list[Participant],
    session: Session,
) -> tuple[list[Group], list[Participant]]:
    """방식 C: 기준별 우선 분리 → 잔여 인원 통합."""
    same_date = [p for p in participants if p.date_id == session.id]
    score_cache = _build_score_cache(same_date)
    group_counter = itertools.count(1)

    all_groups: list[Group] = []
    leftover: list[Participant] = []

    # 1단계: 기준별로 분리해 그룹 형성
    for criterion in ("seniority", "job", "topic"):
        pool = [p for p in same_date if p.criterion == criterion]
        if not pool:
            continue
        groups, rem = _form_groups(
            pool, session, f"criterion:{criterion}", group_counter, score_cache
        )
        all_groups.extend(groups)
        leftover.extend(rem)

    # 2단계: 잔여 인원 통합 배정
    if len(leftover) >= session.min_group_size:
        mixed_groups, final_unassigned = _form_groups(
            leftover, session, "mixed", group_counter, score_cache
        )
        all_groups.extend(mixed_groups)
    else:
        final_unassigned = leftover

    # 3단계: 아직 남은 인원(< min) — 기존 그룹에 붙일 수 있으면 붙임 (max 이내)
    still_unassigned = []
    for p in final_unassigned:
        placed = False
        # 점수가 가장 잘 맞는 그룹부터 시도
        candidates = sorted(
            all_groups,
            key=lambda g: _avg_score_to_group(p, g.members, score_cache),
            reverse=True,
        )
        for g in candidates:
            if g.size < session.max_group_size:
                g.members.append(p)
                placed = True
                break
        if not placed:
            still_unassigned.append(p)

    return all_groups, still_unassigned


# ---------------------------------------------------------------------------
# 리포팅
# ---------------------------------------------------------------------------

def group_metrics(group: Group, score_cache: dict[tuple[str, str], float]) -> dict:
    pairs = list(itertools.combinations(group.members, 2))
    if not pairs:
        return {"avg": 0.0, "min": 0.0}
    scores = [score_cache[_key(a.id, b.id)] for a, b in pairs]
    return {
        "avg": sum(scores) / len(scores),
        "min": min(scores),
    }


def print_report(session: Session, groups: list[Group], unassigned: list[Participant],
                 participants: list[Participant]) -> None:
    print(f"\n{'=' * 70}")
    print(f"세션 {session.id} ({session.date})")
    print(f"신청자 {sum(1 for p in participants if p.date_id == session.id)}명 → "
          f"{len(groups)}개 그룹, 미배정 {len(unassigned)}명")
    print(f"{'=' * 70}")

    score_cache = _build_score_cache([p for p in participants if p.date_id == session.id])

    for g in groups:
        m = group_metrics(g, score_cache)
        warn = ""
        if g.size < session.min_group_size:
            warn = " ⚠ 정원 미달"
        elif g.size > session.max_group_size:
            warn = " ⚠ 정원 초과"

        print(f"\n[{g.id}] {g.origin} | {g.size}명 | "
              f"평균 {m['avg']:.1f}점 / 최저 {m['min']:.1f}점{warn}")
        for p in g.members:
            marker = {"seniority": "연차", "job": "직무", "topic": "주제"}[p.criterion]
            topics_str = f" · {', '.join(p.topics)}" if p.topics else ""
            print(f"  · {p.name:8s} {p.seniority:2d}년 {p.current_job:8s} "
                  f"[{marker}]{topics_str}")

    if unassigned:
        print(f"\n[미배정 {len(unassigned)}명]")
        for p in unassigned:
            print(f"  · {p.name} ({p.criterion}, {p.seniority}년 {p.current_job})")


# ---------------------------------------------------------------------------
# 샘플 데이터 & 실행
# ---------------------------------------------------------------------------

def sample_participants() -> list[Participant]:
    """1개 날짜 · 18명 (연차 6, 직무 6, 주제 6) 혼합."""
    P = Participant
    s = "2026-08-15"

    return [
        # ── 연차 기준 (6명) ─────────────────────────────
        P("u01", "김선배", 12, "경영기획", s, "seniority",
          desired_seniority=(10, 15),
          concern="팀 리더로서 성과 관리가 어렵다",
          experience="10년간 전략 조직 리드"),
        P("u02", "박중견", 11, "전략", s, "seniority",
          desired_seniority=(9, 13),
          concern="시니어 매니저 역할 전환 고민",
          experience="컨설팅 → 인하우스 전환"),
        P("u03", "이경력", 8, "마케팅", s, "seniority",
          desired_seniority=(6, 10),
          concern="첫 팀장 역할, 팀원 관리 노하우",
          experience="퍼포먼스 마케팅 8년"),
        P("u04", "정중반", 7, "브랜드", s, "seniority",
          desired_seniority=(5, 10),
          concern="브랜드 전략 수립 프레임",
          experience="B2C 브랜드 리뉴얼 3건"),
        P("u05", "최주니어", 4, "개발", s, "seniority",
          desired_seniority=(3, 7),
          concern="시니어 개발자로 성장하는 길",
          experience="스타트업 초기 멤버"),
        P("u06", "강신입", 3, "데이터", s, "seniority",
          desired_seniority=(2, 6),
          concern="분석가 커리어 방향",
          experience="SQL과 대시보드 구축"),

        # ── 직무 기준 (6명) ─────────────────────────────
        P("u07", "한마케팅", 6, "마케팅", s, "job",
          desired_jobs=["브랜드", "제품"],
          concern="브랜드 마케터로 전환하고 싶다",
          experience="퍼포먼스 → 브랜드 이동 경험"),
        P("u08", "윤브랜드", 7, "브랜드", s, "job",
          desired_jobs=["마케팅", "디자인"],
          concern="브랜드 팀 세팅",
          experience="브랜드 팀 0→1 셋업"),
        P("u09", "노기획", 5, "서비스 기획", s, "job",
          desired_jobs=["제품", "데이터"],
          concern="데이터 기반 기획 역량",
          experience="B2B SaaS 기획 5년"),
        P("u10", "서프로덕트", 8, "제품", s, "job",
          desired_jobs=["서비스 기획", "개발"],
          concern="PM 역할 정의",
          experience="PM 리드로 3년"),
        P("u11", "임인사", 9, "인사", s, "job",
          desired_jobs=["조직문화", "경영기획"],
          concern="조직문화 개선 사례",
          experience="HR BP 5년"),
        P("u12", "장문화", 6, "조직문화", s, "job",
          desired_jobs=["인사", "브랜드"],
          concern="문화팀 없이 문화 만들기",
          experience="AAR과 회고 워크숍 운영"),

        # ── 주제 기준 (6명) ─────────────────────────────
        P("u13", "오AI", 5, "개발", s, "topic",
          topics=["AI 활용", "새로운 사업", "기획력"],
          concern="AI 프로덕트 기획 실전",
          experience="LLM 파이프라인 구축"),
        P("u14", "권기획", 7, "서비스 기획", s, "topic",
          topics=["AI 활용", "기획력", "새로운 사업"],
          concern="AI 시대 기획자 역할",
          experience="AI 기능 3건 릴리즈"),
        P("u15", "황리더", 10, "경영기획", s, "topic",
          topics=["리더십", "팀 관리", "조직문화"],
          concern="팀장 첫 1년",
          experience="10명 팀 리드"),
        P("u16", "송매니저", 9, "인사", s, "topic",
          topics=["리더십", "조직문화"],
          concern="MZ 팀원과 시니어의 갈등",
          experience="1:1 코칭 프로그램 도입"),
        P("u17", "배창업", 8, "창업", s, "topic",
          topics=["독립과 창업", "사이드 프로젝트"],
          concern="첫 창업 준비",
          experience="사이드 프로젝트 2건"),
        P("u18", "구프리", 6, "디자인", s, "topic",
          topics=["독립과 창업", "커리어 전환"],
          concern="프리랜서 전환 시점",
          experience="사내 → 프리랜서 3년"),
    ]


def main() -> None:
    random.seed(42)
    participants = sample_participants()
    session = Session(id="2026-08-15", date="2026-08-15",
                      target_group_size=5, min_group_size=4, max_group_size=6)

    groups, unassigned = assign_session(participants, session)
    print_report(session, groups, unassigned, participants)

    # 요약 지표 (요구서 6.6 실행 결과)
    print(f"\n{'=' * 70}")
    print("실행 요약")
    print(f"{'=' * 70}")
    print(f"생성 그룹: {len(groups)}개")
    print(f"배정 완료: {sum(g.size for g in groups)}명")
    print(f"미배정:    {len(unassigned)}명")
    if groups:
        score_cache = _build_score_cache(participants)
        avg_scores = [group_metrics(g, score_cache)["avg"] for g in groups]
        print(f"평균 매칭 점수: {sum(avg_scores) / len(avg_scores):.1f}")


if __name__ == "__main__":
    main()
