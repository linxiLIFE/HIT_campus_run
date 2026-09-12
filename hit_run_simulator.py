#!/usr/bin/env python3
"""Generate and optionally play paced GPX routes around HIT campuses.

The supported route geometries are embedded, reproducible copies of public
OpenStreetMap track boundaries for HIT Campus I and Campus II.  The points are
only a GPS/Core Location simulation; this program does not inject accelerometer
data, steps, HealthKit data, or any third-party app's activity record.
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import math
import random
import secrets
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


# Public source: OpenStreetMap way 319275785, relation 4434603.
# Retrieved 2026-09-12.  The geometry is distributed under the ODbL.
TRACK_INNER_RING_LATLON: tuple[tuple[float, float], ...] = (
    (45.7367241, 126.6275568),
    (45.7363993, 126.6275416),
    (45.7362013, 126.6275189),
    (45.7361380, 126.6275643),
    (45.7360852, 126.6276173),
    (45.7360482, 126.6276816),
    (45.7360165, 126.6277345),
    (45.7359743, 126.6278329),
    (45.7359400, 126.6279501),
    (45.7359294, 126.6280636),
    (45.7359267, 126.6281960),
    (45.7359373, 126.6283057),
    (45.7359584, 126.6283889),
    (45.7359875, 126.6284722),
    (45.7360218, 126.6285743),
    (45.7360693, 126.6286613),
    (45.7361248, 126.6287256),
    (45.7362198, 126.6288012),
    (45.7363175, 126.6288353),
    (45.7363941, 126.6288353),
    (45.7371861, 126.6288353),
    (45.7372732, 126.6288088),
    (45.7373445, 126.6287672),
    (45.7373973, 126.6287294),
    (45.7374527, 126.6286651),
    (45.7375055, 126.6285818),
    (45.7375425, 126.6284986),
    (45.7375689, 126.6284116),
    (45.7375874, 126.6283246),
    (45.7376032, 126.6282301),
    (45.7376111, 126.6281393),
    (45.7376111, 126.6280447),
    (45.7376006, 126.6279464),
    (45.7375795, 126.6278480),
    (45.7375478, 126.6277610),
    (45.7375214, 126.6276891),
    (45.7374712, 126.6276211),
    (45.7374079, 126.6275643),
    (45.7373603, 126.6275303),
    (45.7370092, 126.6275568),
)

# Public source: OpenStreetMap relation 8914003, inner way 643311728.
# Retrieved 2026-09-12.  This is the inner boundary of the running track
# mapped inside HIT Campus II; the route is shifted into the track surface.
CAMPUS_II_INNER_RING_LATLON: tuple[tuple[float, float], ...] = (
    (45.7571458, 126.6783290),
    (45.7562692, 126.6785519),
    (45.7561803, 126.6786334),
    (45.7561186, 126.6787218),
    (45.7560717, 126.6788599),
    (45.7560618, 126.6789979),
    (45.7560816, 126.6791501),
    (45.7561433, 126.6793023),
    (45.7562272, 126.6793872),
    (45.7563161, 126.6794474),
    (45.7563877, 126.6794757),
    (45.7572619, 126.6792562),
    (45.7573557, 126.6791784),
    (45.7574224, 126.6790545),
    (45.7574668, 126.6788917),
    (45.7574767, 126.6787501),
    (45.7574545, 126.6786192),
    (45.7573903, 126.6784989),
    (45.7573310, 126.6784210),
    (45.7572594, 126.6783608),
    (45.7571458, 126.6783290),
)

TARGET_MIN_PACE_SECONDS = 4 * 60 + 30
TARGET_MAX_PACE_SECONDS = 5 * 60 + 30
METERS_PER_DEGREE_LAT = 111_320.0
GPX_NS = "http://www.topografix.com/GPX/1/1"


Point = tuple[float, float]


@dataclass(frozen=True)
class CampusRoute:
    """Static metadata and geometry for one supported HIT campus route."""

    key: str
    name_zh: str
    name_en: str
    track_points: tuple[tuple[float, float], ...]
    source_label: str
    source_urls: tuple[str, ...]
    baseline_offset: float
    lane_bias_limit: float
    lateral_shift_limit: float
    default_output: Path


CAMPUS_ROUTES: dict[str, CampusRoute] = {
    "campus1": CampusRoute(
        key="campus1",
        name_zh="哈工大一校区体育场",
        name_en="HIT Campus I athletics track",
        track_points=TRACK_INNER_RING_LATLON,
        source_label="OpenStreetMap relation 4434603 / way 319275785",
        source_urls=(
            "https://www.openstreetmap.org/relation/4434603",
            "https://www.openstreetmap.org/way/319275785",
        ),
        baseline_offset=-10.0,
        lane_bias_limit=1.4,
        lateral_shift_limit=1.8,
        default_output=Path("routes/hit_campus_2_2km.gpx"),
    ),
    "campus2": CampusRoute(
        key="campus2",
        name_zh="哈工大二校区田径场",
        name_en="HIT Campus II running track",
        track_points=CAMPUS_II_INNER_RING_LATLON,
        source_label="OpenStreetMap relation 8914003 / inner way 643311728",
        source_urls=(
            "https://www.openstreetmap.org/relation/8914003",
            "https://www.openstreetmap.org/way/643311728",
        ),
        # The Campus II inner way is ordered in the opposite direction from
        # Campus I, so the positive normal points from the field into the
        # running lanes here.
        baseline_offset=5.5,
        lane_bias_limit=1.0,
        lateral_shift_limit=1.2,
        default_output=Path("routes/hit_campus_ii_2_2km.gpx"),
    ),
}

CAMPUS_ALIASES = {
    "1": "campus1",
    "i": "campus1",
    "campusi": "campus1",
    "campus1": "campus1",
    "一校区": "campus1",
    "2": "campus2",
    "ii": "campus2",
    "campusii": "campus2",
    "campus2": "campus2",
    "二校区": "campus2",
}


@dataclass(frozen=True)
class LocalProjection:
    """Small local metre projection centred on one campus track."""

    lat0: float
    lon0: float
    meters_per_degree_lon: float

    @classmethod
    def from_points(cls, points: Sequence[tuple[float, float]]) -> "LocalProjection":
        if not points:
            raise ValueError("路线至少需要 1 个经纬度点")
        lat0 = sum(point[0] for point in points) / len(points)
        lon0 = sum(point[1] for point in points) / len(points)
        meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(lat0))
        return cls(lat0, lon0, meters_per_degree_lon)

    def to_xy(self, lat: float, lon: float) -> Point:
        return (
            (lon - self.lon0) * self.meters_per_degree_lon,
            (lat - self.lat0) * METERS_PER_DEGREE_LAT,
        )

    def to_latlon(self, point: Point) -> tuple[float, float]:
        x, y = point
        return (
            self.lat0 + y / METERS_PER_DEGREE_LAT,
            self.lon0 + x / self.meters_per_degree_lon,
        )


@dataclass(frozen=True)
class LapSpan:
    """A section of the generated route belonging to one lap."""

    index: int
    start_distance: float
    end_distance: float
    local_end_distance: float


@dataclass(frozen=True)
class GeneratedRoute:
    points: tuple[Point, ...]
    distances: tuple[float, ...]
    lap_spans: tuple[LapSpan, ...]
    loop_length: float
    start_offset: float


@dataclass(frozen=True)
class RouteVariation:
    """Randomized but seedable route characteristics for one generation."""

    lane_biases: tuple[float, ...] = (0.0,)
    lap_paces: tuple[float, ...] = ()
    lateral_shift: float = 0.0
    wave_phase: float = 0.7
    wave_amplitude: float = 0.45
    harmonic_phase: float = 1.4
    harmonic_amplitude: float = 0.18
    pace_phase: float = 0.5
    pace_amplitude: float = 0.022
    pace_harmonic_phase: float = 1.1
    pace_harmonic_amplitude: float = 0.008
    curve_slowdown: float = 0.025


def parse_pace(value: str) -> float:
    """Return seconds per kilometre.

    Accepted forms are ``5:00``, ``5.00`` (minutes.seconds), or ``5.0``
    (decimal minutes).  The two-digit dotted form is intentionally treated as
    minutes and seconds because it is common Chinese running-app notation.
    """

    value = value.strip()
    try:
        if ":" in value:
            minute_text, second_text = value.split(":", 1)
            minutes = int(minute_text)
            seconds = float(second_text)
            if not 0 <= seconds < 60:
                raise ValueError
            return minutes * 60 + seconds
        if "." in value and len(value.rsplit(".", 1)[1]) == 2:
            minute_text, second_text = value.split(".", 1)
            minutes = int(minute_text)
            seconds = int(second_text)
            if not 0 <= seconds < 60:
                raise ValueError
            return minutes * 60 + seconds
        return float(value) * 60
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            f"无法解析配速 {value!r}，请使用 5:00、5.00 或 5.0"
        ) from exc


def format_pace(seconds_per_km: float) -> str:
    total_seconds = max(0, int(round(seconds_per_km)))
    return f"{total_seconds // 60}:{total_seconds % 60:02d}/km"


def distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def scale(a: Point, factor: float) -> Point:
    return a[0] * factor, a[1] * factor


def unit(a: Point) -> Point:
    length = math.hypot(a[0], a[1])
    if length == 0:
        return 0.0, 0.0
    return a[0] / length, a[1] / length


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


class ClosedPolyline:
    """Distance-addressable closed polyline in a local metre projection."""

    def __init__(self, points: Sequence[Point], projection: LocalProjection) -> None:
        if len(points) < 3:
            raise ValueError("操场轮廓至少需要 3 个点")
        self.points = tuple(points)
        self.projection = projection
        self.segment_lengths = tuple(
            distance(self.points[index], self.points[(index + 1) % len(self.points)])
            for index in range(len(self.points))
        )
        self.cumulative = [0.0]
        for segment_length in self.segment_lengths:
            self.cumulative.append(self.cumulative[-1] + segment_length)
        self.length = self.cumulative[-1]

    def at(self, travelled: float) -> Point:
        travelled %= self.length
        index = bisect.bisect_right(self.cumulative, travelled) - 1
        index = min(index, len(self.points) - 1)
        start = self.cumulative[index]
        segment_length = self.segment_lengths[index]
        fraction = 0.0 if segment_length == 0 else (travelled - start) / segment_length
        a = self.points[index]
        b = self.points[(index + 1) % len(self.points)]
        return a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction

    def tangent(self, travelled: float, lookaround: float = 2.0) -> Point:
        before = self.at(travelled - lookaround)
        after = self.at(travelled + lookaround)
        return unit((after[0] - before[0], after[1] - before[1]))


def parse_campus(value: str) -> str:
    """Normalize a campus name or a short numeric alias."""

    normalized = (
        value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    )
    try:
        return CAMPUS_ALIASES[normalized]
    except KeyError as exc:
        choices = "、".join(("campus1", "campus2"))
        raise argparse.ArgumentTypeError(
            f"无法识别校区 {value!r}，请使用 {choices}"
        ) from exc


def track_loop(campus: CampusRoute) -> ClosedPolyline:
    projection = LocalProjection.from_points(campus.track_points)
    points = [projection.to_xy(*point) for point in campus.track_points]
    if distance(points[0], points[-1]) < 0.01:
        points.pop()
    return ClosedPolyline(points, projection)


def lane_offset(
    loop: ClosedPolyline,
    local_distance: float,
    lap_index: int,
    variation: RouteVariation,
    baseline_offset: float,
    start_offset: float = 0.0,
) -> Point:
    """Return a point with a small, continuous per-lap lane deviation."""

    previous_bias = (
        variation.lane_biases[lap_index - 1]
        if lap_index
        else variation.lane_biases[lap_index]
    )
    current_bias = variation.lane_biases[lap_index]
    transition_length = min(55.0, loop.length * 0.15)
    if local_distance < transition_length:
        transition = smoothstep(local_distance / transition_length)
        bias = previous_bias + (current_bias - previous_bias) * transition
    else:
        bias = current_bias

    # The wave is the same at the lap boundary, so changing lane does not
    # create a teleporting jump at the start/finish line.  The phase is based
    # on the ring position, while the lane transition is based on local lap
    # distance.
    ring_distance = start_offset + local_distance
    wave = variation.wave_amplitude * math.sin(
        2 * math.pi * ring_distance / loop.length + variation.wave_phase
    )
    wave += variation.harmonic_amplitude * math.sin(
        4 * math.pi * ring_distance / loop.length + variation.harmonic_phase
    )
    offset = baseline_offset + variation.lateral_shift + bias + wave
    tangent = loop.tangent(ring_distance)
    # The sign is configured per campus because the source way direction can
    # differ.  It always moves from the field-side boundary into the lanes.
    right_normal = (tangent[1], -tangent[0])
    return add(loop.at(ring_distance), scale(right_normal, offset))


def generated_loop_length(
    loop: ClosedPolyline,
    baseline_offset: float,
    variation: RouteVariation | None = None,
    sample_step: float = 1.0,
    start_offset: float = 0.0,
) -> float:
    """Estimate the length of one generated centre-line lap."""

    variation = variation or RouteVariation()
    positions = [
        min(index * sample_step, loop.length)
        for index in range(int(loop.length / sample_step) + 1)
    ]
    if not positions or positions[-1] < loop.length:
        positions.append(loop.length)
    points = [
        lane_offset(
            loop,
            position,
            0,
            variation,
            baseline_offset,
            start_offset,
        )
        for position in positions
    ]
    return sum(distance(a, b) for a, b in zip(points, points[1:]))


def interpolate_segment(a: Point, b: Point, fraction: float) -> Point:
    return a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction


def build_route(
    loop: ClosedPolyline,
    target_distance: float,
    variation: RouteVariation,
    baseline_offset: float,
    sample_step: float = 1.0,
    start_offset: float = 0.0,
) -> GeneratedRoute:
    if target_distance <= 0:
        raise ValueError("总距离必须大于 0")

    route_points: list[Point] = []
    route_distances: list[float] = []
    spans: list[LapSpan] = []
    total = 0.0

    for lap_index, _ in enumerate(variation.lane_biases):
        # Build a complete mapped lap and truncate the final segment by the
        # requested distance.  The inward offset changes physical metres per
        # metre of source-ring distance, so using the remaining distance as a
        # source-ring distance would undershoot the final target.
        lap_target = loop.length
        local_positions = [
            min(index * sample_step, lap_target)
            for index in range(int(lap_target / sample_step) + 1)
        ]
        if not local_positions or local_positions[-1] < lap_target:
            local_positions.append(lap_target)
        lap_points = [
            lane_offset(
                loop,
                local,
                lap_index,
                variation,
                baseline_offset,
                start_offset,
            )
            for local in local_positions
        ]
        lap_start = total

        if not route_points:
            route_points.append(lap_points[0])
            route_distances.append(0.0)
        local_end_distance = 0.0
        for position, (previous, current) in enumerate(zip(lap_points, lap_points[1:])):
            segment_length = distance(previous, current)
            if segment_length == 0:
                continue
            remaining = target_distance - total
            if segment_length <= remaining:
                total += segment_length
                route_points.append(current)
                route_distances.append(total)
                local_end_distance = local_positions[position + 1]
                continue
            fraction = remaining / segment_length
            route_points.append(interpolate_segment(previous, current, fraction))
            total = target_distance
            route_distances.append(total)
            local_end_distance = local_positions[position] + (
                local_positions[position + 1] - local_positions[position]
            ) * fraction
            break

        spans.append(
            LapSpan(
                index=lap_index,
                start_distance=lap_start,
                end_distance=total,
                local_end_distance=local_end_distance,
            )
        )
        if total >= target_distance - 1e-6:
            break

    if total < target_distance - 1e-3:
        raise RuntimeError("无法在操场环线上生成请求的总距离")
    return GeneratedRoute(
        points=tuple(route_points),
        distances=tuple(route_distances),
        lap_spans=tuple(spans),
        loop_length=loop.length,
        start_offset=start_offset,
    )


def route_point_at(route: GeneratedRoute, travelled: float) -> Point:
    travelled = max(0.0, min(route.distances[-1], travelled))
    index = bisect.bisect_right(route.distances, travelled) - 1
    index = max(0, min(index, len(route.points) - 2))
    start = route.distances[index]
    end = route.distances[index + 1]
    fraction = 0.0 if end == start else (travelled - start) / (end - start)
    return interpolate_segment(route.points[index], route.points[index + 1], fraction)


def span_at(route: GeneratedRoute, travelled: float) -> LapSpan:
    for span in route.lap_spans:
        if travelled <= span.end_distance + 1e-6:
            return span
    return route.lap_spans[-1]


def route_local_distance(route: GeneratedRoute, travelled: float, span: LapSpan) -> float:
    span_distance = max(0.001, span.end_distance - span.start_distance)
    fraction = (travelled - span.start_distance) / span_distance
    return max(0.0, min(span.local_end_distance, fraction * span.local_end_distance))


def pace_profile(
    route: GeneratedRoute,
    loop: ClosedPolyline,
    variation: RouteVariation,
) -> tuple[list[float], list[float]]:
    """Build cumulative time at each route sample and the instantaneous speed."""

    times = [0.0]
    speeds: list[float] = []
    for index in range(len(route.points) - 1):
        a = route.points[index]
        b = route.points[index + 1]
        segment = distance(a, b)
        midpoint = (route.distances[index] + route.distances[index + 1]) / 2
        span = span_at(route, midpoint)
        local = route_local_distance(route, midpoint, span)
        lap_fraction = local / max(0.001, loop.length)
        speed = 1000.0 / variation.lap_paces[span.index]
        speed *= 1.0 + variation.pace_amplitude * math.sin(
            2 * math.pi * lap_fraction + variation.pace_phase
        )
        speed *= 1.0 + variation.pace_harmonic_amplitude * math.sin(
            4 * math.pi * lap_fraction + variation.pace_harmonic_phase
        )

        # Ease off a little on the two bends, then return to cruising speed.
        ring_distance = route.start_offset + local
        before = loop.tangent(ring_distance - 7.0)
        after = loop.tangent(ring_distance + 7.0)
        angle = abs(
            math.atan2(
                before[0] * after[1] - before[1] * after[0],
                before[0] * after[0] + before[1] * after[1],
            )
        )
        curve_factor = min(1.0, angle / (math.pi / 2))
        speed *= 1.0 - variation.curve_slowdown * curve_factor

        speeds.append(speed)
        times.append(times[-1] + segment / speed)
    return times, speeds


def timed_points(
    route: GeneratedRoute,
    loop: ClosedPolyline,
    variation: RouteVariation,
    start_time: dt.datetime,
    sample_rate: float,
    gps_noise: float,
    rng: random.Random,
    duration_scale: float = 1.0,
) -> tuple[tuple[dt.datetime, float, float], ...]:
    raw_times, _ = pace_profile(route, loop, variation)
    times = [value * duration_scale for value in raw_times]
    duration = times[-1]
    interval = 1.0 / sample_rate
    output_seconds: list[float] = []
    current = 0.0
    while current < duration - 1e-7:
        output_seconds.append(current)
        current += interval
    if not output_seconds or output_seconds[-1] < duration - 1e-7:
        output_seconds.append(duration)

    noise_x = 0.0
    noise_y = 0.0
    correlation = 0.94
    innovation = math.sqrt(1.0 - correlation * correlation)
    result: list[tuple[dt.datetime, float, float]] = []
    for seconds in output_seconds:
        index = bisect.bisect_right(times, seconds) - 1
        index = max(0, min(index, len(times) - 2))
        start_t, end_t = times[index], times[index + 1]
        fraction = 0.0 if end_t == start_t else (seconds - start_t) / (end_t - start_t)
        travelled = route.distances[index] + (
            route.distances[index + 1] - route.distances[index]
        ) * fraction
        point = route_point_at(route, travelled)

        noise_x = correlation * noise_x + innovation * rng.gauss(0.0, gps_noise)
        noise_y = correlation * noise_y + innovation * rng.gauss(0.0, gps_noise)
        measured = (point[0] + noise_x, point[1] + noise_y)
        lat, lon = loop.projection.to_latlon(measured)
        result.append((start_time + dt.timedelta(seconds=seconds), lat, lon))
    return tuple(result)


def parse_start_time(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def write_gpx(
    output: Path,
    points: Iterable[tuple[dt.datetime, float, float]],
    campus: CampusRoute,
    seed: int,
) -> None:
    ET.register_namespace("", GPX_NS)
    root = ET.Element(
        f"{{{GPX_NS}}}gpx",
        {"version": "1.1", "creator": "hit_run_simulator.py", "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance", "xsi:schemaLocation": f"{GPX_NS} http://www.topografix.com/GPX/1/1/gpx.xsd"},
    )
    metadata = ET.SubElement(root, f"{{{GPX_NS}}}metadata")
    name = ET.SubElement(metadata, f"{{{GPX_NS}}}name")
    name.text = f"{campus.name_en} · generated GPX route"
    description = ET.SubElement(metadata, f"{{{GPX_NS}}}desc")
    description.text = (
        f"Generated by hit_run_simulator.py; seed={seed}; "
        f"source={campus.source_label}; links={', '.join(campus.source_urls)}; "
        "OSM data is ODbL."
    )
    track = ET.SubElement(root, f"{{{GPX_NS}}}trk")
    track_name = ET.SubElement(track, f"{{{GPX_NS}}}name")
    track_name.text = f"{campus.name_en} simulation"
    segment = ET.SubElement(track, f"{{{GPX_NS}}}trkseg")
    for timestamp, lat, lon in points:
        track_point = ET.SubElement(
            segment,
            f"{{{GPX_NS}}}trkpt",
            {"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"},
        )
        elevation = ET.SubElement(track_point, f"{{{GPX_NS}}}ele")
        elevation.text = "0"
        time_element = ET.SubElement(track_point, f"{{{GPX_NS}}}time")
        time_element.text = timestamp.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )

    ET.indent(root, space="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )


def haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6_371_000.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def gpx_distance(points: Sequence[tuple[float, float]]) -> float:
    return sum(haversine_meters(a, b) for a, b in zip(points, points[1:]))


def validate_gpx(path: Path) -> tuple[int, float, float]:
    tree = ET.parse(path)
    root = tree.getroot()
    track_points = []
    timestamps = []
    for element in root.iter():
        if element.tag.endswith("}trkpt"):
            track_points.append((float(element.attrib["lat"]), float(element.attrib["lon"])))
            time_element = next((child for child in element if child.tag.endswith("}time")), None)
            if time_element is not None and time_element.text:
                timestamps.append(dt.datetime.fromisoformat(time_element.text.replace("Z", "+00:00")))
    if len(track_points) < 2 or len(timestamps) < 2:
        raise ValueError(f"GPX 点数不足：{path}")
    distance_m = gpx_distance(track_points)
    duration_s = (timestamps[-1] - timestamps[0]).total_seconds()
    return len(track_points), distance_m, duration_s


def clear_location() -> int:
    command = [
        sys.executable,
        "-m",
        "pymobiledevice3",
        "developer",
        "dvt",
        "simulate-location",
        "clear",
        "--userspace",
    ]
    print("清除 iPhone 模拟定位：", " ".join(command))
    return subprocess.run(command, check=False).returncode


def play_location(path: Path, keep_simulation: bool) -> int:
    command = [
        sys.executable,
        "-m",
        "pymobiledevice3",
        "developer",
        "dvt",
        "simulate-location",
        "play",
        str(path.resolve()),
    ]
    print("播放 GPX：", " ".join(command))
    try:
        return subprocess.run(command, check=False).returncode
    except KeyboardInterrupt:
        print("\n已中断播放。")
        return 130
    finally:
        if not keep_simulation:
            clear_location()


def create_lap_paces(
    count: int,
    target: float,
    rng: random.Random,
) -> list[float]:
    # Keep even the boundary requests (4:30 and 5:30) valid.  At a boundary
    # there is naturally no room for variation on one side of the target.
    headroom = min(
        2.8,
        target - TARGET_MIN_PACE_SECONDS,
        TARGET_MAX_PACE_SECONDS - target,
    )
    values = [target + rng.uniform(-headroom, headroom) for _ in range(count)]
    weighted_mean = sum(values) / max(1, len(values))
    correction = target - weighted_mean
    values = [value + correction for value in values]
    values = [
        max(TARGET_MIN_PACE_SECONDS, min(TARGET_MAX_PACE_SECONDS, value))
        for value in values
    ]
    return values


def create_route_variation(
    count: int,
    target_pace: float,
    campus: CampusRoute,
    rng: random.Random,
) -> RouteVariation:
    """Create one route variation from a caller-provided random stream."""

    # Use independent streams for count-dependent arrays.  If distance
    # correction temporarily asks for one more lap, the already generated
    # laps and the global shape parameters must stay unchanged.
    stream_seed = rng.getrandbits(63)
    lane_rng = random.Random(stream_seed + 1)
    pace_rng = random.Random(stream_seed + 2)
    shape_rng = random.Random(stream_seed + 3)
    return RouteVariation(
        lane_biases=tuple(
            lane_rng.uniform(-campus.lane_bias_limit, campus.lane_bias_limit)
            for _ in range(count)
        ),
        lap_paces=tuple(create_lap_paces(count, target_pace, pace_rng)),
        lateral_shift=shape_rng.uniform(
            -campus.lateral_shift_limit, campus.lateral_shift_limit
        ),
        wave_phase=shape_rng.uniform(0.0, 2.0 * math.pi),
        wave_amplitude=shape_rng.uniform(0.30, 0.60),
        harmonic_phase=shape_rng.uniform(0.0, 2.0 * math.pi),
        harmonic_amplitude=shape_rng.uniform(0.10, 0.24),
        pace_phase=shape_rng.uniform(0.0, 2.0 * math.pi),
        pace_amplitude=shape_rng.uniform(0.014, 0.026),
        pace_harmonic_phase=shape_rng.uniform(0.0, 2.0 * math.pi),
        pace_harmonic_amplitude=shape_rng.uniform(0.004, 0.012),
        curve_slowdown=shape_rng.uniform(0.018, 0.032),
    )


def resolve_seed(value: int | None) -> int:
    """Return an explicit seed or fresh OS entropy for the default case."""

    return value if value is not None else secrets.randbits(63)


def generate_timed_route(
    campus: CampusRoute,
    loop: ClosedPolyline,
    target_distance: float,
    target_pace: float,
    start_time: dt.datetime,
    sample_rate: float,
    gps_noise: float,
    seed: int,
) -> tuple[GeneratedRoute, tuple[tuple[dt.datetime, float, float], ...], float]:
    """Generate a route whose *sampled GPX distance* stays near the target.

    A logger measures straight chords between timestamped fixes.  Chords cut a
    few metres from tight bends, so the clean geometric route needs to be a
    little longer than the distance displayed by a 1 Hz logger.  Repeating the
    deterministic build with a small correction keeps the final GPX near the
    requested distance while retaining the real mapped shape.  All random
    choices come from ``seed``, so an explicit seed can reproduce the route.
    """

    source_distance = target_distance
    start_time = start_time.astimezone(dt.timezone.utc)
    expected_duration = target_distance * target_pace / 1000.0
    start_offset = random.Random(seed + 5).uniform(0.0, loop.length)
    estimated_run_lap_length = generated_loop_length(
        loop,
        campus.baseline_offset,
        start_offset=start_offset,
    )
    best_route: GeneratedRoute | None = None
    best_timed: tuple[tuple[dt.datetime, float, float], ...] = ()
    best_generated_length = estimated_run_lap_length
    best_error = math.inf
    for _ in range(10):
        lap_count = math.ceil(source_distance / estimated_run_lap_length) + 1
        variation = create_route_variation(
            lap_count,
            target_pace,
            campus,
            random.Random(seed + 23),
        )
        route = build_route(
            loop,
            source_distance,
            variation,
            campus.baseline_offset,
            start_offset=start_offset,
        )
        generated_length = generated_loop_length(
            loop,
            campus.baseline_offset,
            variation,
            start_offset=start_offset,
        )
        raw_times, _ = pace_profile(route, loop, variation)
        duration_scale = expected_duration / max(0.001, raw_times[-1])
        timed = timed_points(
            route=route,
            loop=loop,
            variation=variation,
            start_time=start_time,
            sample_rate=sample_rate,
            gps_noise=gps_noise,
            rng=random.Random(seed + 37),
            duration_scale=duration_scale,
        )
        measured = gpx_distance([(lat, lon) for _, lat, lon in timed])
        error = abs(measured - target_distance)
        if error < best_error:
            best_route = route
            best_timed = timed
            best_generated_length = generated_length
            best_error = error
        if error <= 0.25:
            return route, timed, generated_length
        source_distance *= target_distance / max(0.001, measured)

    if best_route is None:
        raise RuntimeError("无法生成路线")
    return best_route, best_timed, best_generated_length


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成哈工大一校区或二校区田径场 GPX，并可用 pymobiledevice3 播放。"
    )
    parser.add_argument(
        "--campus",
        type=parse_campus,
        default="campus1",
        help="路线校区：campus1/一校区 或 campus2/二校区，默认 campus1",
    )
    parser.add_argument("--distance", type=float, default=2200.0, help="总距离，单位米，默认 2200")
    parser.add_argument("--pace", type=parse_pace, default=parse_pace("5:00"), help="目标配速，如 5:00、4.50、5.5")
    parser.add_argument("--output", "-o", type=Path, help="输出 GPX 路径；省略时按校区使用 routes/ 下的默认文件名")
    parser.add_argument("--start", help="起始时间，ISO 8601；省略则使用当前 UTC 时间")
    parser.add_argument("--seed", type=int, help="随机种子；省略时每次使用新的系统随机种子，并在输出中打印")
    parser.add_argument("--sample-rate", type=float, default=1.0, help="GPX 采样频率，默认 1 Hz")
    parser.add_argument("--gps-noise", type=float, default=0.8, help="相关 GPS 噪声标准差，单位米")
    parser.add_argument("--play", action="store_true", help="生成后调用 pymobiledevice3 播放")
    parser.add_argument("--keep-location-simulation", action="store_true", help="播放结束后不自动清除模拟定位")
    parser.add_argument("--clear", action="store_true", help="只清除 iPhone 模拟定位，不生成 GPX")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.clear:
        return clear_location()
    if not TARGET_MIN_PACE_SECONDS <= args.pace <= TARGET_MAX_PACE_SECONDS:
        parser.error("--pace 必须在 4:30–5:30/km 以内")
    if args.distance <= 0:
        parser.error("--distance 必须大于 0")
    if args.sample_rate <= 0:
        parser.error("--sample-rate 必须大于 0")
    if args.gps_noise < 0:
        parser.error("--gps-noise 不能为负数")

    campus = CAMPUS_ROUTES[args.campus]
    output = args.output or campus.default_output
    seed = resolve_seed(args.seed)
    loop = track_loop(campus)
    route, timed, estimated_run_lap_length = generate_timed_route(
        campus=campus,
        loop=loop,
        target_distance=args.distance,
        target_pace=args.pace,
        start_time=parse_start_time(args.start),
        sample_rate=args.sample_rate,
        gps_noise=args.gps_noise,
        seed=seed,
    )
    write_gpx(output, timed, campus, seed)

    count, measured_distance, duration = validate_gpx(output)
    actual_pace = duration / max(0.001, measured_distance) * 1000
    full_spans = [
        span
        for span in route.lap_spans
        # The sampled-distance correction may stop a fraction of a metre
        # before the source-ring endpoint; count that as a completed lap for
        # the human-readable summary.
        if span.local_end_distance >= loop.length - 2.0
    ]
    full_laps = len(full_spans)
    remainder = max(
        0.0,
        args.distance
        - sum(span.end_distance - span.start_distance for span in full_spans),
    )
    print(f"校区：{campus.name_zh}（{campus.name_en}）")
    print(f"数据来源：{campus.source_label}")
    print(f"随机种子：{seed}（使用 --seed {seed} 可复现路线变化）")
    print(f"起点在环线上的偏移：{route.start_offset:.1f} m")
    print(f"已生成：{output.resolve()}")
    print(f"公开内圈轮廓长度：{loop.length:.1f} m")
    print(f"生成跑线估算圈长：{estimated_run_lap_length:.1f} m")
    print(f"路线结构：{full_laps} 圈 + {remainder:.1f} m")
    print(f"GPX 点数：{count}，测得距离：{measured_distance:.1f} m")
    print(f"时长：{duration:.1f} s，平均配速：{format_pace(actual_pace)}")
    print("说明：GPX 只包含模拟 GPS 轨迹；不会增加 iPhone 系统步数或加速度计数据。")

    if args.play:
        return play_location(output, args.keep_location_simulation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
