# HIT Athletics Track GPX Route Generator

[中文说明](README.md)

This small utility generates GPX tracks for iPhone Core Location/DVT testing. It currently supports:

- HIT Campus I athletics track (default)
- HIT Campus II athletics track

The route is not a fixed template. When `--seed` is omitted, every run gets fresh operating-system randomness for the start position, lateral track offset, per-lap pace, and route waveform. The selected seed is printed so a particular run can be reproduced later.

## Quick start

The generator itself uses only the Python standard library. `pymobiledevice3` is needed only when `--play` is used to play a route to an iPhone.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Generate the default 2.2 km Campus I route:

```bash
python3 hit_run_simulator.py \
  --campus campus1 \
  --distance 2200 \
  --pace 5:00
```

Generate the Campus II athletics-track route:

```bash
python3 hit_run_simulator.py \
  --campus campus2 \
  --distance 2200 \
  --pace 5:00
```

Without `--output`, Campus I is written to `routes/hit_campus_2_2km.gpx` and Campus II to `routes/hit_campus_ii_2_2km.gpx`. The `routes/*.gpx` pattern is ignored by Git so personal generated files are not accidentally published.

## Route sources

The source map geometry is cached in the script. Each campus gets its own local metre projection before lane offsets are applied:

| Option | Route | Embedded geometry |
| --- | --- | --- |
| `campus1` | Campus I athletics track | [OSM relation 4434603](https://www.openstreetmap.org/relation/4434603) / [way 319275785](https://www.openstreetmap.org/way/319275785) |
| `campus2` | Campus II athletics track | Inner boundary [way 643311728](https://www.openstreetmap.org/way/643311728) of [OSM relation 8914003](https://www.openstreetmap.org/relation/8914003) |

The data was checked and embedded on 2026-09-12. OpenStreetMap data is available under the [ODbL](https://opendatacommons.org/licenses/odbl/); keep the source and licence attribution when publishing this repository. The [HIT campus map](https://map.hit.edu.cn/en/) can be used to check the current campus and venue layout.

## Randomization and reproducibility

One seed feeds independent random streams. This keeps earlier laps stable if distance correction temporarily needs an extra lap. The generated variation includes:

- a random start position on the track;
- a small lateral offset for the complete route;
- a small, continuous lane bias for each lap;
- a slightly different target pace for each lap;
- waveform phase, bend slowdown, and correlated GPS noise.

When `--seed` is omitted, the seed comes from the operating system. The program prints a command-style seed value such as `--seed 123456`. To reproduce the complete GPX, including timestamps, fix both the seed and start time:

```bash
python3 hit_run_simulator.py \
  --campus campus2 \
  --distance 2200 \
  --pace 5:00 \
  --seed 123456 \
  --start 2026-09-12T08:00:00Z \
  --output /tmp/hit-campus2-seed123456.gpx
```

The same seed with different `--distance`, `--pace`, `--sample-rate`, or `--gps-noise` values is expected to produce a different GPX because those settings are part of the route result.

## Main options

| Option | Description |
| --- | --- |
| `--campus campus1|campus2` | Select Campus I or Campus II; `1`, `2`, `一校区`, and `二校区` are also accepted. |
| `--distance METERS` | Total distance; default `2200`. |
| `--pace PACE` | Target pace such as `5:00`, `5.00`, or `5.0`; accepted range is 4:30–5:30/km. |
| `--output PATH` | GPX output path; defaults to a campus-specific path under `routes/`. |
| `--seed INTEGER` | Optional fixed random seed; omitted means a fresh seed on every run. |
| `--start ISO8601` | Optional start time; omitted means the current UTC time. |
| `--sample-rate HZ` | Sample frequency; default `1.0` Hz. |
| `--gps-noise METERS` | Correlated GPS noise standard deviation; default `0.8` m. Use `0` for stable coordinate checks. |
| `--play` | Play the generated GPX through `pymobiledevice3` in the current Python environment. |
| `--keep-location-simulation` | Keep simulated location after playback; the default clears it. |
| `--clear` | Only clear iPhone simulated location. |

## Playback on a configured development device

Before playback, prepare `pymobiledevice3` on macOS. The iPhone must be connected over USB, trust the Mac, and satisfy the Developer Mode/DVT prerequisites:

```bash
python3 hit_run_simulator.py \
  --campus campus2 \
  --pace 5:00 \
  --distance 2200 \
  --play
```

The script invokes `python -m pymobiledevice3` through the current interpreter, which avoids accidentally selecting an old command from another Python environment. Playback is cleared automatically after completion or `Ctrl-C` unless `--keep-location-simulation` is supplied:

```bash
python3 hit_run_simulator.py --clear
```

## Checks and tests

```bash
python3 -m py_compile hit_run_simulator.py
python3 -m unittest -v
```

The tests cover both campuses, target distance, seed reproducibility, different-seed variation, and campus aliases. After generation, the CLI reads the GPX back and reports point count, measured distance, duration, and average pace.

## Scope and safety

This project only generates or plays Core Location/GPS tracks. It does not fake accelerometer or gyroscope data, `CMPedometer`, HealthKit steps, or any third-party fitness app's local record. Use it only with devices, apps, and test environments you are authorized to test; no real-run record, step count, or anti-cheat result is guaranteed.

The map geometry is a static snapshot embedded in the script. Track layout, campus access rules, and third-party app behaviour can change, so check the venue and your authorization before actual use.

## Public-repository checklist

- Do not commit `.venv/`, `__pycache__/`, or generated `routes/*.gpx` files.
- Keep the OpenStreetMap source, ODbL attribution, and project scope statement.
- Before publishing, add a code licence that matches your intended distribution; the OSM data licence and the code licence are separate.
