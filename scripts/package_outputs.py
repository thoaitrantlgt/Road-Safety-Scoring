from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("configs/package.json")


def read_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_executive_summary(context: dict[str, Any]) -> str:
    scoring = context["scoring"]
    features = context["features"]
    metrics = context["metrics"]
    risk_counts = metrics.get("risk_band_counts", {})
    cv = metrics.get("spatial_cross_validation", {})
    policy = metrics.get("policy_weighted_classification", {})
    return f"""# Executive Summary

The pipeline produces a policy-ready Speed Safety Score for {scoring.get("feature_count", 0):,} road segments across Thailand and Maharashtra.

## Key Outputs

| Item | Value |
| --- | --- |
| Total scored road segments | {scoring.get("feature_count", 0):,} |
| Trainable observed segments | {scoring.get("train_rows", 0):,} |
| Critical segments | {risk_counts.get("Critical", 0):,} |
| Moderate segments | {risk_counts.get("Moderate", 0):,} |
| Low-risk segments | {risk_counts.get("Low", 0):,} |
| Spatial CV MAE | {cv.get("mean_mae", "n/a")} |
| Spatial CV R2 | {cv.get("mean_r2", "n/a")} |
| Critical recall | {policy.get("critical_recall", "n/a")} |

The main feature table contains {features.get("feature_count", 0):,} rows and includes speed variance, speeding pressure, VRU exposure, feature quality, and final safety score fields.

The interactive map output is `data/processed/visualization/index.html`. It identifies the highest-priority road segments for speed-limit review or intervention and can be opened at `file:///C:/Thoai/Road/data/processed/visualization/index.html` during local review.
"""


def render_technical_report(context: dict[str, Any]) -> str:
    metrics = context["metrics"]
    feature_summary = context["feature_summary"]
    cv = metrics.get("spatial_cross_validation", {})
    policy = metrics.get("policy_weighted_classification", {})
    return f"""# Technical Report

## Pipeline

1. ETL and spatial alignment standardizes local road layers to a shared segment schema.
2. Feature engineering derives `speed_variance_kmh`, `speeding_pressure`, and `vru_exposure_index`.
3. Model scoring trains a gradient-boosted tree regressor using observed segments and scores all segments.
4. Visualization exports a standalone interactive HTML map identifying the highest-priority road segments for speed-limit review or intervention, plus a policy-ready scored GeoJSON.

## Target Definition

The current implementation uses a policy-derived surrogate target because direct crash labels are not present in the local input files. The target combines speed variance, speeding pressure, and VRU exposure, then applies a critical-segment guardrail for segments with clearly unsafe operating conditions.

## Feature Summary

```json
{json.dumps(feature_summary.get("numeric_summary", {}), ensure_ascii=False, indent=2)}
```

## Spatial Cross-Validation

```json
{json.dumps(cv, ensure_ascii=False, indent=2)}
```

## Policy-Weighted Critical Segment Evaluation

```json
{json.dumps(policy, ensure_ascii=False, indent=2)}
```

## Risk Band Definition

| Score | Band | Suggested action |
| --- | --- | --- |
| 0-45 | Low | Monitor under normal planning cycles. |
| 46-74 | Moderate | Review passive calming, monitoring, and speed-management options. |
| 75-100 | Critical | Prioritize immediate review and speed-management intervention. |
"""


