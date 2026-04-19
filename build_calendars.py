#!/usr/bin/env python3
"""Build per-pool, per-course ICS calendars from Toronto Open Data."""

import argparse
import csv
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SITE_URL = "https://swimcal.ca"
TEMPLATES_DIR = Path(__file__).parent / "templates"

DROP_IN_CSV_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca"
    "/dataset/1a5be46a-4039-48cd-a2d2-8e702abf9516"
    "/resource/90f7fffe-658b-4a79-bce3-a91c1b5886de"
    "/download/drop-in.csv"
)
FACILITIES_CSV_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca"
    "/dataset/cbea3a67-9168-4c6d-8186-16ac1a795b5b"
    "/resource/61691590-4c3f-42d3-94c5-443ad3856f64"
    "/download/parks-and-recreation-facilities-4326.csv"
)

SWIM_KEYWORDS = ("swim", "aqua", "water", "pool", "dive")
TZ = ZoneInfo("America/Toronto")
UID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "toronto-pool-calendars.v1")

VTIMEZONE = [
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


def fetch_csv(url):
    with urllib.request.urlopen(url) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8-sig"))))


def is_swim_course(title):
    t = (title or "").lower()
    return any(k in t for k in SWIM_KEYWORDS)


_MC_RE = re.compile(r"\bMc([a-z])")


def prettify(text):
    """Turn 'PAM McCONNELL AQUATIC CENTRE' into 'Pam McConnell Aquatic Centre'."""
    if not text or text == "None":
        return ""
    return _MC_RE.sub(lambda m: "Mc" + m.group(1).upper(), text.title())


def slugify(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def to_dt(date_str, hour, minute):
    return datetime(
        int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
        int(hour), int(minute), 0, tzinfo=TZ,
    )


def fmt_dt(dt):
    return dt.strftime("%Y%m%dT%H%M%S")


def escape_ics(text):
    return (text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\n", "\\n"))


def build_ics(sessions, course_title, location_name, location_address, location_url):
    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    calname = f"{course_title} — {location_name}"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Toronto Pool Calendars//v1//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics(calname)}",
        "X-WR-TIMEZONE:America/Toronto",
        *VTIMEZONE,
    ]

    for row in sessions:
        start = to_dt(row["First Date"], row["Start Hour"], row["Start Minute"])
        end = to_dt(row["First Date"], row["End Hour"], row["End Min"])
        uid = uuid.uuid5(UID_NAMESPACE, row["_id"]).hex

        age_min = (row.get("Age Min") or "").strip()
        age_max = (row.get("Age Max") or "").strip()
        if age_min and age_min != "None":
            if age_max and age_max != "None":
                age_note = f"Ages {age_min}–{age_max}"
            else:
                age_note = f"Ages {age_min}+"
        else:
            age_note = ""

        desc = [f"Location: {location_name}"]
        if location_address:
            desc.append(f"Address: {location_address}")
        if age_note:
            desc.append(age_note)
        desc.append("Free drop-in session.")
        if location_url:
            desc.append(location_url)
        desc.append("")
        desc.append("Data: City of Toronto Open Data (Open Government Licence – Toronto).")
        description = "\n".join(desc)

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@toronto-pool-calendars",
            f"DTSTAMP:{now_utc}",
            f"DTSTART;TZID=America/Toronto:{fmt_dt(start)}",
            f"DTEND;TZID=America/Toronto:{fmt_dt(end)}",
            f"SUMMARY:{escape_ics(course_title)}",
            f"DESCRIPTION:{escape_ics(description)}",
            f"LOCATION:{escape_ics(location_address or location_name)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="public")
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("Fetching drop-in schedule...", file=sys.stderr)
    drop_in = fetch_csv(DROP_IN_CSV_URL)
    print("Fetching facilities...", file=sys.stderr)
    facilities = {r["LOCATIONID"]: r for r in fetch_csv(FACILITIES_CSV_URL)}

    today_iso = datetime.now(TZ).date().isoformat()

    groups = {}
    for row in drop_in:
        if not is_swim_course(row["Course Title"]):
            continue
        if row["First Date"] < today_iso:
            continue
        key = (row["Location ID"], row["Course Title"])
        groups.setdefault(key, []).append(row)

    pools = {}
    for (loc_id, course), rows in sorted(groups.items()):
        rows.sort(key=lambda r: (r["First Date"], int(r["Start Hour"]), int(r["Start Minute"])))
        fac = facilities.get(loc_id)
        loc_name = prettify(fac["ASSET_NAME"]) if fac else f"Location {loc_id}"
        loc_addr = prettify(fac.get("ADDRESS", "")) if fac else ""
        loc_url = fac.get("URL", "") if fac else ""
        if loc_url == "None":
            loc_url = ""
        loc_coords = _parse_coords(fac.get("geometry", "")) if fac else None

        slug = slugify(course)
        pool_dir = out / "pools" / loc_id
        pool_dir.mkdir(parents=True, exist_ok=True)
        ics = build_ics(rows, course, loc_name, loc_addr, loc_url)
        (pool_dir / f"{slug}.ics").write_text(ics, encoding="utf-8")

        first = rows[0]
        next_dt = to_dt(first["First Date"], first["Start Hour"], first["Start Minute"])
        hour12 = next_dt.hour % 12 or 12
        ampm = "AM" if next_dt.hour < 12 else "PM"
        next_label = (
            f"{next_dt.strftime('%a %b')} {next_dt.day}, "
            f"{hour12}:{next_dt.minute:02d} {ampm}"
        )

        pool = pools.setdefault(loc_id, {
            "id": loc_id,
            "name": loc_name,
            "address": loc_addr,
            "url": loc_url,
            "coords": loc_coords,
            "calendars": [],
        })
        pool["calendars"].append({
            "course_title": course,
            "slug": slug,
            "ics_path": f"pools/{loc_id}/{slug}.ics",
            "session_count": len(rows),
            "next_session": next_label,
        })

    pools_list = sorted(pools.values(), key=lambda p: p["name"])
    for p in pools_list:
        p["calendars"].sort(key=lambda c: c["course_title"])

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "drop_in_csv": DROP_IN_CSV_URL,
            "facilities_csv": FACILITIES_CSV_URL,
            "license": "Open Government Licence – Toronto",
        },
        "pools": pools_list,
    }
    (out / "pools.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    total_cals = sum(len(p["calendars"]) for p in pools_list)
    print(
        f"Wrote {total_cals} calendars across {len(pools_list)} pools to {out}/.",
        file=sys.stderr,
    )

    render_site(out, pools_list, manifest["generated_at"], total_cals)
    sanity_check(pools_list, total_cals)


def _render(template_name, **subs):
    tmpl = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    for k, v in subs.items():
        tmpl = tmpl.replace(f"<!-- {{{{{k}}}}} -->", v)
    return tmpl


def _calendar_li(cal, pool_id, ics_href):
    course = html.escape(cal["course_title"])
    slug = cal["slug"]
    https_url = f"{SITE_URL}/pools/{pool_id}/{slug}.ics"
    webcal_url = https_url.replace("https:", "webcal:", 1)
    gcal_url = (
        "https://calendar.google.com/calendar/r?cid="
        + urllib.parse.quote(https_url, safe="")
    )
    return (
        "<li>"
        f'<span class="course">{course}</span>'
        f'<span class="count">{cal["session_count"]} upcoming</span>'
        f'<a class="cta" href="{html.escape(webcal_url)}">Subscribe</a>'
        f'<a class="cta" href="{html.escape(gcal_url)}" target="_blank" rel="noopener">Google</a>'
        f'<a class="cta" href="{ics_href}">Download</a>'
        f'<span class="next">next: {html.escape(cal["next_session"])}</span>'
        "</li>"
    )


def _search_text(pool):
    courses = " ".join(c["course_title"] for c in pool["calendars"])
    return f"{pool['name']} {pool.get('address', '')} {courses}".lower()


def _parse_coords(geometry_str):
    """Pull (lat, lng) from a facilities-CSV GeoJSON geometry cell."""
    if not geometry_str or geometry_str == "None":
        return None
    try:
        geo = json.loads(geometry_str)
    except json.JSONDecodeError:
        return None
    coords = geo.get("coordinates") or []
    if geo.get("type") == "MultiPoint" and coords:
        lng, lat = coords[0]
    elif geo.get("type") == "Point" and len(coords) == 2:
        lng, lat = coords
    else:
        return None
    return [lat, lng]


def _address_html(address, pool_name="", coords=None):
    if not address:
        return ""
    if coords:
        lat, lng = coords
        query = f"{lat},{lng}"
    else:
        query = urllib.parse.quote(
            f"{pool_name}, {address}, Toronto" if pool_name else address
        )
    href = f"https://www.google.com/maps/search/?api=1&query={query}"
    return f'<a href="{href}" target="_blank" rel="noopener">{html.escape(address)}</a>'


def render_site(out, pools_list, generated_at_iso, total_cals):
    # Per-pool pages
    for pool in pools_list:
        pool_id = pool["id"]
        lis = "\n".join(
            _calendar_li(c, pool_id, f"{c['slug']}.ics") for c in pool["calendars"]
        )
        address_line = _address_html(pool["address"], pool["name"], pool.get("coords"))
        city_link = (
            f'<a href="{html.escape(pool["url"])}">Official City of Toronto page for this pool</a>'
            if pool.get("url") else ""
        )
        meta_desc = (
            f"Free drop-in swim schedule at {pool['name']}"
            + (f" ({pool['address']})" if pool["address"] else "")
            + f". Subscribable calendar feeds for {len(pool['calendars'])} swim program(s)."
        )
        rendered = _render(
            "pool.html",
            pool_name=html.escape(pool["name"]),
            pool_address_line=address_line,
            canonical_url=f"{SITE_URL}/pools/{pool_id}/",
            meta_description=html.escape(meta_desc),
            calendars_html=lis,
            city_link_line=city_link,
        )
        (out / "pools" / pool_id / "index.html").write_text(rendered, encoding="utf-8")

    # Main index: SSR the whole pool list
    sections = []
    for pool in pools_list:
        pool_id = pool["id"]
        name = html.escape(pool["name"])
        lis = "\n".join(
            _calendar_li(c, pool_id, f"pools/{pool_id}/{c['slug']}.ics")
            for c in pool["calendars"]
        )
        addr_inner = _address_html(pool["address"], pool["name"], pool.get("coords"))
        addr_html = f'<p class="meta">{addr_inner}</p>' if addr_inner else ""
        sections.append(
            f'<section data-search="{html.escape(_search_text(pool), quote=True)}">'
            f'<h2><a href="pools/{pool_id}/">{name}</a></h2>'
            f"{addr_html}"
            f"<ul>{lis}</ul>"
            "</section>"
        )
    when = datetime.fromisoformat(generated_at_iso).astimezone().strftime("%b %d, %Y %I:%M %p")
    summary = (
        f"{len(pools_list)} pools · {total_cals} calendars · updated {when}"
    )
    index_html = _render(
        "index.html",
        pools_html="\n".join(sections),
        summary_line=html.escape(summary),
    )
    (out / "index.html").write_text(index_html, encoding="utf-8")

    # sitemap.xml
    today = datetime.now(TZ).date().isoformat()
    urls = [f"{SITE_URL}/"] + [f"{SITE_URL}/pools/{p['id']}/" for p in pools_list]
    sitemap_body = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>"
        for u in urls
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{sitemap_body}\n"
        "</urlset>\n"
    )
    (out / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    # robots.txt
    (out / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n",
        encoding="utf-8",
    )


def sanity_check(pools_list, total_cals):
    """Fail the build if output shape suggests upstream data broke.

    Thresholds are deliberately loose — seasonal lows can shrink total
    session counts substantially — but structural collapse (empty CSV,
    renamed columns, broken facilities join) drops counts far below these.
    """
    problems = []
    if len(pools_list) < 30:
        problems.append(f"only {len(pools_list)} pools (expected >= 30)")
    if total_cals < 100:
        problems.append(f"only {total_cals} calendars (expected >= 100)")
    fallbacks = sum(1 for p in pools_list if p["name"].startswith("Location "))
    if fallbacks > 5:
        problems.append(
            f"{fallbacks} pools fell back to placeholder names — "
            f"facilities join may be broken"
        )
    if problems:
        print("Sanity check failed:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
