from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from .utils import DATA_DIR, DurableStateError, load_durable_json, load_json, save_json


RESULT_FIELDS = [
    "checked_at", "university_name", "region", "city", "title", "url", "source_type", "source_query",
    "notice_date", "application_start_date", "application_end_date", "deadline_status",
    "registration_score", "external_score", "computer_score", "freshness_score", "grade",
    "external_applicant_status", "computer_course_status", "possible_departments", "possible_computer_courses",
    "course_evidence_url", "course_evidence_text", "attachment_urls", "image_urls", "ocr_checked", "ocr_text_found", "ocr_evidence",
    "date_source", "date_conflict", "matched_keywords", "reason", "content_fingerprint", "change_type",
    "previous_grade", "is_new"
]

GRADUATE_ADMISSION_FIELDS = [
    "checked_at", "university_name", "region", "city", "board_type", "title", "url", "notice_date",
    "grade", "matched_keywords", "reason", "attachment_urls", "is_new"
]

HISTORY_FIELDS = [
    "university_name", "region", "semester", "notice_date", "application_start_date",
    "application_end_date", "url", "title", "source",
]


def _csv_safe_value(value: object) -> object:
    if not isinstance(value, str):
        return value

    trimmed_value = value.lstrip()
    if trimmed_value.startswith(("=", "+", "-", "@")):
        return "'" + value

    return value


def _load_seen_values(path: Path) -> set[str]:
    data = load_durable_json(path, [], (list, dict))

    if isinstance(data, list):
        if not all(isinstance(value, str) for value in data):
            raise DurableStateError(f"Durable seen state contains a non-string value: {path}")
        return set(data)

    values: set[str] = set()
    for key, nested_values in data.items():
        if not isinstance(key, str):
            raise DurableStateError(f"Durable seen state contains a non-string key: {path}")
        values.add(key)

        if nested_values is None:
            continue
        if not isinstance(nested_values, list) or not all(
            isinstance(value, str) for value in nested_values
        ):
            raise DurableStateError(f"Durable seen state contains invalid nested values: {path}")
        values.update(nested_values)

    return values


