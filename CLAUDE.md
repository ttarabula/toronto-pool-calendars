# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo does

Generates a static site of subscribable ICS calendars — one per (Toronto aquatic centre × drop-in swim course) — from the city's open data, and publishes it via GitHub Pages. Users subscribe in Apple/Google/Outlook Calendar using `webcal://` or a Google `cid=` link; the city's schedule updates flow through automatically because calendar apps repoll the URL.

## Running

```
python3 build_calendars.py --output-dir public
```

Python 3.9+ standard library only (uses `zoneinfo`). Writes `public/pools/<location_id>/<course-slug>.ics` and `public/pools.json`. The hand-written `public/index.html` reads the manifest at runtime and renders subscribe links — so a local preview is just `python3 -m http.server --directory public` then `http://localhost:8000`.

## Deployment

`.github/workflows/build.yml` runs daily (~6am Toronto), on push to `main`, and on manual dispatch. It executes `build_calendars.py`, uploads `public/` as the Pages artifact, and deploys via `actions/deploy-pages` — no `gh-pages` branch, no commit spam. One-time: **Settings → Pages → Source: GitHub Actions**.

## Data pipeline

Two Toronto Open Data CSVs, joined on Location ID:

- **drop-in.csv** (`DROP_IN_CSV_URL`): session-level rows across all programs city-wide. Columns of note: `Location ID`, `Course Title`, `First Date`, `Start Hour`/`Start Minute`, `End Hour`/`End Min` (note the asymmetric name — comes from upstream, don't "fix" it), `_id` (stable session identifier).
- **parks-and-recreation-facilities-4326.csv** (`FACILITIES_CSV_URL`): supplies `ASSET_NAME` (location name), `ADDRESS`, and the canonical Toronto.ca URL. Values arrive UPPERCASE; `prettify()` title-cases them with a `Mc` fix for Toronto's many `McConnell`/`McCormick`-style names.

Filters, in order: swim-related course title (`title.lower()` contains any of `swim`, `aqua`, `water`, `pool`, `dive`); date is today or later; group by `(location_id, course_title)`. This keyword-based filter intentionally replaces the old single-pool `Course Title == "Lane Swim"` exact match — variants like "Lane Swim: Older Adult" are now their own calendars rather than being excluded.

Not every location in drop-in.csv is present in the facilities CSV (currently 1 of 49 swim locations is missing). The script falls back to `Location <id>` with no address when the join fails — don't hard-require facility data.

## ICS details

- Events are timezone-aware (`TZID=America/Toronto`) and the ICS file embeds a full `VTIMEZONE` with DST rules so importers don't resolve the zone themselves.
- Event UIDs are deterministic: `uuid5(UID_NAMESPACE, row["_id"])`. Same underlying session → same UID → calendar clients update in place rather than duplicating on re-subscribe.
- `escape_ics` expects **real `\n` newlines** in its input and emits the ICS `\n` escape. Don't pre-escape newlines before passing through — that was a bug during initial development (double-escape produced literal `\\n` in the output).

## Subscription URL forms (for the index page)

- Apple/iOS/Outlook: `webcal://host/path.ics` — swap the `https` scheme for `webcal` on the absolute URL.
- Google Calendar: `https://calendar.google.com/calendar/r?cid=<url-encoded https ICS URL>`.
- Plain download: the `https://` URL served by Pages.

## Attribution

The Open Government Licence – Toronto requires attribution. It's embedded in each ICS event's `DESCRIPTION` and in the site footer; keep it in both if you refactor.
