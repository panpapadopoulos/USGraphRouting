#!/usr/bin/env python3
"""
Central/Eastern United States highway graph project.

Implements BFS, DFS, Prim, Kruskal, and Dijkstra with travel metrics:
map distance, elevation-adjusted real distance, weather risk, best start date,
gasoline consumption, and performance monitoring.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import html
import io
import heapq
import json
import math
import os
import random
import statistics
import struct
import subprocess
import sys
import time
import tracemalloc
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - psutil is optional for Linux lab runs
    psutil = None


DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
US_STATES_GEOJSON = DATA_DIR / "us_states.geojson"
START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 3, 30)
MAX_DRIVING_HOURS_PER_DAY = 8
MAX_SPEED_MPH = 75
MAX_DAILY_MILES = MAX_DRIVING_HOURS_PER_DAY * MAX_SPEED_MPH
BASE_MPG = 45.0
EARTH_RADIUS_MILES = 3958.8
AUTO_OPEN_IMAGES = True

CENTRAL_EASTERN_REGIONS = {
    "AL", "AR", "CT", "DE", "DC", "FL", "GA", "IA", "IL", "IN",
    "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS",
    "NC", "ND", "NE", "NH", "NJ", "NY", "OH", "OK", "PA", "RI",
    "SC", "SD", "TN", "TX", "VA", "VT", "WI", "WV",
}

STATE_NAME_TO_ABBR = {
    "Alabama": "AL", "Arkansas": "AR", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Iowa": "IA",
    "Illinois": "IL", "Indiana": "IN", "Kansas": "KS", "Kentucky": "KY",
    "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Nebraska": "NE", "New Hampshire": "NH", "New Jersey": "NJ", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Vermont": "VT",
    "Virginia": "VA", "West Virginia": "WV", "Wisconsin": "WI",
}

STATE_NEIGHBORS: dict[str, set[str]] = {
    "AL": {"FL", "GA", "TN", "MS"},
    "AR": {"MO", "TN", "MS", "LA", "TX", "OK"},
    "CT": {"NY", "MA", "RI"},
    "DC": {"MD", "VA"},
    "DE": {"MD", "PA", "NJ"},
    "FL": {"GA", "AL"},
    "GA": {"FL", "AL", "TN", "NC", "SC"},
    "IA": {"MN", "WI", "IL", "MO", "NE", "SD"},
    "IL": {"WI", "IA", "MO", "KY", "IN"},
    "IN": {"IL", "MI", "OH", "KY"},
    "KS": {"NE", "MO", "OK", "CO"},
    "KY": {"IL", "IN", "OH", "WV", "VA", "TN", "MO"},
    "LA": {"TX", "AR", "MS"},
    "ME": {"NH"},
    "MA": {"RI", "CT", "NY", "VT", "NH"},
    "MD": {"DC", "VA", "WV", "PA", "DE"},
    "MI": {"WI", "IN", "OH"},
    "MN": {"WI", "IA", "ND", "SD"},
    "MO": {"IA", "IL", "KY", "TN", "AR", "OK", "KS", "NE"},
    "MS": {"LA", "AR", "TN", "AL"},
    "NC": {"VA", "TN", "GA", "SC"},
    "ND": {"MN", "SD", "MT"},
    "NE": {"SD", "IA", "MO", "KS", "CO", "WY"},
    "NH": {"ME", "MA", "VT"},
    "NJ": {"NY", "PA", "DE"},
    "NY": {"PA", "NJ", "CT", "MA", "VT"},
    "OH": {"MI", "IN", "KY", "WV", "PA"},
    "OK": {"KS", "MO", "AR", "TX", "NM", "CO"},
    "PA": {"NY", "NJ", "DE", "MD", "WV", "OH"},
    "RI": {"CT", "MA"},
    "SC": {"NC", "GA"},
    "SD": {"ND", "MN", "IA", "NE", "WY", "MT"},
    "TN": {"KY", "VA", "NC", "GA", "AL", "MS", "AR", "MO"},
    "TX": {"LA", "AR", "OK", "NM"},
    "VA": {"NC", "TN", "KY", "WV", "MD", "DC"},
    "VT": {"NY", "MA", "NH"},
    "WV": {"OH", "PA", "MD", "VA", "KY"},
    "WI": {"MN", "IA", "IL", "MI"},
}


@dataclass(frozen=True)
class City:
    name: str
    state: str
    timezone: str
    latitude: float
    longitude: float
    elevation_ft: float


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    map_distance: float


@dataclass
class PerfResult:
    name: str
    elapsed_ms: float
    cpu_percent: float
    memory_peak_kb: float
    disk_read_kb: float
    disk_write_kb: float
    result: object


class TeeOutput:
    def __init__(self, *streams: object) -> None:
        self.streams = streams

    def write(self, text: str) -> None:
        for stream in self.streams:
            stream.write(text)  # type: ignore[attr-defined]

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()  # type: ignore[attr-defined]


class PerformanceMonitor:
    def __init__(self) -> None:
        self.process = psutil.Process(os.getpid()) if psutil else None

    def run(self, name: str, func: Callable[[], object]) -> PerfResult:
        if self.process:
            self.process.cpu_percent(None)
            before_io = self.process.io_counters()
        else:
            before_io = None

        tracemalloc.start()
        start = time.perf_counter()
        result = func()
        elapsed_ms = (time.perf_counter() - start) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        if self.process:
            cpu_percent = self.process.cpu_percent(None)
            after_io = self.process.io_counters()
            disk_read_kb = (after_io.read_bytes - before_io.read_bytes) / 1024
            disk_write_kb = (after_io.write_bytes - before_io.write_bytes) / 1024
        else:
            cpu_percent = 0.0
            disk_read_kb = 0.0
            disk_write_kb = 0.0

        return PerfResult(
            name=name,
            elapsed_ms=elapsed_ms,
            cpu_percent=cpu_percent,
            memory_peak_kb=peak / 1024,
            disk_read_kb=disk_read_kb,
            disk_write_kb=disk_write_kb,
            result=result,
        )


def load_cities(path: Path = DATA_DIR / "cities.csv") -> dict[str, City]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        cities = {
            row["city"]: City(
                name=row["city"],
                state=row["state"],
                timezone=row["timezone"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                elevation_ft=float(row["elevation_ft"]),
            )
            for row in rows
        }
    validate_region_coverage(cities)
    return cities


def validate_region_coverage(cities: dict[str, City]) -> None:
    states = {city.state for city in cities.values()}
    missing = CENTRAL_EASTERN_REGIONS - states
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"cities.csv is missing Central/Eastern state coverage for: {missing_text}")


def haversine_miles(a: City, b: City) -> float:
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    inside = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(inside))


def estimate_highway_distance(a: City, b: City) -> float:
    # Highway mileage is usually longer than straight-line distance.
    return round(haversine_miles(a, b) * 1.18, 1)


def are_neighboring_states(a: str, b: str) -> bool:
    return b in STATE_NEIGHBORS.get(a, set())


def build_graph(cities: dict[str, City]) -> dict[str, list[Edge]]:
    graph: dict[str, dict[str, Edge]] = {name: {} for name in cities}
    city_items = list(cities.items())
    for index, (city_name, city) in enumerate(city_items):
        for other_name, other in city_items[index + 1 :]:
            if not are_neighboring_states(city.state, other.state):
                continue
            distance = estimate_highway_distance(city, other)
            graph[city_name][other_name] = Edge(city_name, other_name, distance)
            graph[other_name][city_name] = Edge(other_name, city_name, distance)

    return {city: sorted(edges.values(), key=lambda e: (e.map_distance, e.target)) for city, edges in graph.items()}


def bfs_with_tree(graph: dict[str, list[Edge]], start: str) -> tuple[list[str], list[Edge]]:
    visited: set[str] = set()
    order: list[str] = []
    tree_edges: list[Edge] = []
    queue: deque[str] = deque([start])
    parent_edge: dict[str, Edge] = {}
    while queue:
        city = queue.popleft()
        if city in visited:
            continue
        visited.add(city)
        order.append(city)
        if city in parent_edge:
            tree_edges.append(parent_edge[city])
        for edge in graph[city]:
            if edge.target not in visited and edge.target not in parent_edge:
                parent_edge[edge.target] = edge
                queue.append(edge.target)
    return order, tree_edges


def bfs(graph: dict[str, list[Edge]], start: str) -> list[str]:
    order, _ = bfs_with_tree(graph, start)
    return order


def dfs_with_tree(graph: dict[str, list[Edge]], start: str) -> tuple[list[str], list[Edge]]:
    visited: set[str] = set()
    order: list[str] = []
    tree_edges: list[Edge] = []
    stack: list[tuple[str, Edge | None]] = [(start, None)]
    while stack:
        city, incoming_edge = stack.pop()
        if city in visited:
            continue
        visited.add(city)
        order.append(city)
        if incoming_edge:
            tree_edges.append(incoming_edge)
        for edge in reversed(graph[city]):
            if edge.target not in visited:
                stack.append((edge.target, edge))
    return order, tree_edges


def dfs(graph: dict[str, list[Edge]], start: str) -> list[str]:
    order, _ = dfs_with_tree(graph, start)
    return order


def dijkstra(graph: dict[str, list[Edge]], start: str, goal: str) -> tuple[float, list[str]]:
    distances = defaultdict(lambda: math.inf)
    previous: dict[str, str | None] = {start: None}
    distances[start] = 0.0
    heap: list[tuple[float, str]] = [(0.0, start)]

    while heap:
        current_distance, city = heapq.heappop(heap)
        if city == goal:
            break
        if current_distance > distances[city]:
            continue
        for edge in graph[city]:
            candidate = current_distance + edge.map_distance
            if candidate < distances[edge.target]:
                distances[edge.target] = candidate
                previous[edge.target] = city
                heapq.heappush(heap, (candidate, edge.target))

    if math.isinf(distances[goal]):
        return math.inf, []

    path = [goal]
    while path[-1] != start:
        path.append(previous[path[-1]])  # type: ignore[arg-type]
    path.reverse()
    return distances[goal], path


def bellman_ford(graph: dict[str, list[Edge]], start: str, goal: str) -> tuple[float, list[str]]:
    distances = {city: math.inf for city in graph}
    previous: dict[str, str | None] = {city: None for city in graph}
    distances[start] = 0.0
    directed_edges = [edge for edges in graph.values() for edge in edges]

    for _ in range(len(graph) - 1):
        changed = False
        for edge in directed_edges:
            if math.isinf(distances[edge.source]):
                continue
            candidate = distances[edge.source] + edge.map_distance
            if candidate < distances[edge.target]:
                distances[edge.target] = candidate
                previous[edge.target] = edge.source
                changed = True
        if not changed:
            break

    for edge in directed_edges:
        if distances[edge.source] + edge.map_distance < distances[edge.target]:
            raise ValueError("Negative-weight cycle detected")

    if math.isinf(distances[goal]):
        return math.inf, []

    path = [goal]
    while path[-1] != start:
        parent = previous[path[-1]]
        if parent is None:
            return math.inf, []
        path.append(parent)
    path.reverse()
    return distances[goal], path


def prim(graph: dict[str, list[Edge]], start: str) -> list[Edge]:
    visited = {start}
    tree: list[Edge] = []
    heap = [(edge.map_distance, edge.source, edge.target, edge) for edge in graph[start]]
    heapq.heapify(heap)

    while heap and len(visited) < len(graph):
        _, _, target, edge = heapq.heappop(heap)
        if target in visited:
            continue
        visited.add(target)
        tree.append(edge)
        for next_edge in graph[target]:
            if next_edge.target not in visited:
                heapq.heappush(heap, (next_edge.map_distance, next_edge.source, next_edge.target, next_edge))
    return tree


class DisjointSet:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: str) -> str:
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, a: str, b: str) -> bool:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return False
        if self.rank[root_a] < self.rank[root_b]:
            root_a, root_b = root_b, root_a
        self.parent[root_b] = root_a
        if self.rank[root_a] == self.rank[root_b]:
            self.rank[root_a] += 1
        return True


def kruskal(graph: dict[str, list[Edge]]) -> list[Edge]:
    seen: set[tuple[str, str]] = set()
    edges: list[Edge] = []
    for source, neighbors in graph.items():
        for edge in neighbors:
            key = tuple(sorted((source, edge.target)))
            if key not in seen:
                seen.add(key)
                edges.append(edge)

    ds = DisjointSet(graph.keys())
    tree: list[Edge] = []
    for edge in sorted(edges, key=lambda e: e.map_distance):
        if ds.union(edge.source, edge.target):
            tree.append(edge)
    return tree


def connected_city_sample(
    cities: dict[str, City],
    start: str,
    end: str,
    requested_count: int,
) -> dict[str, City]:
    full_graph = build_graph(cities)
    _, required_path = dijkstra(full_graph, start, end)
    if not required_path:
        raise SystemExit(f"No neighboring-state route exists from {start} to {end}.")

    target_count = max(len(required_path), min(requested_count, len(cities)))
    selected = set(required_path)
    frontier = {
        edge.target
        for city_name in selected
        for edge in full_graph[city_name]
        if edge.target not in selected
    }

    while len(selected) < target_count and frontier:
        next_city = random.choice(sorted(frontier))
        frontier.remove(next_city)
        selected.add(next_city)
        frontier.update(
            edge.target
            for edge in full_graph[next_city]
            if edge.target not in selected
        )

    return {name: cities[name] for name in cities if name in selected}


def risk_from_condition(condition: str) -> int:
    return {"sun": 1, "cloud": 1, "rain": 5, "snow": 10, "ice": 10}[condition]


def weather_condition(city: City, current_date: date) -> str:
    """Deterministic example weather for Jan. 1-Mar. 30, 2026.

    Replace this with Weather Underground history exports for real reporting.
    """
    northern = city.latitude >= 39.5
    gulf_or_florida = city.state in {"FL", "LA", "TX", "MS"}
    day = current_date.timetuple().tm_yday
    seed = sum(ord(char) for char in city.name) + day * 17

    if northern and current_date.month in {1, 2} and seed % 11 in {0, 1}:
        return "snow"
    if northern and current_date.month == 1 and seed % 23 == 0:
        return "ice"
    if gulf_or_florida and seed % 7 in {0, 2}:
        return "rain"
    if seed % 9 in {0, 3}:
        return "rain"
    if seed % 5 in {0, 1}:
        return "cloud"
    return "sun"


def weather_risk(city: City, current_date: date) -> int:
    return risk_from_condition(weather_condition(city, current_date))


def edge_by_city(graph: dict[str, list[Edge]], source: str, target: str) -> Edge:
    for edge in graph[source]:
        if edge.target == target:
            return edge
    raise ValueError(f"No edge between {source} and {target}")


def adjusted_real_distance(cities: dict[str, City], edge: Edge) -> tuple[float, float]:
    source = cities[edge.source]
    target = cities[edge.target]
    elevation_delta_miles = (target.elevation_ft - source.elevation_ft) / 5280
    tan_theta = elevation_delta_miles / edge.map_distance
    real_distance = edge.map_distance * (1 + tan_theta)
    return max(real_distance, edge.map_distance * 0.85), tan_theta


def evaluate_route(
    cities: dict[str, City],
    graph: dict[str, list[Edge]],
    path: list[str],
) -> dict[str, object]:
    if len(path) < 2:
        return {
            "path": path,
            "map_distance": 0.0,
            "real_distance": 0.0,
            "best_start_date": START_DATE.isoformat(),
            "accumulated_risk": weather_risk(cities[path[0]], START_DATE) if path else 0,
            "average_risk": weather_risk(cities[path[0]], START_DATE) if path else 0,
            "gasoline_gallons": 0.0,
            "travel_days": 1,
        }

    edge_metrics = []
    for source, target in zip(path, path[1:]):
        edge = edge_by_city(graph, source, target)
        real_distance, tan_theta = adjusted_real_distance(cities, edge)
        edge_metrics.append((edge, real_distance, tan_theta))

    total_real_distance = sum(metric[1] for metric in edge_metrics)
    travel_days = max(1, math.ceil(total_real_distance / MAX_DAILY_MILES))
    latest_start = END_DATE - timedelta(days=travel_days - 1)

    best_date = START_DATE
    best_risk = math.inf
    current = START_DATE
    while current <= latest_start:
        day_offset_miles = 0.0
        risk_total = 0.0
        for edge, real_distance, _ in edge_metrics:
            leg_date = current + timedelta(days=int(day_offset_miles // MAX_DAILY_MILES))
            source_risk = weather_risk(cities[edge.source], leg_date)
            target_risk = weather_risk(cities[edge.target], leg_date)
            risk_total += (source_risk + target_risk) / 2
            day_offset_miles += real_distance
        if risk_total < best_risk:
            best_date = current
            best_risk = risk_total
        current += timedelta(days=1)

    return {
        "path": path,
        "map_distance": round(sum(metric[0].map_distance for metric in edge_metrics), 2),
        "real_distance": round(total_real_distance, 2),
        "best_start_date": best_date.isoformat(),
        "accumulated_risk": round(best_risk, 2),
        "average_risk": round(best_risk / len(edge_metrics), 2) if edge_metrics else 0.0,
        "gasoline_gallons": round(total_real_distance / BASE_MPG, 2),
        "travel_days": travel_days,
        "legs": [
            {
                "from": edge.source,
                "to": edge.target,
                "map_distance": edge.map_distance,
                "real_distance": round(real_distance, 2),
                "tan_theta": round(tan_theta, 6),
            }
            for edge, real_distance, tan_theta in edge_metrics
        ],
    }


def export_weather_sample(cities: dict[str, City], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "city", "state", "condition", "risk"])
        current = START_DATE
        while current <= END_DATE:
            for city in cities.values():
                condition = weather_condition(city, current)
                writer.writerow([current.isoformat(), city.name, city.state, condition, risk_from_condition(condition)])
            current += timedelta(days=1)


def create_route_map(cities: dict[str, City], path: list[str], filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    min_lon, max_lon = -100.5, -69.0
    min_lat, max_lat = 25.0, 46.5

    def project(city_name: str) -> tuple[float, float]:
        city = cities[city_name]
        x = 40 + ((city.longitude - min_lon) / (max_lon - min_lon)) * 920
        y = 620 - ((city.latitude - min_lat) / (max_lat - min_lat)) * 560
        return x, y

    route_points = [project(city_name) for city_name in path]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in route_points)
    city_marks = []
    for city_name in path:
        x, y = project(city_name)
        city_marks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#0f766e" />'
            f'<text x="{x + 8:.1f}" y="{y - 8:.1f}" font-size="12">{city_name}</text>'
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Travel Route Map</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #172026; }}
    svg {{ max-width: 100%; border: 1px solid #c9d1d9; background: #f8fafc; }}
  </style>
</head>
<body>
  <h1>Travel Route Map</h1>
  <svg viewBox="0 0 1000 660" role="img" aria-label="Route map">
    <rect x="40" y="60" width="920" height="560" fill="#eef6f3" stroke="#b8c7c0" />
    <polyline points="{polyline}" fill="none" stroke="#b91c1c" stroke-width="4" />
    {''.join(city_marks)}
  </svg>
</body>
</html>
"""
    filepath.write_text(html, encoding="utf-8")


