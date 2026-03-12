#!/usr/bin/env python3
"""
Fetches Lane Swim schedule for Pam McConnell Aquatic Centre from Toronto Open Data
and generates an ICS calendar file you can import into any calendar app.
"""

import csv
import io
import sys
import uuid
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

LOCATION_ID = "2012"
LOCATION_NAME = "Pam McConnell Aquatic Centre"
LOCATION_ADDRESS = "640 Dundas St E, Toronto, ON M5A 2B8"

DROP_IN_CSV_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca"
    "/dataset/1a5be46a-4039-48cd-a2d2-8e702abf9516"
    "/resource/90f7fffe-658b-4a79-bce3-a91c1b5886de"
    "/download/drop-in.csv"
)

TZ = ZoneInfo("America/Toronto")


def fetch_lane_swim_sessions():
    print("Downloading schedule from Toronto Open Data...", file=sys.stderr)
    with urllib.request.urlopen(DROP_IN_CSV_URL) as r:
        content = r.read().decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(content))
    sessions = []
    for row in reader:
        if row.get("Location ID") != LOCATION_ID:
            continue
        if row.get("Course Title") != "Lane Swim":
            continue
        sessions.append(row)

    sessions.sort(key=lambda r: (r["First Date"], int(r["Start Hour"]), int(r["Start Minute"])))
    print(f"Found {len(sessions)} Lane Swim sessions.", file=sys.stderr)
    return sessions


def make_ics_datetime(date_str, hour, minute):
    """Return a timezone-aware datetime for use in ICS."""
    dt = datetime(
        int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
        int(hour), int(minute), 0,
        tzinfo=TZ,
    )
    return dt


def format_ics_dt(dt):
    """Format datetime as ICS TZID value."""
    return dt.strftime("%Y%m%dT%H%M%S")


def escape_ics(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics(sessions):
    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lane Swim Schedule//Pam McConnell//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Lane Swim – {LOCATION_NAME}",
        "X-WR-TIMEZONE:America/Toronto",
        # Embed timezone definition
        "BEGIN:VTIMEZONE",
        "TZID:America/Toronto",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:-0500",
        "TZOFFSETTO:-0400",
        "TZNAME:EDT",
        "DTSTART:19700308T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:-0400",
        "TZOFFSETTO:-0500",
        "TZNAME:EST",
        "DTSTART:19701101T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for row in sessions:
        start = make_ics_datetime(row["First Date"], row["Start Hour"], row["Start Minute"])
        end = make_ics_datetime(row["First Date"], row["End Hour"], row["End Min"])
        event_uid = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"pam-mcconnell-lane-swim-{row['_id']}-{row['First Date']}-{row['Start Hour']}-{row['Start Minute']}"
        ))

        age_min = row.get("Age Min", "")
        age_max = row.get("Age Max", "None")
        if age_min and age_min != "None":
            if age_max and age_max != "None":
                age_note = f"Ages {age_min}–{age_max}"
            else:
                age_note = f"Ages {age_min}+"
        else:
            age_note = ""

        description_parts = [f"Location: {LOCATION_NAME}", f"Address: {LOCATION_ADDRESS}"]
        if age_note:
            description_parts.append(age_note)
        description_parts.append("Free drop-in swim.")
        description_parts.append("https://www.toronto.ca/explore-enjoy/parks-recreation/places-spaces/parks-and-recreation-facilities/location/?id=2012")
        description = "\\n".join(description_parts)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{event_uid}",
            f"DTSTAMP:{now_utc}",
            f"DTSTART;TZID=America/Toronto:{format_ics_dt(start)}",
            f"DTEND;TZID=America/Toronto:{format_ics_dt(end)}",
            f"SUMMARY:Lane Swim – {LOCATION_NAME}",
            f"DESCRIPTION:{escape_ics(description)}",
            f"LOCATION:{escape_ics(LOCATION_ADDRESS)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    sessions = fetch_lane_swim_sessions()
    if not sessions:
        print("No Lane Swim sessions found.", file=sys.stderr)
        sys.exit(1)

    # Print human-readable schedule
    print(f"\nLane Swim Schedule – {LOCATION_NAME}")
    print("=" * 55)
    current_week = None
    for row in sessions:
        date = row["First Date"]
        week = date[:7]  # year-month as rough week grouping
        day = row["DayOftheWeek"]
        start_h, start_m = int(row["Start Hour"]), int(row["Start Minute"])
        end_h, end_m = int(row["End Hour"]), int(row["End Min"])

        def fmt_time(h, m):
            suffix = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {suffix}"

        print(f"  {day[:3]} {date}  {fmt_time(start_h, start_m)} – {fmt_time(end_h, end_m)}")

    print(f"\nTotal: {len(sessions)} sessions")

    # Write ICS file
    ics_content = build_ics(sessions)
    output_path = "lane_swim_pam_mcconnell.ics"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    print(f"\nCalendar file written: {output_path}")
    print("Import this file into Apple Calendar, Google Calendar, Outlook, etc.")


if __name__ == "__main__":
    main()
