from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.exceptions import SSLError

from .utils import normalize_space, truncate, unique_preserve_order

HTML_PARSER = "lxml"


class CourseFinder:
    def __init__(self, keywords: dict, timeout: int = 12):
        self.keywords = keywords
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 university-course-watcher/1.0"})
        self._evidence_cache: dict[str, tuple[str, str]] = {}

    def enrich(self, item: dict, university: dict) -> dict:
        if item.get("grade") not in {"A", "B", "C"}:
            return item
        if item.get("computer_course_status") == "가능성 높음":
            item["possible_computer_courses"] = self._matched_courses(item.get("course_evidence_text", "") + " " + item.get("title", ""))
            return item

        domains = university.get("domains", [])
        if not domains:
            return item
        homepage = f"https://www.{domains[0]}"
        evidence = ""
        evidence_url = ""
        for page_url in [homepage, item.get("url", "")]:
            if not page_url:
                continue
            evidence, evidence_url = self._find_evidence(page_url)
            if evidence:
                break

        item["possible_departments"] = self._matched_departments(evidence)
        item["possible_computer_courses"] = self._matched_courses(evidence)
        item["course_evidence_url"] = evidence_url
        item["course_evidence_text"] = truncate(evidence, 350)
        if item["possible_computer_courses"] and item.get("computer_course_status") != "가능성 높음":
            item["computer_course_status"] = "확인 필요"
        return item

    def _find_evidence(self, page_url: str) -> tuple[str, str]:
        if page_url in self._evidence_cache:
            return self._evidence_cache[page_url]

        tupleEvidence = self._scan_page_for_evidence(page_url)
        self._evidence_cache[page_url] = tupleEvidence
        return tupleEvidence

    def _scan_page_for_evidence(self, page_url: str) -> tuple[str, str]:
        try:
            response = self._get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, HTML_PARSER)
            text = normalize_space(soup.get_text(" "))
        except Exception:
            return "", ""

        if self._has_course_signal(text):
            return text, page_url

        for a in soup.find_all("a", href=True):
            label = normalize_space(a.get_text(" "))
            if any(k in label for k in self.keywords["course_search"]):
                href = urljoin(page_url, a["href"])
                try:
                    sub = self._get(href)
                    sub.raise_for_status()
                    sub_text = normalize_space(BeautifulSoup(sub.text, HTML_PARSER).get_text(" "))
                except Exception:
                    continue
                if self._has_course_signal(sub_text):
                    return sub_text, href

        return "", ""

    def _has_course_signal(self, text: str) -> bool:
        return any(name in text for name in self.keywords["course_names"]) or any(key in text for key in self.keywords["course_search"])

    def _matched_courses(self, text: str) -> list[str]:
        return unique_preserve_order([name for name in self.keywords["course_names"] if name in text])

    def _matched_departments(self, text: str) -> list[str]:
        candidates = ["컴퓨터공학과", "소프트웨어학과", "AI융합학과", "인공지능학과", "정보보안학과", "데이터사이언스학과"]
        return unique_preserve_order([name for name in candidates if name in text])

    def _get(self, url: str) -> requests.Response:
        try:
            return self.session.get(url, timeout=self.timeout)
        except SSLError:
            return self.session.get(url, timeout=self.timeout, verify=False)