def unique_edges(graph: dict[str, list[Edge]]) -> list[Edge]:
    seen: set[frozenset[str]] = set()
    edges: list[Edge] = []
    for source, neighbors in graph.items():
        for edge in neighbors:
            key = frozenset((source, edge.target))
            if key not in seen:
                seen.add(key)
                edges.append(edge)
    return edges


def load_state_polygons() -> list[tuple[str, list[list[tuple[float, float]]]]]:
    if not US_STATES_GEOJSON.exists():
        return []
    with US_STATES_GEOJSON.open(encoding="utf-8") as handle:
        data = json.load(handle)

    state_polygons: list[tuple[str, list[list[tuple[float, float]]]]] = []
    for feature in data.get("features", []):
        name = feature.get("properties", {}).get("name", "")
        abbr = STATE_NAME_TO_ABBR.get(name)
        if abbr not in CENTRAL_EASTERN_REGIONS:
            continue
        geometry = feature.get("geometry", {})
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        rings: list[list[tuple[float, float]]] = []
        if geometry_type == "Polygon":
            rings.extend([(float(lon), float(lat)) for lon, lat in ring] for ring in coordinates[:1])
        elif geometry_type == "MultiPolygon":
            for polygon in coordinates:
                rings.extend([(float(lon), float(lat)) for lon, lat in ring] for ring in polygon[:1])
        state_polygons.append((abbr, rings))
    return state_polygons


