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


HARD_EXCLUSION_TERMS = ["자격증 발급", "자격증 신청", "자격 발급", "자격시험", "평생교육사", "교원자격"]


FRESHNESS = {"모집중": 50, "접수예정": 45, "마감임박": 40, "긴급": 35, "날짜확인필요": 10, "마감됨": -30}


def classify(title: str, text: str, dates: dict[str, str], keywords: dict) -> Classification:
    haystack = f"{title}\n{text}"
    registration_score, registration_matches = _score(haystack, keywords["registration_positive"], keywords["registration_negative"])
    external_score, external_matches = _score(haystack, keywords["external_positive"], keywords["external_negative"])
    computer_score, computer_matches = _score(haystack, keywords["computer_positive"], keywords["computer_negative"], positive_wins=True)
    freshness_score = FRESHNESS.get(dates.get("deadline_status", "날짜확인필요"), 10)
    external_status = _external_status(external_score)
    computer_status = _computer_status(computer_score)
    grade = _grade(registration_score, external_score, computer_score, freshness_score, dates.get("deadline_status", ""))
    hard_exclusion = any(term in haystack for term in HARD_EXCLUSION_TERMS)
    if hard_exclusion:
        grade = "D"
    matched = list(dict.fromkeys(registration_matches + external_matches + computer_matches))
    reason = _reason(grade, registration_score, external_status, computer_status, dates.get("deadline_status", ""))
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


def _grade(registration: int, external: int, computer: int, freshness: int, deadline_status: str) -> str:
    if deadline_status == "마감됨":
        return "D"
    total = registration + max(external, 0) + max(computer, 0) + freshness
    if registration >= 70 and external >= 25 and computer >= 25 and freshness > 0:
        return "A"
    if registration >= 45 and external >= 20 and total >= 100:
        return "B"
    if registration >= 20 or computer >= 30:
        return "C"
    return "D"


def _reason(grade: str, registration: int, external_status: str, computer_status: str, deadline_status: str) -> str:
    if grade == "A":
        return f"시간제등록 또는 외부 수강 관련성이 높고, 외부 신청 가능성과 컴퓨터 관련 과목 가능성이 함께 감지됨. 현재 상태: {deadline_status}."
    if grade == "B":
        return f"공식 게시판에서 유력 후보가 발견되었으나 외부 신청 또는 컴퓨터 과목 여부 추가 확인 필요. 현재 상태: {deadline_status}."
    if grade == "C":
        return f"참고 후보입니다. 등록 관련 점수 {registration}, 외부 신청 {external_status}, 컴퓨터 과목 {computer_status}."
    return "제외 후보입니다. 공식 모집 공고 관련성, 외부 신청 가능성 또는 현재 유효성이 낮습니다."