class Storage:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.seen_path = data_dir / "seen_urls.json"
        self.results_csv = data_dir / "results.csv"
        self.results_json = data_dir / "results.json"
        self.debug_json = data_dir / "debug_results.json"
        self.history_csv = data_dir / "university_history.csv"
        self.notice_state_path = data_dir / "notice_state.json"

    def load_seen(self) -> set[str]:
        setSeenUrls = _load_seen_values(self.seen_path)
        lstPreviousItems = load_json(self.results_json, [])

        for dictItem in lstPreviousItems:
            sUrl = dictItem.get("url", "")
            sGrade = dictItem.get("grade", "")

            if sGrade == "C" and sUrl:
                setSeenUrls.add(sUrl)

        return setSeenUrls

    def mark_is_new(self, items: list[dict]) -> list[dict]:
        seen = self.load_seen()
        for item in items:
            item["is_new"] = item["url"] not in seen
        return items

    def mark_changes(self, items: list[dict]) -> list[dict]:
        previous_state = load_durable_json(self.notice_state_path, {}, dict)
        seen_urls = self.load_seen()
        if not isinstance(previous_state, dict):
            previous_state = {}

        for item in items:
            url = item.get("url", "")
            previous = previous_state.get(url, {}) if url else {}
            item["previous_grade"] = previous.get("grade", "")

            if not previous and url in seen_urls:
                item["change_type"] = "unchanged"
            elif not previous:
                item["change_type"] = "new"
            elif previous.get("content_fingerprint") != item.get("content_fingerprint"):
                item["change_type"] = "content_changed"
            elif previous.get("grade") != item.get("grade"):
                item["change_type"] = "grade_changed"
            elif previous.get("deadline_status") != item.get("deadline_status"):
                item["change_type"] = "deadline_changed"
            else:
                item["change_type"] = "unchanged"

        return items

    def update_notice_state(self, items: list[dict]) -> None:
        state = load_durable_json(self.notice_state_path, {}, dict)

        if not isinstance(state, dict):
            state = {}

        for item in items:
            url = item.get("url", "")
            if not url:
                continue

            state[url] = {
                "content_fingerprint": item.get("content_fingerprint", ""),
                "grade": item.get("grade", ""),
                "deadline_status": item.get("deadline_status", ""),
                "checked_at": item.get("checked_at", ""),
            }

        save_json(self.notice_state_path, state)

    def update_seen(self, notified_items: list[dict]) -> None:
        seen = self.load_seen()
        for item in notified_items:
            seen.add(item["url"])
        save_json(self.seen_path, sorted(seen))

    def mark_notified(self, notified_items: list[dict]) -> None:
        """Persist authoritative change state before the secondary seen index."""
        self.update_notice_state(notified_items)
        self.update_seen(notified_items)

    def dedupe(self, items: list[dict]) -> list[dict]:
        result: list[dict] = []
        keys: set[str] = set()
        for item in items:
            key = item.get("url") or self._title_key(item)
            attachment_key = "|".join(item.get("attachment_urls") or [])
            combined = key + attachment_key
            if combined in keys:
                continue
            keys.add(combined)
            result.append(item)
        return result

    def save_results(self, items: list[dict], debug_items: list[dict] | None = None) -> None:
        public_items = [self._serialize_item(i) for i in items if i.get("grade") != "D"]
        save_json(self.results_json, public_items)
        self._write_csv(self.results_csv, RESULT_FIELDS, public_items)
        if debug_items is not None:
            save_json(self.debug_json, [self._serialize_item(i) for i in debug_items])
        self._save_history(items)

    def ensure_empty_files(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for path in [self.results_csv, self.history_csv]:
            if not path.exists():
                with path.open("w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(RESULT_FIELDS if path == self.results_csv else HISTORY_FIELDS)
        for path, default in [
            (self.results_json, []),
            (self.seen_path, []),
            (self.debug_json, []),
            (self.notice_state_path, {}),
        ]:
            if not path.exists():
                save_json(path, default)

    def _serialize_item(self, item: dict) -> dict:
        out = {}
        for field in RESULT_FIELDS:
            value = item.get(field, "")
            if isinstance(value, list):
                value = "; ".join(value)
            elif isinstance(value, dict):
                value = " | ".join(f"{key}: {text}" for key, text in value.items())
            out[field] = value
        return out

    def _save_history(self, items: list[dict]) -> None:
        existing_rows = self._load_history()
        current_rows = []

        for item in items:
            if item.get("registration_score", 0) < 40:
                continue
            semester = "2학기" if "2학기" in item.get("title", "") else "1학기" if "1학기" in item.get("title", "") else ""
            current_rows.append({
                "university_name": item.get("university_name", ""),
                "region": item.get("region", ""),
                "semester": semester,
                "notice_date": item.get("notice_date", ""),
                "application_start_date": item.get("application_start_date", ""),
                "application_end_date": item.get("application_end_date", ""),
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "source": item.get("source_type", ""),
            })

        merged_rows: dict[tuple[str, ...], dict] = {}
        for row in sorted(existing_rows, key=self._history_row_sort_key):
            merged_rows[self._history_key(row)] = row
        for row in sorted(current_rows, key=self._history_row_sort_key):
            merged_rows[self._history_key(row)] = row

        rows = sorted(merged_rows.values(), key=self._history_row_sort_key)
        self._write_csv(self.history_csv, HISTORY_FIELDS, rows)

    def _load_history(self) -> list[dict]:
        if not self.history_csv.exists():
            return []

        with self.history_csv.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return [
                {field: row.get(field, "") or "" for field in HISTORY_FIELDS}
                for row in reader
            ]

    def _history_key(self, row: dict) -> tuple[str, ...]:
        url = str(row.get("url", "")).strip()
        title = str(row.get("title", "")).strip()
        university_name = str(row.get("university_name", "")).strip()

        if url:
            return ("url", url)
        if title:
            return ("title", university_name, title)
        return ("row", *(str(row.get(field, "")) for field in HISTORY_FIELDS))

    def _history_row_sort_key(self, row: dict) -> tuple[str, ...]:
        return tuple(str(row.get(field, "")) for field in HISTORY_FIELDS)

    def _title_key(self, item: dict) -> str:
        raw = f"{item.get('university_name')}::{item.get('title')}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _write_csv(self, path: Path, fields: list[str], rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _csv_safe_value(row.get(field, "")) for field in fields})


class GraduateAdmissionStorage:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.seen_path = data_dir / "seen_graduate_admission_urls.json"
        self.summary_state_path = data_dir / "graduate_admission_summary_state.json"
        self.results_csv = data_dir / "graduate_admission_results.csv"
        self.results_json = data_dir / "graduate_admission_results.json"

    def load_seen(self) -> set[str]:
        return _load_seen_values(self.seen_path)

    def mark_is_new(self, items: list[dict]) -> list[dict]:
        seen = self.load_seen()
        previous_items = load_json(self.results_json, [])
        previous_by_url = {
            item.get("url", ""): item
            for item in previous_items
            if isinstance(item, dict) and item.get("url")
        }

        for item in items:
            item["is_new"] = not self._has_seen_item(item, seen, previous_by_url)

        return items

    def update_seen(self, notified_items: list[dict]) -> None:
        seen = self.load_seen()

        for item in notified_items:
            seen.update(self._seen_keys(item))

        save_json(self.seen_path, sorted(seen))

    def dedupe(self, items: list[dict]) -> list[dict]:
        result: list[dict] = []
        keys: set[str] = set()

        for item in items:
            key = self._content_fingerprint(item)
            if key in keys:
                continue
            keys.add(key)
            result.append(item)

        return result

    def should_send_empty_summary(self, items: list[dict], active_count: int, disabled_count: int) -> bool:
        state = load_durable_json(self.summary_state_path, {}, dict)
        fingerprint = self.empty_summary_fingerprint(items, active_count, disabled_count)
        return state.get("fingerprint") != fingerprint

    def update_empty_summary_state(self, items: list[dict], active_count: int, disabled_count: int) -> None:
        save_json(
            self.summary_state_path,
            {
                "fingerprint": self.empty_summary_fingerprint(items, active_count, disabled_count),
                "candidate_count": len(items),
                "active_count": active_count,
                "disabled_count": disabled_count,
            },
        )

    def empty_summary_fingerprint(self, items: list[dict], active_count: int, disabled_count: int) -> str:
        item_keys = sorted(self._content_fingerprint(item) for item in items)
        raw = "::".join([str(active_count), str(disabled_count), *item_keys])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def save_results(self, items: list[dict]) -> None:
        serialized_items = [self._serialize_item(item) for item in items]
        save_json(self.results_json, serialized_items)
        self._write_csv(self.results_csv, GRADUATE_ADMISSION_FIELDS, serialized_items)

    def _serialize_item(self, item: dict) -> dict:
        out = {}

        for field in GRADUATE_ADMISSION_FIELDS:
            value = item.get(field, "")
            if isinstance(value, list):
                value = "; ".join(value)
            out[field] = value

        return out

    def _title_key(self, item: dict) -> str:
        raw = f"{item.get('university_name')}::{self._normalized_title(item.get('title', ''))}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _has_seen_item(self, item: dict, seen: set[str], previous_by_url: dict[str, dict]) -> bool:
        fingerprint = self._content_fingerprint(item)
        if fingerprint in seen:
            return True

        url = item.get("url", "")
        if not url or url not in seen:
            return False

        previous_item = previous_by_url.get(url)
        if previous_item is None:
            return True

        return self._content_fingerprint(previous_item) == fingerprint

    def _seen_keys(self, item: dict) -> set[str]:
        return {self._content_fingerprint(item)}

    def _content_fingerprint(self, item: dict) -> str:
        attachments = "|".join(sorted(self._list_values(item.get("attachment_urls"))))
        matched_keywords = "|".join(sorted(self._list_values(item.get("matched_keywords"))))
        notice_date = item.get("notice_date", "")

        if "어플라이" in item.get("board_type", ""):
            # 접수중 포털 항목은 확인일을 게시일로 사용하므로 날짜가 바뀌어도 같은 공고다.
            notice_date = ""

        raw = "::".join([
            item.get("university_name", ""),
            item.get("board_type", ""),
            self._normalized_title(item.get("title", "")),
            notice_date,
            matched_keywords,
            attachments,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _list_values(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(";") if item.strip()]
        return []

    def _normalized_title(self, title: str) -> str:
        normalized = re.sub(r"\[[^\]]+\]|\([^)]+\)", " ", title.lower())
        normalized = re.sub(r"20\d{2}|전기|후기|수시|정시|1차|2차|3차", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _write_csv(self, path: Path, fields: list[str], rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _csv_safe_value(row.get(field, "")) for field in fields})
