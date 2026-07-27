from __future__ import annotations

import json
import os
import re
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
import yaml
from bs4 import BeautifulSoup, Tag

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config.yml"))
STATE_PATH = Path(os.getenv("STATE_PATH", "state.json"))
BASE_URL = "https://classes.uwaterloo.ca/cgi-bin/cgiwrap/infocour/salook.pl"
USER_AGENT = "uw-section-avail/2.0 (GitHub Actions section availability checker)"


@dataclass(frozen=True)
class Course:
    level: str
    term: str
    subject: str
    course_number: str
    class_numbers: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.subject} {self.course_number}"


@dataclass(frozen=True)
class Section:
    course: Course
    class_number: str
    component: str
    section: str
    enrolment_capacity: int
    enrolment_total: int
    waitlist_capacity: int | None
    waitlist_total: int | None
    details: str
    url: str

    @property
    def seats_available(self) -> int:
        return max(self.enrolment_capacity - self.enrolment_total, 0)

    @property
    def is_open(self) -> bool:
        return self.enrolment_total < self.enrolment_capacity

    @property
    def state_key(self) -> str:
        # Class numbers can be reused in another term, so include all course data.
        return ":".join(
            [
                self.course.term,
                self.course.subject,
                self.course.course_number,
                self.class_number,
            ]
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object.")
    return data


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalise_course(raw: dict[str, Any], default_level: str) -> Course:
    required = ["term", "subject", "course_number", "class_numbers"]
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError("A course entry is missing config key(s): " + ", ".join(missing))

    class_numbers = raw["class_numbers"]
    if not isinstance(class_numbers, list) or not class_numbers:
        raise ValueError("Each course's class_numbers must be a non-empty YAML list.")

    return Course(
        level=str(raw.get("level", default_level)).strip(),
        term=str(raw["term"]).strip(),
        subject=str(raw["subject"]).strip().upper(),
        course_number=str(raw["course_number"]).strip(),
        class_numbers=tuple(str(number).strip() for number in class_numbers),
    )


def parse_courses(config: dict[str, Any]) -> list[Course]:
    default_level = str(config.get("default_level", "under")).strip()
    raw_courses = config.get("courses")
    if not isinstance(raw_courses, list) or not raw_courses:
        raise ValueError("config.yml must contain a non-empty courses list.")

    courses: list[Course] = []
    seen: set[str] = set()
    for raw in raw_courses:
        if not isinstance(raw, dict):
            raise ValueError("Each item under courses must be a YAML object.")
        course = normalise_course(raw, default_level)
        for class_number in course.class_numbers:
            key = f"{course.term}:{course.subject}:{course.course_number}:{class_number}"
            if key in seen:
                raise ValueError(f"Duplicate monitored section in config: {key}")
            seen.add(key)
        courses.append(course)
    return courses


def course_url(course: Course) -> str:
    params = {
        "level": course.level,
        "sess": course.term,
        "subject": course.subject,
        "cournum": course.course_number,
    }
    return f"{BASE_URL}?{urlencode(params)}"


def integer(text: str) -> int | None:
    text = text.strip().replace(",", "")
    return int(text) if re.fullmatch(r"\d+", text) else None


def row_cells(row: Tag) -> list[str]:
    return [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"], recursive=False)]


def find_section_row(soup: BeautifulSoup, class_number: str) -> Tag | None:
    for row in soup.find_all("tr"):
        cells = row_cells(row)
        if cells and cells[0].strip() == class_number:
            return row
    return None


def parse_section(row: Tag, course: Course, class_number: str, url: str) -> Section:
    cells = row_cells(row)
    if len(cells) < 11:
        raise ValueError(
            f"Unexpected Waterloo table layout for {course.label} class {class_number}: {cells!r}"
        )

    cap = integer(cells[7])
    total = integer(cells[8])
    wait_cap = integer(cells[9])
    wait_total = integer(cells[10])

    if cap is None or total is None:
        raise ValueError(
            f"Could not read enrolment capacity/total for {course.label} "
            f"class {class_number}: {cells!r}"
        )

    return Section(
        course=course,
        class_number=class_number,
        component=cells[1],
        section=cells[2],
        enrolment_capacity=cap,
        enrolment_total=total,
        waitlist_capacity=wait_cap,
        waitlist_total=wait_total,
        details=" | ".join(cells[11:]),
        url=url,
    )


def fetch_course_sections(course: Course) -> list[Section]:
    url = course_url(course)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    sections: list[Section] = []
    missing: list[str] = []

    for class_number in course.class_numbers:
        row = find_section_row(soup, class_number)
        if row is None:
            missing.append(class_number)
            continue
        sections.append(parse_section(row, course, class_number, url))

    if missing:
        raise RuntimeError(
            f"Could not find class number(s) {', '.join(missing)} on the "
            f"{course.term} {course.label} course page: {url}"
        )
    return sections


def gmail_settings() -> tuple[str, str, str]:
    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    recipient = os.environ.get("NOTIFY_EMAIL", sender).strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")

    missing = [
        name
        for name, value in {
            "GMAIL_ADDRESS": sender,
            "GMAIL_APP_PASSWORD": password,
            "NOTIFY_EMAIL/GMAIL_ADDRESS": recipient,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing email setting(s): " + ", ".join(missing))
    return sender, recipient, password


def send_email(opened: list[Section], project_name: str) -> None:
    sender, recipient, password = gmail_settings()

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"[{project_name}] {len(opened)} Waterloo section(s) open"

    lines = ["The following monitored Waterloo section(s) are open:", ""]
    for item in opened:
        lines.extend(
            [
                f"Course: {item.course.label}",
                f"Term: {item.course.term}",
                f"Class number: {item.class_number}",
                f"Component/section: {item.component} {item.section}",
                f"Enrolment: {item.enrolment_total}/{item.enrolment_capacity}",
                f"Seats available: {item.seats_available}",
                f"Details: {item.details or 'Not listed'}",
                f"Course page: {item.url}",
                "",
            ]
        )
    message.set_content("\n".join(lines))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)


def main() -> int:
    config = load_yaml(CONFIG_PATH)
    courses = parse_courses(config)
    project_name = str(config.get("project_name", "uw-section-avail"))
    previous = load_state(STATE_PATH)

    sections: list[Section] = []
    for course in courses:
        sections.extend(fetch_course_sections(course))

    newly_opened: list[Section] = []
    current_state: dict[str, Any] = {}

    for item in sections:
        was_open = bool(previous.get(item.state_key, {}).get("open", False))
        if item.is_open and not was_open:
            newly_opened.append(item)

        current_state[item.state_key] = {
            "term": item.course.term,
            "subject": item.course.subject,
            "course_number": item.course.course_number,
            "class_number": item.class_number,
            "open": item.is_open,
            "enrolment_capacity": item.enrolment_capacity,
            "enrolment_total": item.enrolment_total,
            "seats_available": item.seats_available,
        }

        status = "OPEN" if item.is_open else "FULL"
        print(
            f"{item.course.term} {item.course.label} class {item.class_number}: "
            f"{status} — {item.enrolment_total}/{item.enrolment_capacity} enrolled"
        )

    # Only save an open state after Gmail accepts the notification, allowing a
    # later run to retry if sending fails.
    if newly_opened:
        send_email(newly_opened, project_name)
        print(
            "Email sent for: "
            + ", ".join(
                f"{item.course.label} class {item.class_number}" for item in newly_opened
            )
        )
    else:
        print("No newly opened monitored sections.")

    save_state(STATE_PATH, current_state)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