def graph_bounds(cities: dict[str, City]) -> tuple[float, float, float, float]:
    state_polygons = load_state_polygons()
    lons = [city.longitude for city in cities.values()]
    lats = [city.latitude for city in cities.values()]
    states_in_graph = {city.state for city in cities.values()}
    for state, rings in state_polygons:
        if state not in states_in_graph:
            continue
        for ring in rings:
            for lon, lat in ring:
                lons.append(lon)
                lats.append(lat)
    lon_pad = max((max(lons) - min(lons)) * 0.04, 0.5)
    lat_pad = max((max(lats) - min(lats)) * 0.05, 0.5)
    return min(lons) - lon_pad, max(lons) + lon_pad, min(lats) - lat_pad, max(lats) + lat_pad


def rect_overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def place_label(
    anchor: tuple[float, float],
    text: str,
    occupied: list[tuple[float, float, float, float]],
    width: float,
    height: float,
    font_size: float,
) -> tuple[float, float, tuple[float, float, float, float]]:
    text_width = max(36.0, len(text) * font_size * 0.56)
    text_height = font_size + 6
    offsets = [
        (12, -10), (12, 18), (-text_width - 12, -10), (-text_width - 12, 18),
        (18, -30), (18, 36), (-text_width - 18, -30), (-text_width - 18, 36),
        (0, -46), (0, 50), (28, 0), (-text_width - 28, 0),
    ]
    ax, ay = anchor
    best = None
    best_penalty = float("inf")
    for dx, dy in offsets:
        x = min(max(ax + dx, 4), width - text_width - 4)
        y = min(max(ay + dy, text_height + 4), height - 8)
        rect = (x - 3, y - text_height + 2, x + text_width + 3, y + 4)
        overlap_count = sum(1 for item in occupied if rect_overlaps(rect, item))
        distance_penalty = abs(dx) + abs(dy)
        penalty = overlap_count * 10000 + distance_penalty
        if penalty < best_penalty:
            best = (x, y, rect)
            best_penalty = penalty
            if overlap_count == 0:
                break
    assert best is not None
    occupied.append(best[2])
    return best


