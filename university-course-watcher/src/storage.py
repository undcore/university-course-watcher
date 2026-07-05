from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .utils import DATA_DIR, load_json, save_json


RESULT_FIELDS = [
    "checked_at", "university_name", "region", "city", "title", "url", "source_type", "source_query",
    "notice_date", "application_start_date", "application_end_date", "deadline_status",
    "registration_score", "external_score", "computer_score", "freshness_score", "grade",
    "external_applicant_status", "computer_course_status", "possible_departments", "possible_computer_courses",
    "course_evidence_url", "course_evidence_text", "attachment_urls", "matched_keywords", "reason", "is_new"
]

GRADUATE_ADMISSION_FIELDS = [
    "checked_at", "university_name", "region", "city", "board_type", "title", "url", "notice_date",
    "grade", "matched_keywords", "reason", "attachment_urls", "is_new"
]

HISTORY_FIELDS = [
    "university_name", "region", "semester", "notice_date", "application_start_date",
    "application_end_date", "url", "title", "source", "first_seen_at", "last_seen_at"
]


class Storage:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.seen_path = data_dir / "seen_urls.json"
        self.results_csv = data_dir / "results.csv"
        self.results_json = data_dir / "results.json"
        self.debug_json = data_dir / "debug_results.json"
        self.history_csv = data_dir / "university_history.csv"

    def load_seen(self) -> set[str]:
        data = load_json(self.seen_path, [])
        setSeenUrls = set(data if isinstance(data, list) else data.keys())
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

    def update_seen(self, notified_items: list[dict]) -> None:
        seen = self.load_seen()
        for item in notified_items:
            seen.add(item["url"])
        save_json(self.seen_path, sorted(seen))

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
        for path, default in [(self.results_json, []), (self.seen_path, []), (self.debug_json, [])]:
            if not path.exists():
                save_json(path, default)

    def _serialize_item(self, item: dict) -> dict:
        out = {}
        for field in RESULT_FIELDS:
            value = item.get(field, "")
            if isinstance(value, list):
                value = "; ".join(value)
            out[field] = value
        return out

    def _save_history(self, items: list[dict]) -> None:
        new_rows = []
        for item in items:
            if item.get("registration_score", 0) < 40:
                continue
            semester = "2학기" if "2학기" in item.get("title", "") else "1학기" if "1학기" in item.get("title", "") else ""
            new_rows.append({
                "university_name": item.get("university_name", ""),
                "region": item.get("region", ""),
                "semester": semester,
                "notice_date": item.get("notice_date", ""),
                "application_start_date": item.get("application_start_date", ""),
                "application_end_date": item.get("application_end_date", ""),
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "source": item.get("source_type", ""),
                "checked_at": item.get("checked_at", ""),
            })
        if new_rows:
            self._merge_history(new_rows)

    def _read_history(self) -> list[dict]:
        if not self.history_csv.exists():
            return []
        with self.history_csv.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def _merge_history(self, new_rows: list[dict]) -> None:
        """Accumulate history instead of overwriting.

        Existing rows are kept; a notice already recorded (same url+title) refreshes
        its evolving fields and last_seen_at, while genuinely new notices are appended
        with first_seen_at/last_seen_at stamped from the current run.
        """
        merged: list[dict] = self._read_history()
        index = {(row.get("url", ""), row.get("title", "")): row for row in merged}
        updatable = ("region", "semester", "notice_date", "application_start_date",
                     "application_end_date", "source")

        for row in new_rows:
            stamp = row.pop("checked_at", "") or ""
            key = (row["url"], row["title"])
            existing = index.get(key)
            if existing is None:
                row["first_seen_at"] = stamp
                row["last_seen_at"] = stamp
                index[key] = row
                merged.append(row)
                continue
            existing["last_seen_at"] = stamp or existing.get("last_seen_at", "")
            if not existing.get("first_seen_at"):
                existing["first_seen_at"] = stamp
            for field in updatable:
                if row.get(field):
                    existing[field] = row[field]

        self._write_csv(self.history_csv, HISTORY_FIELDS, merged)

    def _title_key(self, item: dict) -> str:
        raw = f"{item.get('university_name')}::{item.get('title')}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _write_csv(self, path: Path, fields: list[str], rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})


class GraduateAdmissionStorage:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.seen_path = data_dir / "seen_graduate_admission_urls.json"
        self.results_csv = data_dir / "graduate_admission_results.csv"
        self.results_json = data_dir / "graduate_admission_results.json"

    def load_seen(self) -> set[str]:
        data = load_json(self.seen_path, [])
        return set(data if isinstance(data, list) else data.keys())

    def mark_is_new(self, items: list[dict]) -> list[dict]:
        seen = self.load_seen()

        for item in items:
            item["is_new"] = item.get("url", "") not in seen

        return items

    def update_seen(self, notified_items: list[dict]) -> None:
        seen = self.load_seen()

        for item in notified_items:
            if item.get("url"):
                seen.add(item["url"])

        save_json(self.seen_path, sorted(seen))

    def dedupe(self, items: list[dict]) -> list[dict]:
        result: list[dict] = []
        keys: set[str] = set()

        for item in items:
            key = item.get("url") or self._title_key(item)
            if key in keys:
                continue
            keys.add(key)
            result.append(item)

        return result

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
        raw = f"{item.get('university_name')}::{item.get('title')}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _write_csv(self, path: Path, fields: list[str], rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
