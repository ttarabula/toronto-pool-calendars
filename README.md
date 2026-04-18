# Toronto Pool Calendars

Subscribable calendar feeds for the free drop-in swim schedule at every City of Toronto aquatic centre, built from the city's open data.

**Live site: https://swimcal.ca/**

Users subscribe with `webcal://` (Apple/iOS/Outlook) or the Google "add by URL" link. Their calendar app re-polls periodically, so new sessions the city publishes flow through automatically — no download, no account, no app.

## How it works

1. A daily GitHub Actions run (`.github/workflows/build.yml`) executes `build_calendars.py`.
2. The script downloads two Toronto Open Data CSVs — drop-in programs and parks & recreation facilities — joins on Location ID, filters to swim-related courses from today forward, and writes one ICS per (pool × course) plus a `pools.json` manifest.
3. `public/` is uploaded as a Pages artifact and deployed. The static page at `public/index.html` reads the manifest at runtime and renders the Subscribe / Google / `.ics` links.

Event UIDs are deterministic (`uuid5` over the source row's `_id`), so re-subscribing updates existing events in place rather than duplicating them.

## Running locally

Python 3.9+ standard library only (uses `zoneinfo`):

```sh
python3 build_calendars.py --output-dir public
python3 -m http.server --directory public
```

Then open http://localhost:8000/.

## Data & attribution

Schedule and facility data from the [City of Toronto Open Data Portal](https://open.toronto.ca/), used under the [Open Government Licence – Toronto](https://open.toronto.ca/about/frequently-asked-questions/). This project is not affiliated with the City of Toronto. The official [swimming page](https://www.toronto.ca/explore-enjoy/parks-recreation/program-activities/swim-water-activities/swimming-water-play/) remains the authoritative source, especially around holidays, closures, and unplanned maintenance.

## License

Code is released under the [MIT License](LICENSE). Fork, adapt, run it for another city — the hard part here was identifying the two datasets and the join key; the rest is boilerplate.