def save_graph_png(
    cities: dict[str, City],
    graph: dict[str, list[Edge]],
    selected_edges: list[Edge],
    filepath: Path,
    title: str,
    selected_label: str,
) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        save_simple_png_graph(cities, graph, selected_edges, filepath)
        return True

    filepath.parent.mkdir(parents=True, exist_ok=True)
    selected_keys = {
        frozenset((edge.source, edge.target))
        for edge in selected_edges
    }
    label_edges = selected_edges if selected_edges else unique_edges(graph)
    min_lon, max_lon, min_lat, max_lat = graph_bounds(cities)

    fig, ax = plt.subplots(figsize=(18, 11), dpi=170)
    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, color="#e5e7eb", linewidth=0.7)
    ax.set_facecolor("#f8fafc")
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)

    states_in_graph = {city.state for city in cities.values()}
    for state, rings in load_state_polygons():
        if state not in states_in_graph:
            continue
        for ring in rings:
            xs = [point[0] for point in ring]
            ys = [point[1] for point in ring]
            ax.fill(xs, ys, facecolor="#eef6ef", edgecolor="#64748b", linewidth=0.8, alpha=0.55, zorder=0)

    for edge in unique_edges(graph):
        source = cities[edge.source]
        target = cities[edge.target]
        key = frozenset((edge.source, edge.target))
        if key in selected_keys:
            continue
        ax.plot(
            [source.longitude, target.longitude],
            [source.latitude, target.latitude],
            color="#94a3b8",
            linewidth=0.8,
            alpha=0.45,
            zorder=1,
        )

    for index, edge in enumerate(label_edges):
        source = cities[edge.source]
        target = cities[edge.target]
        midpoint_lon = (source.longitude + target.longitude) / 2
        midpoint_lat = (source.latitude + target.latitude) / 2
        key = frozenset((edge.source, edge.target))
        in_selection = key in selected_keys or not selected_edges
        lon_offset = 0.08 * ((index % 3) - 1)
        lat_offset = 0.06 * (((index // 3) % 3) - 1)
        ax.text(
            midpoint_lon + lon_offset,
            midpoint_lat + lat_offset,
            f"{edge.map_distance:.0f} mi",
            fontsize=6.3 if selected_edges else 5.5,
            color="#7f1d1d" if in_selection else "#475569",
            ha="center",
            va="center",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 0.8},
            zorder=6,
        )

    for edge in selected_edges:
        source = cities[edge.source]
        target = cities[edge.target]
        ax.plot(
            [source.longitude, target.longitude],
            [source.latitude, target.latitude],
            color="#b91c1c",
            linewidth=2.4,
            alpha=0.95,
            zorder=3,
        )

    selected_cities = {
        city_name
        for edge in selected_edges
        for city_name in (edge.source, edge.target)
    }
    city_label_offsets = [
        (0.15, 0.16), (0.15, -0.20), (-0.90, 0.16), (-0.90, -0.20),
        (0.35, 0.38), (-1.15, 0.38), (0.35, -0.42), (-1.15, -0.42),
    ]
    for index, city in enumerate(cities.values()):
        in_selection = city.name in selected_cities
        ax.scatter(
            city.longitude,
            city.latitude,
            s=70 if in_selection else 42,
            color="#0f766e" if in_selection else "#2563eb",
            edgecolor="white",
            linewidth=0.8,
            zorder=4,
        )
        dx, dy = city_label_offsets[index % len(city_label_offsets)]
        ax.annotate(
            f"{city.name}, {city.state}",
            xy=(city.longitude, city.latitude),
            xytext=(city.longitude + dx, city.latitude + dy),
            arrowprops={"arrowstyle": "-", "color": "#64748b", "linewidth": 0.4, "alpha": 0.55},
            fontsize=7.1,
            color="#111827",
            zorder=5,
        )

    if selected_edges:
        ax.plot([], [], color="#b91c1c", linewidth=2.4, label=selected_label)
    ax.plot([], [], color="#94a3b8", linewidth=0.8, alpha=0.7, label="allowed neighboring-state edge")
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(filepath, bbox_inches="tight")
    plt.close(fig)
    return True


def save_graph_svg(
    cities: dict[str, City],
    graph: dict[str, list[Edge]],
    selected_edges: list[Edge],
    filepath: Path,
    title: str,
) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    width = 2200
    height = 1450
    margin = 105
    min_lon, max_lon, min_lat, max_lat = graph_bounds(cities)
    x_span = max(max_lon - min_lon, 0.01)
    y_span = max(max_lat - min_lat, 0.01)

    def project_lonlat(lon: float, lat: float) -> tuple[float, float]:
        x = margin + ((lon - min_lon) / x_span) * (width - 2 * margin)
        y = margin + (1 - ((lat - min_lat) / y_span)) * (height - 2 * margin)
        return x, y

    def project(city_name: str) -> tuple[float, float]:
        city = cities[city_name]
        return project_lonlat(city.longitude, city.latitude)

    selected_keys = {
        frozenset((edge.source, edge.target))
        for edge in selected_edges
    }
    selected_cities = {
        city_name
        for edge in selected_edges
        for city_name in (edge.source, edge.target)
    }
    label_edges = selected_edges if selected_edges else unique_edges(graph)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="{margin}" y="36" font-family="Arial" font-size="24" font-weight="700" fill="#111827">{html.escape(title)}</text>',
    ]

    for i in range(6):
        x = margin + i * (width - 2 * margin) / 5
        y = margin + i * (height - 2 * margin) / 5
        parts.append(f'<line x1="{x:.1f}" y1="{margin}" x2="{x:.1f}" y2="{height - margin}" stroke="#e5e7eb" stroke-width="1"/>')
        parts.append(f'<line x1="{margin}" y1="{y:.1f}" x2="{width - margin}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')

    states_in_graph = {city.state for city in cities.values()}
    parts.append('<g id="state-outlines" fill="#eef6ef" stroke="#64748b" stroke-width="1.5" opacity="0.72">')
    for state, rings in load_state_polygons():
        if state not in states_in_graph:
            continue
        for ring in rings:
            if not ring:
                continue
            commands = []
            for index, (lon, lat) in enumerate(ring):
                x, y = project_lonlat(lon, lat)
                command = "M" if index == 0 else "L"
                commands.append(f"{command}{x:.1f},{y:.1f}")
            commands.append("Z")
            parts.append(f'<path d="{" ".join(commands)}"/>')
    parts.append("</g>")

    for edge in unique_edges(graph):
        key = frozenset((edge.source, edge.target))
        if key in selected_keys:
            continue
        x1, y1 = project(edge.source)
        x2, y2 = project(edge.target)
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#94a3b8" stroke-width="1.2" opacity="0.55"/>')

    for edge in selected_edges:
        x1, y1 = project(edge.source)
        x2, y2 = project(edge.target)
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#b91c1c" stroke-width="4.2" opacity="0.95"/>')

    occupied: list[tuple[float, float, float, float]] = []
    for city_name in cities:
        x, y = project(city_name)
        occupied.append((x - 12, y - 12, x + 12, y + 12))

    for edge in label_edges:
        x1, y1 = project(edge.source)
        x2, y2 = project(edge.target)
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        text = f"{edge.map_distance:.0f} mi"
        lx, ly, rect = place_label((mx, my), text, occupied, width, height, 12)
        label_width = rect[2] - rect[0]
        parts.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{lx + label_width / 2:.1f}" y2="{ly - 6:.1f}" stroke="#94a3b8" stroke-width="0.8" opacity="0.55"/>')
        parts.append(f'<rect x="{rect[0]:.1f}" y="{rect[1]:.1f}" width="{label_width:.1f}" height="{rect[3] - rect[1]:.1f}" rx="3" fill="white" opacity="0.86"/>')
        parts.append(f'<text x="{lx + label_width / 2:.1f}" y="{ly:.1f}" text-anchor="middle" font-family="Arial" font-size="12" fill="#7f1d1d">{text}</text>')

    for city_name, city in cities.items():
        x, y = project(city_name)
        selected = city_name in selected_cities
        fill = "#0f766e" if selected else "#2563eb"
        radius = 8 if selected else 6
        label = html.escape(f"{city.name}, {city.state}")
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{fill}" stroke="white" stroke-width="2"/>')
        lx, ly, rect = place_label((x, y), label, occupied, width, height, 13)
        parts.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{lx:.1f}" y2="{ly - 5:.1f}" stroke="#64748b" stroke-width="0.8" opacity="0.6"/>')
        parts.append(f'<rect x="{rect[0]:.1f}" y="{rect[1]:.1f}" width="{rect[2] - rect[0]:.1f}" height="{rect[3] - rect[1]:.1f}" rx="3" fill="white" opacity="0.88"/>')
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-family="Arial" font-size="13" fill="#111827">{label}</text>')

    parts.append(f'<text x="{margin}" y="{height - 30}" font-family="Arial" font-size="15" fill="#475569">Basemap: real US state outlines from GeoJSON. Cities are placed by longitude and latitude; gray edges are allowed neighboring-state connections; red edges are the selected algorithm result.</text>')
    parts.append("</svg>")
    filepath.write_text("\n".join(parts), encoding="utf-8")


def generate_graph_images(
    cities: dict[str, City],
    graph: dict[str, list[Edge]],
    results: list[PerfResult],
    shortest_path: list[str],
    start: str,
    end: str,
) -> list[Path]:
    bfs_edges = results[0].result[1]  # type: ignore[index]
    dfs_edges = results[1].result[1]  # type: ignore[index]
    prim_edges = results[2].result  # type: ignore[assignment]
    kruskal_edges = results[3].result  # type: ignore[assignment]
    dijkstra_edges = path_edges(graph, shortest_path)
    bellman_edges: list[Edge] = []
    if len(results) > 5:
        _, bellman_path = results[5].result  # type: ignore[misc]
        if bellman_path:
            bellman_edges = path_edges(graph, bellman_path)

    specs = [
        ("full_graph.png", [], "Full Graph: Neighboring-State Highway Network", "graph edge"),
        ("bfs_graph.png", bfs_edges, f"BFS Traversal: Starting from {start}", "BFS tree edge"),
        ("dfs_graph.png", dfs_edges, f"DFS Traversal: Starting from {start}", "DFS tree edge"),
        ("prim_mst.png", prim_edges, "Prim Algorithm: Minimum Spanning Tree", "Prim MST edge"),
        ("kruskal_mst.png", kruskal_edges, "Kruskal Algorithm: Minimum Spanning Tree", "Kruskal MST edge"),
        ("dijkstra_route.png", dijkstra_edges, f"Dijkstra Algorithm: Shortest Route from {start} to {end}", "Dijkstra route edge"),
    ]
    if bellman_edges:
        specs.append(
            (
                "bellman_ford_route.png",
                bellman_edges,
                f"Bellman-Ford Algorithm: Shortest Route from {start} to {end}",
                "Bellman-Ford route edge",
            )
        )

    generated: list[Path] = []
    for filename, selected_edges, title, label in specs:
        filepath = OUTPUT_DIR / filename
        if save_graph_png(cities, graph, selected_edges, filepath, title, label):
            generated.append(filepath)
        svg_path = OUTPUT_DIR / filename.replace(".png", ".svg")
        save_graph_svg(cities, graph, selected_edges, svg_path, title)
        generated.append(svg_path)
    return generated


def safe_filename(text: str) -> str:
    cleaned = []
    for char in text.lower().replace(" ", "_"):
        cleaned.append(char if char.isalnum() or char in {"_", "-"} else "_")
    return "".join(cleaned).strip("_")


def open_image_file(path: Path) -> None:
    if not AUTO_OPEN_IMAGES:
        return
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        print(f"Opened image: {path}")
    except Exception as error:
        print(f"Could not open image automatically: {error}")


def save_result_images(
    cities: dict[str, City],
    graph: dict[str, list[Edge]],
    edges: list[Edge],
    base_filename: str,
    title: str,
) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    base = base_filename.removesuffix(".svg").removesuffix(".png")
    png_path = OUTPUT_DIR / f"{base}.png"
    svg_path = OUTPUT_DIR / f"{base}.svg"
    save_graph_png(cities, graph, edges, png_path, title, "selected algorithm result")
    save_graph_svg(cities, graph, edges, svg_path, title)
    print(f"Saved map PNG: {png_path}")
    print(f"Saved map SVG: {svg_path}")
    open_image_file(png_path)
    return png_path, svg_path


def save_simple_png_graph(
    cities: dict[str, City],
    graph: dict[str, list[Edge]],
    selected_edges: list[Edge],
    filepath: Path,
    width: int = 1400,
    height: int = 900,
) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    background = (248, 250, 252)
    canvas = [[background for _ in range(width)] for _ in range(height)]

    min_lon, max_lon, min_lat, max_lat = graph_bounds(cities)
    x_span = max(max_lon - min_lon, 0.01)
    y_span = max(max_lat - min_lat, 0.01)
    margin = 55

    def project_lonlat(lon: float, lat: float) -> tuple[int, int]:
        x = margin + round(((lon - min_lon) / x_span) * (width - 2 * margin))
        y = margin + round((1 - ((lat - min_lat) / y_span)) * (height - 2 * margin))
        return x, y

    def project(city_name: str) -> tuple[int, int]:
        city = cities[city_name]
        return project_lonlat(city.longitude, city.latitude)

    positions = {city_name: project(city_name) for city_name in cities}
    selected_keys = {
        frozenset((edge.source, edge.target))
        for edge in selected_edges
    }
    selected_cities = {
        city_name
        for edge in selected_edges
        for city_name in (edge.source, edge.target)
    }

    states_in_graph = {city.state for city in cities.values()}
    for state, rings in load_state_polygons():
        if state not in states_in_graph:
            continue
        for ring in rings:
            projected = [project_lonlat(lon, lat) for lon, lat in ring]
            for start, end in zip(projected, projected[1:]):
                draw_png_line(canvas, start, end, (100, 116, 139), 1)

    for edge in unique_edges(graph):
        key = frozenset((edge.source, edge.target))
        if key not in selected_keys:
            draw_png_line(canvas, positions[edge.source], positions[edge.target], (148, 163, 184), 1)

    for edge in selected_edges:
        draw_png_line(canvas, positions[edge.source], positions[edge.target], (185, 28, 28), 4)

    for city_name, point in positions.items():
        color = (15, 118, 110) if city_name in selected_cities else (37, 99, 235)
        draw_png_circle(canvas, point, 8 if city_name in selected_cities else 6, color)
        draw_png_circle(canvas, point, 10 if city_name in selected_cities else 8, (255, 255, 255), outline_only=True)

    write_png(filepath, canvas)


def draw_png_line(
    canvas: list[list[tuple[int, int, int]]],
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    x1, y1 = start
    x2, y2 = end
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    step_x = 1 if x1 < x2 else -1
    step_y = 1 if y1 < y2 else -1
    error = dx + dy

    while True:
        draw_png_circle(canvas, (x1, y1), max(1, thickness), color)
        if x1 == x2 and y1 == y2:
            break
        doubled_error = 2 * error
        if doubled_error >= dy:
            error += dy
            x1 += step_x
        if doubled_error <= dx:
            error += dx
            y1 += step_y


def draw_png_circle(
    canvas: list[list[tuple[int, int, int]]],
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    outline_only: bool = False,
) -> None:
    cx, cy = center
    height = len(canvas)
    width = len(canvas[0])
    inner = max(0, radius - 2)
    for y in range(cy - radius, cy + radius + 1):
        if y < 0 or y >= height:
            continue
        for x in range(cx - radius, cx + radius + 1):
            if x < 0 or x >= width:
                continue
            distance_sq = (x - cx) ** 2 + (y - cy) ** 2
            if outline_only:
                if inner ** 2 <= distance_sq <= radius ** 2:
                    canvas[y][x] = color
            elif distance_sq <= radius ** 2:
                canvas[y][x] = color


def write_png(filepath: Path, canvas: list[list[tuple[int, int, int]]]) -> None:
    height = len(canvas)
    width = len(canvas[0])
    raw_rows = []
    for row in canvas:
        raw_rows.append(b"\x00" + b"".join(bytes(pixel) for pixel in row))
    raw = b"".join(raw_rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, level=9))
    png += chunk(b"IEND", b"")
    filepath.write_bytes(png)


def draw_line(
    canvas: list[list[str]],
    start: tuple[int, int],
    end: tuple[int, int],
    char: str,
    overwrite: bool = False,
) -> None:
    x1, y1 = start
    x2, y2 = end
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    step_x = 1 if x1 < x2 else -1
    step_y = 1 if y1 < y2 else -1
    error = dx + dy

    while True:
        if 0 <= y1 < len(canvas) and 0 <= x1 < len(canvas[0]):
            if overwrite or canvas[y1][x1] == " ":
                canvas[y1][x1] = char
        if x1 == x2 and y1 == y2:
            break
        doubled_error = 2 * error
        if doubled_error >= dy:
            error += dy
            x1 += step_x
        if doubled_error <= dx:
            error += dx
            y1 += step_y


def print_terminal_graph(
    cities: dict[str, City],
    graph: dict[str, list[Edge]],
    route_path: list[str],
    width: int = 96,
    height: int = 28,
) -> None:
    print_section("TERMINAL GRAPH VIEW")
    print("This is a coordinate-based ASCII drawing. Dots are allowed graph edges; stars are the Dijkstra route.")

    min_lon = min(city.longitude for city in cities.values())
    max_lon = max(city.longitude for city in cities.values())
    min_lat = min(city.latitude for city in cities.values())
    max_lat = max(city.latitude for city in cities.values())
    x_span = max(max_lon - min_lon, 0.01)
    y_span = max(max_lat - min_lat, 0.01)
    symbols = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#%&+=?"
    city_symbols = {
        city_name: symbols[index % len(symbols)]
        for index, city_name in enumerate(sorted(cities))
    }

    def project(city_name: str) -> tuple[int, int]:
        city = cities[city_name]
        x = round(((city.longitude - min_lon) / x_span) * (width - 1))
        y = round((1 - ((city.latitude - min_lat) / y_span)) * (height - 1))
        return x, y

    positions = {city_name: project(city_name) for city_name in cities}
    canvas = [[" " for _ in range(width)] for _ in range(height)]
    route_edges = {
        frozenset((source, target))
        for source, target in zip(route_path, route_path[1:])
    }

    seen_edges: set[frozenset[str]] = set()
    for source, edges in graph.items():
        for edge in edges:
            key = frozenset((source, edge.target))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            if key not in route_edges:
                draw_line(canvas, positions[source], positions[edge.target], ".")

    for source, target in zip(route_path, route_path[1:]):
        draw_line(canvas, positions[source], positions[target], "*", overwrite=True)

    for city_name, (x, y) in positions.items():
        canvas[y][x] = city_symbols[city_name]

    border = "+" + "-" * width + "+"
    print(border)
    for row in canvas:
        print("|" + "".join(row) + "|")
    print(border)

    print("\nLegend:")
    for city_name in sorted(cities):
        city = cities[city_name]
        marker = "*" if city_name in route_path else " "
        print(f"  {city_symbols[city_name]} = {city_name}, {city.state}{marker}")
    print("\nLegend marker: city rows ending with * are on the Dijkstra route.")


def print_perf(results: list[PerfResult]) -> None:
    print("\nSECTION 7. PERFORMANCE MONITOR")
    print("algorithm        elapsed_ms   cpu_%   peak_mem_kb   disk_read_kb   disk_write_kb")
    for item in results:
        print(
            f"{item.name:<14} {item.elapsed_ms:>10.3f} "
            f"{item.cpu_percent:>7.1f} {item.memory_peak_kb:>13.1f} "
            f"{item.disk_read_kb:>14.1f} {item.disk_write_kb:>15.1f}"
        )


def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_city_inventory(cities: dict[str, City]) -> None:
    print_section("SECTION 1. CITY DATASET")
    print(f"Coverage: {len(cities)} cities, {len({city.state for city in cities.values()})} states/regions")
    print("Each row is one graph node.")
    print("\ncity                 state  timezone  elevation_ft")
    print("-" * 55)
    for city in sorted(cities.values(), key=lambda item: (item.state, item.name)):
        print(f"{city.name:<20} {city.state:<5} {city.timezone:<9} {city.elevation_ft:>8.0f}")


def print_input_graph(cities: dict[str, City], graph: dict[str, list[Edge]]) -> None:
    edge_count = sum(len(edges) for edges in graph.values()) // 2
    print_section("SECTION 2. INPUT GRAPH")
    print("Rule used to build edges: connect cities only when their states share a border.")
    print(f"Graph size: {len(graph)} nodes and {edge_count} undirected edges.")
    print("\nAdjacency list with estimated highway mileage:")
    for city_name in sorted(graph):
        neighbors = ", ".join(
            f"{edge.target} ({edge.map_distance:.1f} mi)"
            for edge in graph[city_name]
        )
        state = cities[city_name].state
        print(f"{city_name}, {state}: {neighbors}")


def print_edge_graph(title: str, edges: list[Edge]) -> None:
    print(title)
    if not edges:
        print("  no edges")
        return
    for edge in edges:
        print(f"  {edge.source} -> {edge.target}  {edge.map_distance:.1f} mi")


def path_edges(graph: dict[str, list[Edge]], path: list[str]) -> list[Edge]:
    return [edge_by_city(graph, source, target) for source, target in zip(path, path[1:])]


def print_algorithm_perf(result: PerfResult) -> None:
    print(
        "Performance: "
        f"{result.elapsed_ms:.3f} ms, "
        f"CPU {result.cpu_percent:.1f}%, "
        f"peak memory {result.memory_peak_kb:.1f} KB, "
        f"disk read/write {result.disk_read_kb:.1f}/{result.disk_write_kb:.1f} KB"
    )


def print_bfs_section(result: PerfResult) -> None:
    order, tree_edges = result.result  # type: ignore[misc]
    print_section("SECTION 3. BFS RESULT")
    print("Purpose: BFS checks the network level by level from the start city.")
    print(f"Visited nodes: {len(order)}")
    print(f"Visit order: {' -> '.join(order)}")
    print_edge_graph("\nBFS traversal graph:", tree_edges)
    print("Interpretation: this is useful for reachability and broad expansion, not shortest weighted distance.")
    print_algorithm_perf(result)


def print_dfs_section(result: PerfResult) -> None:
    order, tree_edges = result.result  # type: ignore[misc]
    print_section("SECTION 4. DFS RESULT")
    print("Purpose: DFS follows one branch deeply before returning to unexplored branches.")
    print(f"Visited nodes: {len(order)}")
    print(f"Visit order: {' -> '.join(order)}")
    print_edge_graph("\nDFS traversal graph:", tree_edges)
    print("Interpretation: this traversal is good for structural exploration, but it is not optimized for distance.")
    print_algorithm_perf(result)


def print_mst_section(title: str, result: PerfResult, note: str) -> None:
    tree_edges = result.result  # type: ignore[assignment]
    total = sum(edge.map_distance for edge in tree_edges)
    print_section(title)
    print(note)
    print(f"MST edges selected: {len(tree_edges)}")
    print(f"Total MST distance: {total:.1f} miles")
    print_edge_graph("\nMinimum spanning tree graph:", tree_edges)
    print("Interpretation: the MST connects all cities with low total mileage, but it is not a point-to-point route.")
    print_algorithm_perf(result)


def print_dijkstra_section(
    result: PerfResult,
    graph: dict[str, list[Edge]],
    route: dict[str, object],
) -> None:
    shortest_distance, shortest_path = result.result  # type: ignore[misc]
    print_section("SECTION 6. DIJKSTRA RESULT AND TRAVEL PLAN")
    print("Purpose: Dijkstra finds the shortest weighted route between the selected start and destination.")
    print(f"Shortest path: {' -> '.join(shortest_path)}")
    print(f"Dijkstra map distance: {shortest_distance:.1f} miles")
    print_edge_graph("\nShortest-path graph:", path_edges(graph, shortest_path))
    print("\nTravel metrics for the selected route:")
    print(f"  map distance: {route['map_distance']} miles")
    print(f"  elevation-adjusted real distance: {route['real_distance']} miles")
    print(f"  best start date: {route['best_start_date']}")
    print(f"  accumulated weather risk: {route['accumulated_risk']} (average {route.get('average_risk', 0)} per leg)")
    print(f"  gasoline consumption: {route['gasoline_gallons']} gallons at {BASE_MPG:g} mpg baseline")
    print(f"  travel days: {route['travel_days']} at max {MAX_DRIVING_HOURS_PER_DAY} hours/day")
    print("Interpretation: this is the route report used for business decisions because it combines distance, weather risk, elevation, and fuel.")
    print_algorithm_perf(result)


def print_shortest_path_section(
    title: str,
    result: PerfResult,
    graph: dict[str, list[Edge]],
    route: dict[str, object],
) -> None:
    distance, path = result.result  # type: ignore[misc]
    print_section(title)
    print(f"Shortest path: {' -> '.join(path)}")
    print(f"Map distance: {distance:.1f} miles")
    print_edge_graph("\nShortest-path graph:", path_edges(graph, path))
    print("\nTravel metrics:")
    print(f"  elevation-adjusted real distance: {route['real_distance']} miles")
    print(f"  best start date: {route['best_start_date']}")
    print(f"  accumulated weather risk: {route['accumulated_risk']} (average {route.get('average_risk', 0)} per leg)")
    print(f"  gasoline consumption: {route['gasoline_gallons']} gallons")
    print_algorithm_perf(result)


def ask_city(cities: dict[str, City], prompt: str, default: str | None = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if not value and default:
            return default
        matches = [name for name in cities if name.lower() == value.lower()]
        if matches:
            return matches[0]
        print(f"Unknown city. Try one of: {', '.join(sorted(cities))}")


def build_default_context() -> tuple[dict[str, City], dict[str, list[Edge]], PerformanceMonitor]:
    cities = load_cities()
    graph = build_graph(cities)
    return cities, graph, PerformanceMonitor()


def show_cities_and_graph() -> None:
    cities, graph, _ = build_default_context()
    print_city_inventory(cities)
    print_input_graph(cities, graph)
    save_result_images(
        cities,
        graph,
        [],
        "menu_full_graph",
        "Full Graph: Neighboring-State Highway Network",
    )



def travel_plan() -> None:
    """Interactive travel planner: Dijkstra best path with full travel report."""
    cities, graph, monitor = build_default_context()
    print_section("TRAVEL PLAN")
    print("Plan a trip between two cities using the shortest Dijkstra route.")
    print(f"Weather window: {START_DATE.isoformat()} to {END_DATE.isoformat()}")
    print(f"Driving limit : {MAX_DRIVING_HOURS_PER_DAY} hours/day at up to {MAX_SPEED_MPH} mph")
    print(f"Fuel economy  : {BASE_MPG:g} mpg baseline\n")

    start = ask_city(cities, "Departure city", "Chicago")
    end = ask_city(cities, "Destination city", "Miami")

    result = monitor.run("Dijkstra", lambda: dijkstra(graph, start, end))
    shortest_distance, shortest_path = result.result  # type: ignore[misc]

    if not shortest_path:
        print(f"\nNo neighboring-state route exists from {start} to {end}.")
        return

    route = evaluate_route(cities, graph, shortest_path)
    total_real = route["real_distance"]
    travel_days = route["travel_days"]
    total_hours = round(total_real / MAX_SPEED_MPH, 2)
    gallons = route["gasoline_gallons"]

    print_section(f"TRAVEL PLAN: {start} \u2192 {end}")
    print(f"\nRoute ({len(shortest_path)} cities):")
    print(f"  {' -> '.join(shortest_path)}")
    print(f"\n{'='*56}")
    print(f"  Map distance              : {route['map_distance']} miles")
    print(f"  Elevation-adjusted dist.  : {total_real} miles")
    print(f"  Travel days               : {travel_days} (max {MAX_DRIVING_HOURS_PER_DAY} hrs driving/day)")
    print(f"  Total hours on road       : {total_hours} hrs")
    print(f"  Gasoline consumed         : {gallons} gallons ({BASE_MPG:g} mpg)")
    print(f"  Best start date           : {route['best_start_date']}")
    print(f"  Accumulated weather risk  : {route['accumulated_risk']} (average {route.get('average_risk', 0)} per leg)")
    print(f"{'='*56}")

    legs = route.get("legs", [])
    if legs:
        print(f"\nLeg-by-leg breakdown ({len(legs)} legs):")
        print(f"  {'#':<4} {'From':<20} {'To':<20} {'Map mi':>8} {'Real mi':>9} {'Slope':>9}")
        print(f"  {'-'*4} {'-'*20} {'-'*20} {'-'*8} {'-'*9} {'-'*9}")
        for index, leg in enumerate(legs, start=1):
            print(
                f"  {index:<4} {leg['from']:<20} {leg['to']:<20} "
                f"{leg['map_distance']:>8.1f} {leg['real_distance']:>9.1f} "
                f"{leg['tan_theta']:>+9.4f}"
            )

    # Day-by-day itinerary — distribute legs across all travel days
    best_start = date.fromisoformat(str(route["best_start_date"]))
    print(f"\nDay-by-day itinerary (starting {route['best_start_date']}):")

    # Find which legs overlap each day's driving window
    leg_cumulative = []
    running = 0.0
    for leg in legs:
        leg_start_mile = running
        running += leg["real_distance"]
        leg_cumulative.append((leg, leg_start_mile, running))

    for d in range(travel_days):
        day_start_mile = d * MAX_DAILY_MILES
        day_end_mile = min((d + 1) * MAX_DAILY_MILES, total_real)
        day_drive = day_end_mile - day_start_mile
        day_hours = round(day_drive / MAX_SPEED_MPH, 1)
        travel_date = best_start + timedelta(days=d)
        print(f"  Day {d + 1} ({travel_date.isoformat()}) — {day_drive:.1f} mi, {day_hours} hrs driving:")
        for leg, ls, le in leg_cumulative:
            if le > day_start_mile and ls < day_end_mile:
                src_w = weather_condition(cities[leg["from"]], travel_date)
                dst_w = weather_condition(cities[leg["to"]], travel_date)
                print(
                    f"    {leg['from']} -> {leg['to']}  "
                    f"{leg['real_distance']:.1f} mi  "
                    f"weather: {src_w}/{dst_w}"
                )

    print_algorithm_perf(result)

    # Save map
    edges = path_edges(graph, shortest_path)
    save_result_images(
        cities,
        graph,
        edges,
        f"travel_plan_{safe_filename(start)}_to_{safe_filename(end)}",
        f"Travel Plan: {start} to {end}",
    )

def run_single_algorithm(algorithm: str) -> None:
    cities, graph, monitor = build_default_context()
    algorithm = algorithm.lower()

    if algorithm == "bfs":
        start = ask_city(cities, "Start city for BFS", "Chicago")
        result = monitor.run("BFS", lambda: bfs_with_tree(graph, start))
        print_bfs_section(result)
        _, tree_edges = result.result  # type: ignore[misc]
        save_result_images(
            cities,
            graph,
            tree_edges,
            f"menu_bfs_{safe_filename(start)}",
            f"BFS Traversal: Starting from {start}",
        )
    elif algorithm == "dfs":
        start = ask_city(cities, "Start city for DFS", "Chicago")
        result = monitor.run("DFS", lambda: dfs_with_tree(graph, start))
        print_dfs_section(result)
        _, tree_edges = result.result  # type: ignore[misc]
        save_result_images(
            cities,
            graph,
            tree_edges,
            f"menu_dfs_{safe_filename(start)}",
            f"DFS Traversal: Starting from {start}",
        )
    elif algorithm == "prim":
        start = ask_city(cities, "Start city for Prim", "Chicago")
        result = monitor.run("Prim", lambda: prim(graph, start))
        print_mst_section(
            "PRIM RESULT",
            result,
            "Purpose: Prim grows one minimum spanning tree outward from the selected start city.",
        )
        tree_edges = result.result  # type: ignore[assignment]
        save_result_images(
            cities,
            graph,
            tree_edges,
            f"menu_prim_{safe_filename(start)}",
            f"Prim Algorithm: Minimum Spanning Tree from {start}",
        )
    elif algorithm == "kruskal":
        result = monitor.run("Kruskal", lambda: kruskal(graph))
        print_mst_section(
            "KRUSKAL RESULT",
            result,
            "Purpose: Kruskal sorts all edges and adds the next cheapest edge that does not create a cycle.",
        )
        tree_edges = result.result  # type: ignore[assignment]
        save_result_images(
            cities,
            graph,
            tree_edges,
            "menu_kruskal_mst",
            "Kruskal Algorithm: Minimum Spanning Tree",
        )
    elif algorithm in {"dijkstra", "bellman-ford", "bellman ford"}:
        default_end = "Miami" if algorithm == "dijkstra" else "Boston"
        start = ask_city(cities, "Start city", "Chicago")
        end = ask_city(cities, "Destination city", default_end)
        if algorithm == "dijkstra":
            result = monitor.run("Dijkstra", lambda: dijkstra(graph, start, end))
            title = f"DIJKSTRA RESULT: {start} TO {end}"
        else:
            result = monitor.run("Bellman-Ford", lambda: bellman_ford(graph, start, end))
            title = f"BELLMAN-FORD RESULT: {start} TO {end}"
        _, path = result.result  # type: ignore[misc]
        if not path:
            print(f"No route found from {start} to {end}.")
            return
        route = evaluate_route(cities, graph, path)
        print_shortest_path_section(title, result, graph, route)
        filename_algorithm = "dijkstra" if algorithm == "dijkstra" else "bellman_ford"
        save_result_images(
            cities,
            graph,
            path_edges(graph, path),
            f"menu_{filename_algorithm}_{safe_filename(start)}_to_{safe_filename(end)}",
            title,
        )
    else:
        print(f"Unknown algorithm: {algorithm}")


def run_all_algorithms_interactive() -> None:
    cities, graph, monitor = build_default_context()
    start = ask_city(cities, "Start city for traversal and route", "Chicago")
    end = ask_city(cities, "Destination city for shortest path", "Miami")
    results = [
        monitor.run("BFS", lambda: bfs_with_tree(graph, start)),
        monitor.run("DFS", lambda: dfs_with_tree(graph, start)),
        monitor.run("Prim", lambda: prim(graph, start)),
        monitor.run("Kruskal", lambda: kruskal(graph)),
        monitor.run("Dijkstra", lambda: dijkstra(graph, start, end)),
        monitor.run("Bellman-Ford", lambda: bellman_ford(graph, start, end)),
    ]
    _, dijkstra_path = results[4].result  # type: ignore[misc]
    _, bellman_path = results[5].result  # type: ignore[misc]
    if dijkstra_path:
        dijkstra_route = evaluate_route(cities, graph, dijkstra_path)
    else:
        dijkstra_route = {}
    if bellman_path:
        bellman_route = evaluate_route(cities, graph, bellman_path)
    else:
        bellman_route = {}

    print_city_inventory(cities)
    print_input_graph(cities, graph)
    print_bfs_section(results[0])
    print_dfs_section(results[1])
    print_mst_section("PRIM RESULT", results[2], "Purpose: Prim grows one minimum spanning tree outward from the start city.")
    print_mst_section("KRUSKAL RESULT", results[3], "Purpose: Kruskal sorts all edges and avoids cycles.")
    if dijkstra_route:
        print_shortest_path_section(f"DIJKSTRA RESULT: {start} TO {end}", results[4], graph, dijkstra_route)
    if bellman_route:
        print_shortest_path_section(f"BELLMAN-FORD RESULT: {start} TO {end}", results[5], graph, bellman_route)
    print_perf(results)
    image_files = generate_graph_images(cities, graph, results, dijkstra_path, start, end) if dijkstra_path else []
    print("\nSaved map files:")
    for image_file in image_files:
        print(f"- {image_file}")
    for image_file in image_files:
        if image_file.suffix.lower() == ".png":
            open_image_file(image_file)


def compare_algorithms() -> None:
    cities, graph, monitor = build_default_context()
    traversal_starts = ["Chicago", "Dallas", "Boston", "Atlanta", "Minneapolis"]
    route_cases = [
        ("Chicago", "Miami"),
        ("Dallas", "Boston"),
        ("Minneapolis", "Atlanta"),
        ("New Orleans", "New York"),
        ("Oklahoma City", "Washington"),
    ]

    print_section("COMPARISON 1. BFS VS DFS")
    print("Five cases compare traversal order and runtime from the same start city.")
    print("case  start city       bfs_ms   dfs_ms   same_nodes   first_bfs_path")
    for index, start in enumerate(traversal_starts, start=1):
        bfs_result = monitor.run("BFS", lambda s=start: bfs_with_tree(graph, s))
        dfs_result = monitor.run("DFS", lambda s=start: dfs_with_tree(graph, s))
        bfs_order, _ = bfs_result.result  # type: ignore[misc]
        dfs_order, _ = dfs_result.result  # type: ignore[misc]
        same_nodes = set(bfs_order) == set(dfs_order)
        print(
            f"{index:<5} {start:<16} {bfs_result.elapsed_ms:>6.3f} "
            f"{dfs_result.elapsed_ms:>7.3f} {str(same_nodes):<10} {' -> '.join(bfs_order[:5])}"
        )
    print("Observation: BFS and DFS should visit the same connected component, but their visit orders differ.")

    print_section("COMPARISON 2. PRIM VS KRUSKAL")
    print("Five cases run Prim from different start cities and compare it with Kruskal.")
    print("case  prim_start       prim_ms  kruskal_ms  prim_miles  kruskal_miles")
    for index, start in enumerate(traversal_starts, start=1):
        prim_result = monitor.run("Prim", lambda s=start: prim(graph, s))
        kruskal_result = monitor.run("Kruskal", lambda: kruskal(graph))
        prim_total = sum(edge.map_distance for edge in prim_result.result)  # type: ignore[union-attr]
        kruskal_total = sum(edge.map_distance for edge in kruskal_result.result)  # type: ignore[union-attr]
        print(
            f"{index:<5} {start:<16} {prim_result.elapsed_ms:>7.3f} "
            f"{kruskal_result.elapsed_ms:>10.3f} {prim_total:>11.1f} {kruskal_total:>14.1f}"
        )
    print("Observation: Prim and Kruskal should produce the same MST total even if the selected edges appear in a different order.")

    print_section("COMPARISON 3. DIJKSTRA VS BELLMAN-FORD")
    print("Five cases compare shortest-path distance and runtime.")
    print("case  route                              dijkstra_ms  bellman_ms  same_distance  miles")
    for index, (start, end) in enumerate(route_cases, start=1):
        dijkstra_result = monitor.run("Dijkstra", lambda s=start, e=end: dijkstra(graph, s, e))
        bellman_result = monitor.run("Bellman-Ford", lambda s=start, e=end: bellman_ford(graph, s, e))
        dijkstra_distance, dijkstra_path = dijkstra_result.result  # type: ignore[misc]
        bellman_distance, bellman_path = bellman_result.result  # type: ignore[misc]
        same_distance = abs(dijkstra_distance - bellman_distance) < 0.001
        route_text = f"{start} to {end}"
        print(
            f"{index:<5} {route_text:<34} {dijkstra_result.elapsed_ms:>10.3f} "
            f"{bellman_result.elapsed_ms:>10.3f} {str(same_distance):<13} {dijkstra_distance:>7.1f}"
        )
        print(f"      Dijkstra:     {' -> '.join(dijkstra_path)}")
        print(f"      Bellman-Ford: {' -> '.join(bellman_path)}")
    print("Observation: both algorithms return the same shortest distances. Dijkstra is usually faster here because all edge weights are positive.")


def interactive_menu() -> None:
    while True:
        print_section("CENTRAL/EASTERN US GRAPH ROUTE MENU")
        print("1.  Show cities and graph")
        print("2.  Travel Plan (Dijkstra best path + travel info)")
        print("3.  Run BFS")
        print("4.  Run DFS")
        print("5.  Run Prim")
        print("6.  Run Kruskal")
        print("7.  Run Dijkstra")
        print("8.  Run Bellman-Ford")
        print("9.  Run all algorithms")
        print("10. Compare algorithms")
        print("0.  Exit")
        choice = input("Select an option: ").strip()

        if choice == "1":
            show_cities_and_graph()
        elif choice == "2":
            travel_plan()
        elif choice == "3":
            run_single_algorithm("bfs")
        elif choice == "4":
            run_single_algorithm("dfs")
        elif choice == "5":
            run_single_algorithm("prim")
        elif choice == "6":
            run_single_algorithm("kruskal")
        elif choice == "7":
            run_single_algorithm("dijkstra")
        elif choice == "8":
            run_single_algorithm("bellman-ford")
        elif choice == "9":
            run_all_algorithms_interactive()
        elif choice == "10":
            compare_algorithms()
        elif choice == "0":
            print("Exiting graph route program.")
            return
        else:
            print("Invalid option. Please choose 0-10.")


def run_demo(start: str, end: str, random_count: int | None, terminal_map: bool) -> None:
    cities = load_cities()
    if start not in cities or end not in cities:
        raise SystemExit(f"Choose cities from: {', '.join(sorted(cities))}")

    if random_count:
        cities = connected_city_sample(cities, start, end, random_count)

    graph = build_graph(cities)

    monitor = PerformanceMonitor()
    results = [
        monitor.run("BFS", lambda: bfs_with_tree(graph, start)),
        monitor.run("DFS", lambda: dfs_with_tree(graph, start)),
        monitor.run("Prim", lambda: prim(graph, start)),
        monitor.run("Kruskal", lambda: kruskal(graph)),
        monitor.run("Dijkstra", lambda: dijkstra(graph, start, end)),
        monitor.run("Bellman-Ford", lambda: bellman_ford(graph, start, end)),
    ]

    _, shortest_path = results[4].result  # type: ignore[misc]
    if not shortest_path:
        raise SystemExit(f"No neighboring-state route exists from {start} to {end}.")
    _, bellman_path = results[5].result  # type: ignore[misc]

    route = evaluate_route(cities, graph, shortest_path)
    bellman_route = evaluate_route(cities, graph, bellman_path) if bellman_path else None

    OUTPUT_DIR.mkdir(exist_ok=True)
    image_files = generate_graph_images(cities, graph, results, shortest_path, start, end)

    print("\nCENTRAL/EASTERN US HIGHWAY ROUTE STUDY")
    print(f"Start city: {start}")
    print(f"Destination city: {end}")
    print(f"Weather window: {START_DATE.isoformat()} to {END_DATE.isoformat()}")
    print(f"Driving limit: {MAX_DRIVING_HOURS_PER_DAY} hours/day at {MAX_SPEED_MPH} mph")
    if terminal_map:
        print_terminal_graph(cities, graph, shortest_path)
    print_city_inventory(cities)
    print_input_graph(cities, graph)
    print_bfs_section(results[0])
    print_dfs_section(results[1])
    print_mst_section(
        "SECTION 5A. PRIM RESULT",
        results[2],
        "Purpose: Prim grows one minimum spanning tree outward from the start city.",
    )
    print_mst_section(
        "SECTION 5B. KRUSKAL RESULT",
        results[3],
        "Purpose: Kruskal sorts all edges and adds the next cheapest edge that does not create a cycle.",
    )
    print_dijkstra_section(results[4], graph, route)
    if bellman_route:
        print_shortest_path_section(f"SECTION 6B. BELLMAN-FORD RESULT: {start} TO {end}", results[5], graph, bellman_route)
    print_perf(results)
    print("\nGenerated files:")
    if image_files:
        for image_file in image_files:
            print(f"- {image_file}")
            if image_file.suffix.lower() == ".png":
                open_image_file(image_file)
    else:
        print("- PNG graphs used the built-in fallback. Optional packages for richer metrics/images: psutil matplotlib")
    print(f"- {OUTPUT_DIR / 'terminal_output.txt'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Central/Eastern US graph route project")
    parser.add_argument("--start", default="Chicago", help="Starting city")
    parser.add_argument("--end", default="Miami", help="Destination city")
    parser.add_argument("--random", type=int, default=None, help="Randomly select 10-20 or another N cities")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for repeatable random city sets")
    parser.add_argument("--terminal-map", action="store_true", help="Print an ASCII graph in the terminal")
    parser.add_argument("--menu", action="store_true", help="Open the interactive menu")
    parser.add_argument("--open-images", action="store_true", help="Open generated PNG images with the system default app")
    parser.add_argument("--no-open-images", action="store_true", help="Do not open generated PNG images automatically")
    args = parser.parse_args()

    global AUTO_OPEN_IMAGES
    AUTO_OPEN_IMAGES = not args.no_open_images
    random.seed(args.seed)
    terminal_capture = io.StringIO()
    tee = TeeOutput(sys.stdout, terminal_capture)
    with contextlib.redirect_stdout(tee):
        if args.menu or len(sys.argv) == 1:
            interactive_menu()
        else:
            run_demo(args.start, args.end, args.random, args.terminal_map)
    terminal_text = terminal_capture.getvalue()
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "terminal_output.txt").write_text(terminal_text, encoding="utf-8")


if __name__ == "__main__":
    main()
