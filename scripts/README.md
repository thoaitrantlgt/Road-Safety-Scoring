# Road Safety Pipeline Scripts

Run the full pipeline:

```bash
python scripts/run_pipeline.py
```

Run from a later step:

```bash
python scripts/run_pipeline.py --from-step scoring
```

## Alignment

```bash
python scripts/alignment.py --config configs/scope.json
```

Outputs:

- `data/processed/alignment/road_network_aligned.geojson`
- `data/processed/alignment/road_network_aligned_summary.csv`
- `data/processed/alignment/schema_report.json`
- `data/processed/alignment/alignment_manifest.json`

## Feature Engineering

```bash
python scripts/features.py --config configs/features.json
```

Outputs:

- `data/processed/features/features.csv`
- `data/processed/features/features.parquet`
- `data/processed/features/road_network_features.geojson`
- `data/processed/features/feature_summary.json`
- `data/processed/features/data_dictionary.md`
- `data/processed/features/features_manifest.json`

## Scoring

```bash
python scripts/scoring.py --config configs/scoring.json
```

Outputs:

- `data/processed/scoring/scored_segments.csv`
- `data/processed/scoring/scored_segments.parquet`
- `data/processed/scoring/safety_scored_network.geojson`
- `data/processed/scoring/model_metrics.json`
- `data/processed/scoring/feature_importance.csv`
- `data/processed/scoring/critical_segments.csv`
- `data/processed/scoring/safety_model.pkl`
- `data/processed/scoring/scoring_manifest.json`

## Visualization

```bash
python scripts/visualization.py --config configs/visualization.json
```

Outputs:

- `data/processed/visualization/index.html`
- `data/processed/visualization/README.md`
- `data/processed/visualization/safety_score_map.html`
- `data/processed/visualization/map_segments.json`
- `data/processed/visualization/highest_priority_segments.csv`
- `data/processed/visualization/visualization_manifest.json`

Working local URL:

```text
file:///C:/Thoai/Road/data/processed/visualization/index.html
```

Optional HTTP server:

```bash
python scripts/serve_visualization.py
```

Then open:

```text
http://127.0.0.1:8094/data/processed/visualization/
```

## Deliverables

```bash
python scripts/package_outputs.py --config configs/package.json
```

Outputs:

- `deliverables/executive_summary.md`
- `deliverables/technical_report.md`
- `deliverables/geospatial_visualization.md`
- `deliverables/arcgis_publish_notes.md`
- `deliverables/deliverables_manifest.json`
