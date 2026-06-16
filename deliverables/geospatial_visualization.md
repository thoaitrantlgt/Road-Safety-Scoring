# Geospatial Visualization

## Submission Requirement

A map-based output identifying the highest-priority road segments for speed-limit review or intervention. Interactive visualizations are strongly encouraged. If submitting an interactive map, provide a working URL.

## Interactive Map

Working local URL:

- `file:///C:/Thoai/Road/data/processed/visualization/index.html`

Optional HTTP URL if serving with `python scripts/serve_visualization.py`:

- `http://127.0.0.1:8094/data/processed/visualization/`

Standalone map file:

- `data/processed/visualization/safety_score_map.html`

Priority table:

- `data/processed/visualization/highest_priority_segments.csv`

## What The Map Shows

- Critical and moderate road segments ranked by Speed Safety Score.
- Top-priority list with segment rank, score, road class, and diagnostic indicators.
- Zoom controls, mouse-wheel zoom, and pan for inspecting dense corridors.
- Hover/click details for speed variance, speeding pressure, VRU exposure, and recommended intervention.
- Risk-band filters for Critical, Moderate, and Low segments.

## Current Risk Band Counts

| Band | Segments |
| --- | ---: |
| Critical | 659 |
| Moderate | 9,954 |
| Low | 59,353 |
