# Road Speed Safety Scoring

Pipeline for scoring road segments by speed-safety risk and prioritizing locations for speed-limit review or intervention.

This project builds an end-to-end geospatial workflow that standardizes road network inputs, engineers safe-system speed features, trains an interpretable scoring model, and exports policy-ready tables, GeoJSON, reports, and an interactive priority map.

## Problem

The goal is to evaluate the relative speed-safety risk of each road segment, not to predict crashes directly. The pipeline produces:

- `speed_safety_score`: 0-100 operational risk score.
- `risk_band`: `Low`, `Moderate`, or `Critical`.
- Ranked priority segments for speed-limit review or intervention.
- Interactive HTML map for inspecting high-priority corridors.

The current implementation does not use crash ground truth labels. Instead, it creates a policy-derived surrogate target from speed variance, speeding pressure, and vulnerable road user exposure.

## Pipeline

```text
raw road network inputs
  -> ETL and spatial alignment
  -> safe-system feature engineering
  -> policy-derived target and model scoring
  -> interactive geospatial visualization
  -> deliverable packaging
```

## Repository Structure

```text
configs/       JSON configuration for each pipeline stage
scripts/       ETL, feature engineering, scoring, visualization, packaging scripts
deliverables/  Markdown reports generated from pipeline outputs
plan.md        Project implementation plan and notes
```

Generated data and confidential source inputs are intentionally excluded from Git.

## Data Privacy

The repository is configured to ignore local source data and generated artifacts, including:

- `data/`
- raw `.geojson`, `.gpkg`, and spreadsheet inputs
- derived `.csv`, `.parquet`, and model files
- GIS sidecar files such as `.shp`, `.dbf`, `.shx`, and `.prj`

Do not commit raw road network data, processed outputs, model artifacts, credentials, or local exports.

## Main Stages

### 1. Alignment

Script:

```bash
python scripts/alignment.py --config configs/scope.json
```

Standardizes road inputs into a shared schema, filters target road classes, validates line geometries, and writes the aligned road network.

Main output:

```text
data/processed/alignment/road_network_aligned.geojson
```

### 2. Feature Engineering

Script:

```bash
python scripts/features.py --config configs/features.json
```

Creates safe-system features such as:

- `speed_variance_kmh`
- `sample_confidence`
- `speeding_pressure`
- `vru_exposure_index`
- `feature_quality_flag`

Main output:

```text
data/processed/features/features.parquet
```

### 3. Scoring

Script:

```bash
python scripts/scoring.py --config configs/scoring.json
```

Builds a policy-derived `risk_target`, trains a `HistGradientBoostingRegressor`, scores all road segments, and applies policy guardrails for clearly unsafe operating conditions.

Main outputs:

```text
data/processed/scoring/scored_segments.csv
data/processed/scoring/safety_scored_network.geojson
data/processed/scoring/model_metrics.json
```

### 4. Visualization

Script:

```bash
python scripts/visualization.py --config configs/visualization.json
```

Builds a standalone interactive HTML map with risk-band filters, pan/zoom, segment details, and top-priority review list.

Main output:

```text
data/processed/visualization/index.html
```

Optional local server:

```bash
python scripts/serve_visualization.py
```

Then open:

```text
http://127.0.0.1:8094/data/processed/visualization/
```

### 5. Deliverables

Script:

```bash
python scripts/package_outputs.py --config configs/package.json
```

Generates project-facing markdown reports:

```text
deliverables/executive_summary.md
deliverables/technical_report.md
deliverables/geospatial_visualization.md
deliverables/arcgis_publish_notes.md
```

## Run The Full Pipeline

```bash
python scripts/run_pipeline.py
```

Run from a later stage:

```bash
python scripts/run_pipeline.py --from-step scoring
```

## Model Notes

The scoring model is a scikit-learn pipeline:

```text
ColumnTransformer
  -> numeric passthrough
  -> categorical OneHotEncoder
  -> HistGradientBoostingRegressor
```

The model learns a policy-derived target rather than observed crash labels. Evaluation metrics therefore measure how well the model reproduces the scoring target and prioritization logic, not crash prediction accuracy.

## Requirements

The scripts are written in Python and use:

- `pandas`
- `numpy`
- `scikit-learn`

Parquet output requires a compatible parquet engine such as `pyarrow` or `fastparquet`.

## More Detail

See `scripts/README.md` for stage-by-stage commands and output paths.
