"""유웨이어플라이/진학사어플라이 원서접수 포털에서 일반대학원 모집을 수집."""
from __future__ import annotations

import json
import logging
import re

import requests
from bs4 import BeautifulSoup

from .board_crawler import HTML_PARSER
from .utils import normalize_space, now_kst

LOGGER = logging.getLogger(__name__)
TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 university-course-watcher/1.0"}

UWAY_LIST_URL = "https://www.uwayapply.com/main/applylist_list.inc?v_flag=5&v_loc=All|&v_gb=All|&click=yes"
JINHAK_PAGE_URL = "https://www.jinhakapply.com/SiteList/SiteGraduateList"
JINHAK_API_URL = "https://apply.jinhakapply.com/WebCommon/Ajax/GetUnivList.aspx/ServiceList"

# 일반대학원이 아닌 특수/전문대학원 판별용
NEGATIVE_WORDS = ["교육대학원", "경영전문", "경영대학원", "특수대학원", "전문대학원", "신학대학원",
                  "사회복지대학원", "상담", "외국인", "international", "글로벌", "MBA"]


def fetch_portal_items(target_term: str = "후기") -> list[dict]:
    items: list[dict] = []

    for fn in (_fetch_uway, _fetch_jinhak):
        try:
            items.extend(fn(target_term))
        except Exception as exc:
            LOGGER.warning("Apply portal fetch failed (%s): %s", fn.__name__, exc)

    return items


def _grade(sName: str) -> str:
    sLowered = sName.lower()

    if any(sWord.lower() in sLowered for sWord in NEGATIVE_WORDS):
        return "D"
    if "일반대학원" in sName:
        return "A"
    if "대학원" in sName:
        return "B"
    return "D"


def _item(sPortal: str, sName: str, sUrl: str, sBoardType: str, sReason: str) -> dict:
    sUniversity = sName.split()[0] if sName.split() else sName

    return {
        "checked_at": now_kst().isoformat(timespec="seconds"),
        "university_name": sUniversity,
        "region": "",
        "city": "",
        "board_type": sBoardType,
        "title": sName,
        "url": sUrl,
        # 접수중 목록이므로 확인일을 게시일로 사용 (없으면 recency 필터에서 탈락)
        "notice_date": now_kst().date().isoformat(),
        "grade": _grade(sName),
        "matched_keywords": ["대학원", sPortal],
        "reason": sReason,
        "attachment_urls": [],
        "is_new": False,
    }


def _fetch_uway(target_term: str) -> list[dict]:
    response = requests.get(UWAY_LIST_URL, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.content.decode("utf-8", errors="replace"), HTML_PARSER)
    items: list[dict] = []

    for nodeSection in soup.select("div.list"):
        nodeHeading = nodeSection.find("h4")
        sSection = normalize_space(nodeHeading.get_text(" ")) if nodeHeading else ""

        if "대학원" not in sSection or target_term not in sSection:
            continue

        for nodeLink in nodeSection.find_all("a", href=True):
            nodeStatus = nodeLink.find("i")
            sStatus = nodeStatus.get("title", "") if nodeStatus else ""
            # 상태 아이콘(<i>접</i>, <span><i>U</i></span>) 텍스트가 제목에 섞이지 않도록 제거
            for nodeIcon in nodeLink.find_all(["i", "span"]):
                nodeIcon.decompose()
            sName = normalize_space(nodeLink.get_text(" "))
            item = _item(
                "유웨이어플라이", sName, nodeLink["href"],
                f"유웨이어플라이 {sSection}",
                f"유웨이어플라이 '{sSection}' 목록에서 원서접수 확인됨 (상태: {sStatus or '확인 필요'}).",
            )

            # 포털은 전국 단위라 일반대학원 명시(A)만 알림 대상으로 유지
            if item["grade"] == "A":
                items.append(item)

    return items


def _fetch_jinhak(target_term: str) -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.get(JINHAK_PAGE_URL, timeout=TIMEOUT)
    response.raise_for_status()
    match = re.search(r"__APPLY_TOKEN\s*=\s*['\"]([^'\"]+)['\"]", response.text)
    sToken = match.group(1) if match else ""

    apiResponse = session.post(
        JINHAK_API_URL,
        json={},
        headers={"X-Requested-With": "XMLHttpRequest", "X-PM-TOKEN": sToken},
        timeout=TIMEOUT,
    )
    apiResponse.raise_for_status()
    dictPayload = json.loads(apiResponse.json().get("d", "{}"))
    items: list[dict] = []

    for dictUniv in dictPayload.get("Univdata", []):
        sName = normalize_space(f"{dictUniv.get('ShortName', '')} {dictUniv.get('ServiceName', '')}")
        sCategory = str(dictUniv.get("CategorytypeName", ""))

        if "대학원" not in sName and "대학원" not in sCategory:
            continue
        # 전기/후기 구분: 이름에 다른 학기가 명시되면 제외, 없으면 유지
        if "전기" in sName and target_term not in sName:
            continue

        sUrl = dictUniv.get("Link") or JINHAK_PAGE_URL
        sPeriod = f"{str(dictUniv.get('WriteFromTime', ''))[:10]} ~ {str(dictUniv.get('WriteToTime', ''))[:10]}"
        item = _item(
            "진학사어플라이", sName, sUrl,
            "진학사어플라이 대학원 원서접수",
            f"진학사어플라이 원서접수 목록에서 확인됨 (접수기간: {sPeriod}).",
        )

        if item["grade"] != "D":
            items.append(item)

    return items