def render_arcgis_notes(context: dict[str, Any]) -> str:
    scoring_outputs = context["scoring"].get("outputs", {})
    visualization_outputs = context["visualization"].get("outputs", {})
    return f"""# ArcGIS Publish Notes

## Interactive Geospatial Visualization

Interactive map output:

- `{visualization_outputs.get("index_html", "data/processed/visualization/index.html")}`

The map identifies the highest-priority road segments for speed-limit review or intervention. It includes risk-band filters, a top-priority segment list, hover/click details, and recommended intervention language.

Working local URL:

- `file:///C:/Thoai/Road/data/processed/visualization/index.html`

Optional HTTP URL if serving with `python scripts/serve_visualization.py`:

- `http://127.0.0.1:8094/data/processed/visualization/`

The companion priority table is:

- `{visualization_outputs.get("priority_segments_csv", "data/processed/visualization/highest_priority_segments.csv")}`

Recommended layer:

- `{scoring_outputs.get("scored_geojson", "data/processed/scoring/safety_scored_network.geojson")}`

Suggested symbology:

| Field | Rule |
| --- | --- |
| `risk_band` | Unique value renderer: Low = green, Moderate = orange, Critical = red. |
| `speed_safety_score` | Numeric 0-100 label or popup field. |
| `speed_variance_kmh` | Popup diagnostic field. |
| `speeding_pressure` | Popup diagnostic field. |
| `vru_exposure_index` | Popup diagnostic field. |

Recommended popup fields:

- `road_id`
- `source_area`
- `road_class`
- `land_use_norm`
- `speed_safety_score`
- `risk_band`
- `speed_variance_kmh`
- `speeding_pressure`
- `vru_exposure_index`
- `feature_quality_flag`

For large uploads, publish the GeoJSON as a hosted feature layer or convert it to GeoPackage/FileGDB in ArcGIS Pro.
"""


def render_geospatial_visualization(context: dict[str, Any]) -> str:
    visualization_outputs = context["visualization"].get("outputs", {})
    metrics = context["metrics"]
    risk_counts = metrics.get("risk_band_counts", {})
    return f"""# Geospatial Visualization

## Submission Requirement

A map-based output identifying the highest-priority road segments for speed-limit review or intervention. Interactive visualizations are strongly encouraged. If submitting an interactive map, provide a working URL.

## Interactive Map

Working local URL:

- `file:///C:/Thoai/Road/data/processed/visualization/index.html`

Optional HTTP URL if serving with `python scripts/serve_visualization.py`:

- `http://127.0.0.1:8094/data/processed/visualization/`

Standalone map file:

- `{visualization_outputs.get("map_html", "data/processed/visualization/safety_score_map.html")}`

Priority table:

- `{visualization_outputs.get("priority_segments_csv", "data/processed/visualization/highest_priority_segments.csv")}`

## What The Map Shows

- Critical and moderate road segments ranked by Speed Safety Score.
- Top-priority list with segment rank, score, road class, and diagnostic indicators.
- Zoom controls, mouse-wheel zoom, and pan for inspecting dense corridors.
- Hover/click details for speed variance, speeding pressure, VRU exposure, and recommended intervention.
- Risk-band filters for Critical, Moderate, and Low segments.

## Current Risk Band Counts

| Band | Segments |
| --- | ---: |
| Critical | {risk_counts.get("Critical", 0):,} |
| Moderate | {risk_counts.get("Moderate", 0):,} |
| Low | {risk_counts.get("Low", 0):,} |
"""


def run_packaging(config_path: Path) -> dict[str, Any]:
    config = read_json(config_path)
    inputs = config["inputs"]
    outputs = config["outputs"]
    context = {
        "alignment": read_json(inputs["alignment_manifest"]),
        "features": read_json(inputs["features_manifest"]),
        "scoring": read_json(inputs["scoring_manifest"]),
        "visualization": read_json(inputs["visualization_manifest"]),
        "metrics": read_json("data/processed/scoring/model_metrics.json"),
        "feature_summary": read_json("data/processed/features/feature_summary.json"),
    }
    write_text(Path(outputs["executive_summary_md"]), render_executive_summary(context))
    write_text(Path(outputs["technical_report_md"]), render_technical_report(context))
    write_text(Path(outputs["geospatial_visualization_md"]), render_geospatial_visualization(context))
    write_text(Path(outputs["arcgis_readme_md"]), render_arcgis_notes(context))
    manifest = {
        "stage": "Deliverable Packaging",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "outputs": outputs,
        "source_manifests": inputs,
    }
    write_text(Path(outputs["manifest_json"]), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build project deliverables from pipeline outputs.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    run_packaging(args.config)


if __name__ == "__main__":
    main()
