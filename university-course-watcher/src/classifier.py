from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Classification:
    registration_score: int
    external_score: int
    computer_score: int
    freshness_score: int
    grade: str
    external_applicant_status: str
    computer_course_status: str
    matched_keywords: list[str]
    reason: str


FRESHNESS = {"모집중": 50, "접수예정": 45, "마감임박": 40, "긴급": 35, "날짜확인필요": 10, "마감됨": -30}
RECRUITMENT_TERMS = [
    "모집요강", "모집 안내", "모집안내", "모집 공고", "모집공고", "원서접수", "지원자격",
    "시간제등록생 모집", "시간제 등록생 모집", "시간제등록 모집", "시간제 등록 모집",
]
ADMIN_ONLY_TERMS = [
    "합격자", "최종합격", "추가합격", "등록금", "등록 안내", "등록안내", "등록 기간",
    "등록기간", "납부", "고지서", "환불", "예치금", "문서등록", "생활관", "장학금",
]


def classify(title: str, text: str, dates: dict[str, str], keywords: dict) -> Classification:
    haystack = f"{title}\n{text}"
    registration_score, registration_matches = _score(haystack, keywords["registration_positive"], keywords["registration_negative"])
    external_score, external_matches = _score(haystack, keywords["external_positive"], keywords["external_negative"])
    computer_score, computer_matches = _score(haystack, keywords["computer_positive"], keywords["computer_negative"], positive_wins=True)
    freshness_score = FRESHNESS.get(dates.get("deadline_status", "날짜확인필요"), 10)
    registration_score = _adjust_registration_score(title, haystack, registration_score)
    external_status = _external_status(external_score)
    computer_status = _computer_status(computer_score)
    grade = _grade(title, haystack, registration_score, external_score, computer_score, freshness_score, dates.get("deadline_status", ""))
    matched = list(dict.fromkeys(registration_matches + external_matches + computer_matches))
    reason = _reason(title, haystack, grade, registration_score, external_status, computer_status, dates.get("deadline_status", ""))
    return Classification(
        registration_score=registration_score,
        external_score=external_score,
        computer_score=computer_score,
        freshness_score=freshness_score,
        grade=grade,
        external_applicant_status=external_status,
        computer_course_status=computer_status,
        matched_keywords=matched,
        reason=reason,
    )


def _score(text: str, positive: dict[str, int], negative: dict[str, int], positive_wins: bool = False) -> tuple[int, list[str]]:
    score = 0
    matches: list[str] = []
    lower = text.lower()
    positive_hit = False
    for word, points in positive.items():
        if word.lower() in lower:
            score += points
            matches.append(word)
            positive_hit = True
    if positive_wins and positive_hit:
        return score, matches
    for word, points in negative.items():
        if word.lower() in lower:
            score += points
            matches.append(word)
    return score, matches


def _adjust_registration_score(title: str, text: str, score: int) -> int:
    if _is_admin_only_notice(title, text):
        return min(score - 120, 0)
    if _has_recruitment_signal(title, text):
        return score + 20
    return score


def _external_status(score: int) -> str:
    if score >= 30:
        return "가능성 높음"
    if score <= -20:
        return "불가 가능성 높음"
    return "확인 필요"


def _computer_status(score: int) -> str:
    if score >= 30:
        return "가능성 높음"
    if score <= 0:
        return "관련성 낮음"
    return "확인 필요"


def _grade(title: str, text: str, registration: int, external: int, computer: int, freshness: int, deadline_status: str) -> str:
    if deadline_status == "마감됨":
        return "D"
    if _is_admin_only_notice(title, text):
        return "D"
    total = registration + max(external, 0) + max(computer, 0) + freshness
    if registration >= 70 and external >= 25 and computer >= 25 and freshness > 0 and _has_recruitment_signal(title, text):
        return "A"
    if registration >= 45 and total >= 100 and _has_recruitment_signal(title, text):
        return "B"
    if registration >= 20 or computer >= 30:
        return "C"
    return "D"


def _reason(title: str, text: str, grade: str, registration: int, external_status: str, computer_status: str, deadline_status: str) -> str:
    if _is_admin_only_notice(title, text):
        return "합격자 등록, 등록금 납부 등 모집요강 이후 행정 안내로 판단되어 알림 대상에서 제외됨."
    if grade == "A":
        return f"시간제등록 또는 외부 수강 관련성이 높고, 외부 신청 가능성과 컴퓨터 관련 과목 가능성이 함께 감지됨. 현재 상태: {deadline_status}."
    if grade == "B":
        return f"공식 게시판에서 유력 후보가 발견되었으나 외부 신청 또는 컴퓨터 과목 여부 추가 확인 필요. 현재 상태: {deadline_status}."
    if grade == "C":
        return f"참고 후보입니다. 등록 관련 점수 {registration}, 외부 신청 {external_status}, 컴퓨터 과목 {computer_status}."
    return "제외 후보입니다. 공식 모집 공고 관련성, 외부 신청 가능성 또는 현재 유효성이 낮습니다."


def _has_recruitment_signal(title: str, text: str) -> bool:
    lower_title = title.lower()
    lower_text = text.lower()
    for term in RECRUITMENT_TERMS:
        term_lower = term.lower()
        if term_lower in lower_title or term_lower in lower_text:
            return True
    return False


def _is_admin_only_notice(title: str, text: str) -> bool:
    lower_title = title.lower()
    lower_text = text.lower()
    has_admin_term = False
    has_recruitment_term = False

    for term in ADMIN_ONLY_TERMS:
        term_lower = term.lower()
        if term_lower in lower_title:
            has_admin_term = True
            break

    if not has_admin_term:
        return False

    for term in RECRUITMENT_TERMS:
        term_lower = term.lower()
        if term_lower in lower_title:
            has_recruitment_term = True
            break

    if has_recruitment_term:
        return False
    return any(term.lower() in lower_text for term in ADMIN_ONLY_TERMS)
