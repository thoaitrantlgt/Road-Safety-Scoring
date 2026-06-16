from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("configs/visualization.json")


def collect_points(coordinates: Any) -> list[list[float]]:
    points: list[list[float]] = []

    def visit(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            points.append([float(value[0]), float(value[1])])
            return
        if isinstance(value, list):
            for item in value:
                visit(item)

    visit(coordinates)
    return points


def simplify_points(points: list[list[float]], max_points: int) -> list[list[float]]:
    if len(points) <= max_points:
        return points
    step = max(1, len(points) // max_points)
    simplified = points[::step]
    if simplified[-1] != points[-1]:
        simplified.append(points[-1])
    return simplified[:max_points]


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def risk_sort_key(feature: dict[str, Any]) -> tuple[int, float, float, float]:
    props = feature.get("properties") or {}
    band = props.get("risk_band")
    priority = {"Critical": 3, "Moderate": 2, "Low": 1}.get(band, 0)
    return (
        priority,
        numeric(props.get("speed_safety_score")),
        numeric(props.get("speeding_pressure")),
        numeric(props.get("vru_exposure_index")),
    )


def intervention_recommendation(props: dict[str, Any]) -> str:
    band = props.get("risk_band")
    speed_variance = numeric(props.get("speed_variance_kmh"))
    speeding_pressure = numeric(props.get("speeding_pressure"))
    vru_exposure = numeric(props.get("vru_exposure_index"))
    if band == "Critical" and speeding_pressure >= 70:
        return "Immediate speed-limit review plus targeted enforcement"
    if band == "Critical" and speed_variance >= 25 and vru_exposure >= 70:
        return "Immediate speed-limit review and traffic calming assessment"
    if band == "Critical":
        return "Immediate corridor safety review"
    if band == "Moderate":
        return "Schedule speed-management review and monitoring"
    return "Routine monitoring"


def build_map_segments(config: dict[str, Any]) -> dict[str, Any]:
    with Path(config["scored_geojson"]).open("r", encoding="utf-8") as file:
        geojson = json.load(file)
    max_segments = config["map"]["max_segments"]
    max_points = config["map"]["max_points_per_segment"]
    selected = sorted(geojson.get("features", []), key=risk_sort_key, reverse=True)[:max_segments]
    segments: list[dict[str, Any]] = []
    bbox: list[float] | None = None

    for rank, feature in enumerate(selected, start=1):
        props = feature.get("properties") or {}
        points = simplify_points(collect_points((feature.get("geometry") or {}).get("coordinates")), max_points)
        if len(points) < 2:
            continue
        for lon, lat in points:
            if bbox is None:
                bbox = [lon, lat, lon, lat]
            else:
                bbox = [min(bbox[0], lon), min(bbox[1], lat), max(bbox[2], lon), max(bbox[3], lat)]
        segments.append(
            {
                "rank": rank,
                "id": props.get("road_id"),
                "area": props.get("source_area"),
                "road_class": props.get("road_class"),
                "land_use": props.get("land_use_norm") or props.get("land_use"),
                "score": props.get("speed_safety_score"),
                "band": props.get("risk_band"),
                "speed_limit": props.get("speed_limit_kmh"),
                "median_speed": props.get("median_speed_kmh"),
                "v85_speed": props.get("v85_speed_kmh"),
                "speed_variance": props.get("speed_variance_kmh"),
                "speeding_pressure": props.get("speeding_pressure"),
                "vru_exposure": props.get("vru_exposure_index"),
                "quality": props.get("feature_quality_flag"),
                "recommendation": intervention_recommendation(props),
                "points": points,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bbox": bbox,
        "segments": segments,
        "top_priority": segments[:50],
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Highest-Priority Speed Review Map</title>
  <style>
    :root {
      --critical: #c83232;
      --moderate: #e5962d;
      --low: #3b8f4f;
      --ink: #1f2933;
      --muted: #66737f;
      --line: #d8ddd3;
      --paper: #ffffff;
      --wash: #eef1ed;
    }
    html, body { margin: 0; height: 100%; font-family: Arial, sans-serif; background: var(--wash); color: var(--ink); }
    #app { display: grid; grid-template-columns: 360px 1fr; height: 100%; }
    aside { border-right: 1px solid var(--line); background: var(--paper); overflow: auto; }
    .panel { padding: 16px 18px; border-bottom: 1px solid var(--line); }
    h1 { font-size: 20px; margin: 0 0 8px; letter-spacing: 0; line-height: 1.2; }
    h2 { font-size: 12px; margin: 18px 0 8px; color: var(--muted); text-transform: uppercase; letter-spacing: 0; }
    p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.45; }
    label { display: flex; align-items: center; gap: 8px; margin: 8px 0; font-size: 14px; }
    #mapShell { position: relative; min-width: 0; min-height: 0; }
    canvas { width: 100%; height: 100%; display: block; background: #edf1ed; cursor: grab; }
    canvas.dragging { cursor: grabbing; }
    .map-controls { position: absolute; top: 14px; right: 14px; display: flex; align-items: center; gap: 6px; z-index: 2; background: rgba(255,255,255,0.94); border: 1px solid var(--line); border-radius: 6px; padding: 6px; box-shadow: 0 8px 22px rgba(31,41,51,0.12); }
    .map-controls button { min-width: 34px; height: 32px; border-radius: 4px; font-weight: 700; }
    .map-controls .reset { min-width: 56px; font-weight: 400; }
    #zoomLabel { min-width: 52px; text-align: center; font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }
    button { font: inherit; cursor: pointer; border: 1px solid var(--line); background: #fafbf8; color: var(--ink); }
    .stat { display: flex; justify-content: space-between; border-bottom: 1px solid #edf0ea; padding: 7px 0; font-size: 14px; }
    .stat strong { font-variant-numeric: tabular-nums; }
    .legend { display: grid; gap: 8px; margin-top: 10px; font-size: 14px; }
    .legend span { display: inline-block; width: 14px; height: 14px; margin-right: 7px; vertical-align: -2px; }
    #detail { font-size: 14px; line-height: 1.5; background: #f8faf6; border: 1px solid var(--line); padding: 10px; min-height: 142px; }
    #priorityList { display: grid; gap: 7px; }
    .priority-item { text-align: left; border-radius: 4px; padding: 8px; display: grid; gap: 3px; }
    .priority-item.active { outline: 2px solid #2b5b84; background: #f1f7fb; }
    .priority-row { display: flex; justify-content: space-between; gap: 10px; font-size: 13px; }
    .priority-id { color: var(--muted); overflow-wrap: anywhere; }
    .tag { display: inline-block; border-radius: 999px; padding: 2px 7px; color: #fff; font-size: 12px; }
    .Critical { background: var(--critical); }
    .Moderate { background: var(--moderate); }
    .Low { background: var(--low); }
    .toolbar { display: flex; gap: 8px; align-items: center; }
    input[type="search"] { width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid var(--line); border-radius: 4px; font: inherit; }
    @media (max-width: 820px) {
      #app { grid-template-columns: 1fr; grid-template-rows: minmax(360px, 45vh) 1fr; }
      aside { order: 2; border-right: 0; border-top: 1px solid var(--line); }
      #mapShell { order: 1; min-height: 360px; }
      canvas { min-height: 360px; }
    }
  </style>
</head>
<body>
<div id="app">
  <aside>
    <div class="panel">
      <h1>Highest-Priority Speed Review Map</h1>
      <p>Interactive geospatial output identifying road segments that should be prioritized for speed-limit review or intervention.</p>
      <div class="stat"><span>Rendered priority segments</span><strong id="rendered"></strong></div>
      <div class="stat"><span>Critical</span><strong id="criticalCount"></strong></div>
      <div class="stat"><span>Moderate</span><strong id="moderateCount"></strong></div>
      <div class="stat"><span>Low</span><strong id="lowCount"></strong></div>
    </div>
    <div class="panel">
      <h2>Filters</h2>
      <label><input type="checkbox" data-band="Critical" checked> Critical review required</label>
      <label><input type="checkbox" data-band="Moderate" checked> Moderate review queue</label>
      <label><input type="checkbox" data-band="Low"> Low-risk reference</label>
      <h2>Legend</h2>
      <div class="legend">
        <div><span style="background:#c83232"></span>75-100 Critical</div>
        <div><span style="background:#e5962d"></span>46-74 Moderate</div>
        <div><span style="background:#3b8f4f"></span>0-45 Low</div>
      </div>
    </div>
    <div class="panel">
      <h2>Selected Segment</h2>
      <div id="detail">Hover over a segment or select one from the priority list.</div>
    </div>
    <div class="panel">
      <div class="toolbar">
        <input id="search" type="search" placeholder="Filter top priorities by road id or area">
      </div>
      <h2>Top Priority Segments</h2>
      <div id="priorityList"></div>
    </div>
  </aside>
  <div id="mapShell">
    <div class="map-controls" aria-label="Map zoom controls">
      <button id="zoomIn" type="button" title="Zoom in">+</button>
      <button id="zoomOut" type="button" title="Zoom out">-</button>
      <button id="zoomReset" class="reset" type="button" title="Reset map view">Reset</button>
      <span id="zoomLabel">100%</span>
    </div>
    <canvas id="map"></canvas>
  </div>
</div>
<script>
const MAP_DATA = __MAP_DATA__;
const RISK_COUNTS = __RISK_COUNTS__;
const canvas = document.getElementById('map');
const ctx = canvas.getContext('2d');
const detail = document.getElementById('detail');
const priorityList = document.getElementById('priorityList');
const search = document.getElementById('search');
const zoomLabel = document.getElementById('zoomLabel');
const colors = {Critical: '#c83232', Moderate: '#e5962d', Low: '#3b8f4f'};
let projected = [];
let selectedId = null;
let dragState = null;
let suppressClick = false;
const view = {scale: 1, offsetX: 0, offsetY: 0};

function fmt(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a';
  return Number(value).toFixed(digits);
}

function resize() {
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(360, Math.floor(rect.width * devicePixelRatio));
  canvas.height = Math.max(360, Math.floor(rect.height * devicePixelRatio));
  draw();
}

function activeBands() {
  return new Set([...document.querySelectorAll('input[data-band]:checked')].map(input => input.dataset.band));
}

function baseProject(point) {
  const [minX, minY, maxX, maxY] = MAP_DATA.bbox;
  const pad = 34 * devicePixelRatio;
  const width = canvas.width - pad * 2;
  const height = canvas.height - pad * 2;
  const x = pad + ((point[0] - minX) / (maxX - minX)) * width;
  const y = canvas.height - pad - ((point[1] - minY) / (maxY - minY)) * height;
  return [x, y];
}

function project(point) {
  const [x, y] = baseProject(point);
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;
  return [
    (x - centerX) * view.scale + centerX + view.offsetX,
    (y - centerY) * view.scale + centerY + view.offsetY,
  ];
}

function updateZoomLabel() {
  zoomLabel.textContent = `${Math.round(view.scale * 100)}%`;
}

function setZoom(nextScale, centerX = canvas.width / 2, centerY = canvas.height / 2) {
  const oldScale = view.scale;
  const newScale = Math.max(0.6, Math.min(12, nextScale));
  if (newScale === oldScale) return;
  view.offsetX = centerX - (((centerX - canvas.width / 2 - view.offsetX) / oldScale) * newScale + canvas.width / 2);
  view.offsetY = centerY - (((centerY - canvas.height / 2 - view.offsetY) / oldScale) * newScale + canvas.height / 2);
  view.scale = newScale;
  updateZoomLabel();
  draw();
}

function zoomBy(factor, centerX = canvas.width / 2, centerY = canvas.height / 2) {
  setZoom(view.scale * factor, centerX, centerY);
}

function resetView() {
  view.scale = 1;
  view.offsetX = 0;
  view.offsetY = 0;
  updateZoomLabel();
  draw();
}

function draw() {
  if (!MAP_DATA.bbox) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#edf1ed';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const bands = activeBands();
  projected = [];
  for (const segment of MAP_DATA.segments) {
    if (!bands.has(segment.band)) continue;
    const pts = segment.points.map(project);
    projected.push({segment, pts});
    ctx.beginPath();
    pts.forEach((p, i) => i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]));
    ctx.strokeStyle = colors[segment.band] || '#77838f';
    ctx.globalAlpha = segment.band === 'Low' ? 0.28 : 0.74;
    ctx.lineWidth = segment.band === 'Critical' ? 2.25 * devicePixelRatio : 1.35 * devicePixelRatio;
    if (segment.id === selectedId) {
      ctx.globalAlpha = 1;
      ctx.lineWidth = 4.6 * devicePixelRatio;
    }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function distanceToSegment(px, py, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  if (dx === 0 && dy === 0) return Math.hypot(px - a[0], py - a[1]);
  const t = Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy));
}

function nearestSegment(event) {
  const rect = canvas.getBoundingClientRect();
  const px = (event.clientX - rect.left) * devicePixelRatio;
  const py = (event.clientY - rect.top) * devicePixelRatio;
  let best = null;
  let bestDistance = 12 * devicePixelRatio;
  for (const item of projected) {
    for (let i = 1; i < item.pts.length; i++) {
      const d = distanceToSegment(px, py, item.pts[i - 1], item.pts[i]);
      if (d < bestDistance) {
        bestDistance = d;
        best = item.segment;
      }
    }
  }
  return best;
}

function showSegment(segment) {
  if (!segment) return;
  selectedId = segment.id;
  detail.innerHTML = `<strong>#${segment.rank} ${segment.id || 'segment'}</strong><br>
    Score: ${fmt(segment.score)} <span class="tag ${segment.band}">${segment.band}</span><br>
    Recommended action: ${segment.recommendation}<br>
    Area: ${segment.area || 'n/a'}<br>
    Road class: ${segment.road_class || 'n/a'}; land use: ${segment.land_use || 'n/a'}<br>
    Speed limit: ${fmt(segment.speed_limit)} km/h; V85: ${fmt(segment.v85_speed)} km/h<br>
    Speed variance: ${fmt(segment.speed_variance)} km/h<br>
    Speeding pressure: ${fmt(segment.speeding_pressure)}; VRU exposure: ${fmt(segment.vru_exposure)}`;
  document.querySelectorAll('.priority-item').forEach(button => {
    button.classList.toggle('active', button.dataset.id === selectedId);
  });
  draw();
}

function renderPriorityList() {
  const query = search.value.trim().toLowerCase();
  const items = MAP_DATA.top_priority
    .filter(segment => !query || `${segment.id} ${segment.area} ${segment.road_class}`.toLowerCase().includes(query))
    .slice(0, 30);
  priorityList.innerHTML = '';
  for (const segment of items) {
    const button = document.createElement('button');
    button.className = 'priority-item';
    button.dataset.id = segment.id;
    button.innerHTML = `<div class="priority-row"><strong>#${segment.rank} Score ${fmt(segment.score)}</strong><span class="tag ${segment.band}">${segment.band}</span></div>
      <div class="priority-id">${segment.id}</div>
      <div class="priority-row"><span>${segment.area || ''} / ${segment.road_class || ''}</span><span>${fmt(segment.speed_variance)} km/h</span></div>`;
    button.addEventListener('click', () => showSegment(segment));
    priorityList.appendChild(button);
  }
}

canvas.addEventListener('mousedown', event => {
  dragState = {
    x: event.clientX * devicePixelRatio,
    y: event.clientY * devicePixelRatio,
    moved: false,
  };
  canvas.classList.add('dragging');
});
canvas.addEventListener('mousemove', event => {
  if (dragState) {
    const x = event.clientX * devicePixelRatio;
    const y = event.clientY * devicePixelRatio;
    const dx = x - dragState.x;
    const dy = y - dragState.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) dragState.moved = true;
    view.offsetX += dx;
    view.offsetY += dy;
    dragState.x = x;
    dragState.y = y;
    draw();
    return;
  }
  const segment = nearestSegment(event);
  if (segment) showSegment(segment);
});
canvas.addEventListener('click', event => {
  if (suppressClick) return;
  const segment = nearestSegment(event);
  if (segment) showSegment(segment);
});
function stopDrag() {
  if (dragState?.moved) {
    suppressClick = true;
    setTimeout(() => {
      suppressClick = false;
    }, 0);
  }
  dragState = null;
  canvas.classList.remove('dragging');
}
canvas.addEventListener('mouseup', stopDrag);
canvas.addEventListener('mouseleave', stopDrag);
canvas.addEventListener('wheel', event => {
  event.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const centerX = (event.clientX - rect.left) * devicePixelRatio;
  const centerY = (event.clientY - rect.top) * devicePixelRatio;
  zoomBy(event.deltaY < 0 ? 1.18 : 0.85, centerX, centerY);
}, {passive: false});
document.getElementById('zoomIn').addEventListener('click', () => zoomBy(1.3));
document.getElementById('zoomOut').addEventListener('click', () => zoomBy(0.77));
document.getElementById('zoomReset').addEventListener('click', resetView);
for (const input of document.querySelectorAll('input[data-band]')) input.addEventListener('change', draw);
search.addEventListener('input', renderPriorityList);
document.getElementById('rendered').textContent = MAP_DATA.segments.length.toLocaleString();
document.getElementById('criticalCount').textContent = (RISK_COUNTS.Critical || 0).toLocaleString();
document.getElementById('moderateCount').textContent = (RISK_COUNTS.Moderate || 0).toLocaleString();
document.getElementById('lowCount').textContent = (RISK_COUNTS.Low || 0).toLocaleString();
renderPriorityList();
showSegment(MAP_DATA.top_priority[0]);
updateZoomLabel();
addEventListener('resize', resize);
resize();
</script>
</body>
</html>
"""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_priority_csv(path: Path, segments: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "rank",
        "id",
        "area",
        "road_class",
        "land_use",
        "score",
        "band",
        "speed_limit",
        "v85_speed",
        "speed_variance",
        "speeding_pressure",
        "vru_exposure",
        "recommendation",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for segment in segments:
            writer.writerow({field: segment.get(field) for field in fieldnames})


def render_index() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0; url=safety_score_map.html">
  <title>Geospatial Visualization</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; line-height: 1.5; color: #1f2933; }
    a { color: #245b8f; }
  </style>
</head>
<body>
  <h1>Geospatial Visualization</h1>
  <p>Redirecting to the interactive highest-priority speed review map.</p>
  <p><a href="safety_score_map.html">Open safety_score_map.html</a></p>
</body>
</html>
"""


def render_readme() -> str:
    return """# Geospatial Visualization

This folder contains the map-based output identifying the highest-priority road segments for speed-limit review or intervention.

## Working URLs

Open directly:

```text
file:///C:/Thoai/Road/data/processed/visualization/index.html
```

Or serve the workspace root:

```bash
python scripts/serve_visualization.py
```

Then open:

```text
http://127.0.0.1:8094/data/processed/visualization/
```

## Files

- `index.html`: landing page that redirects to the interactive map.
- `safety_score_map.html`: standalone interactive map with zoom, mouse-wheel zoom, pan, filters, and segment details.
- `highest_priority_segments.csv`: top 50 road segments ranked for review/intervention.
- `map_segments.json`: compact map data for the rendered priority network.
- `visualization_manifest.json`: metadata for the visualization output.
"""


def render_html(map_data: dict[str, Any], metrics: dict[str, Any] | None) -> str:
    risk_counts = (metrics or {}).get("risk_band_counts", {})
    return (
        HTML_TEMPLATE.replace(
            "__MAP_DATA__",
            json.dumps(map_data, ensure_ascii=False, separators=(",", ":")),
        )
        .replace(
            "__RISK_COUNTS__",
            json.dumps(risk_counts, ensure_ascii=False, separators=(",", ":")),
        )
    )


def run_visualization(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    outputs = config["outputs"]
    Path(outputs["visualization_dir"]).mkdir(parents=True, exist_ok=True)
    map_data = build_map_segments(config)
    metrics = None
    metrics_path = Path(config["metrics_json"])
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    write_json(Path(outputs["map_data_json"]), map_data)
    write_priority_csv(Path(outputs["priority_segments_csv"]), map_data["top_priority"])
    Path(outputs["index_html"]).write_text(render_index(), encoding="utf-8")
    Path(outputs["readme_md"]).write_text(render_readme(), encoding="utf-8")
    Path(outputs["map_html"]).write_text(render_html(map_data, metrics), encoding="utf-8")
    manifest = {
        "stage": "Interactive Geospatial Visualization",
        "generated_at": map_data["generated_at"],
        "outputs": outputs,
        "rendered_segments": len(map_data["segments"]),
        "top_priority_segments": len(map_data["top_priority"]),
        "bbox": map_data["bbox"],
        "submission_note": (
            "Map-based output identifying the highest-priority road segments "
            "for speed-limit review or intervention."
        ),
    }
    write_json(Path(outputs["manifest_json"]), manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an interactive priority map for speed review.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    run_visualization(args.config)


if __name__ == "__main__":
    main()
