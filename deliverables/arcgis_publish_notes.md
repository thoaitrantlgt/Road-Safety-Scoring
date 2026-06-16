# ArcGIS Publish Notes

## Interactive Geospatial Visualization

Interactive map output:

- `data/processed/visualization/index.html`

The map identifies the highest-priority road segments for speed-limit review or intervention. It includes risk-band filters, a top-priority segment list, hover/click details, and recommended intervention language.

Working local URL:

- `file:///C:/Thoai/Road/data/processed/visualization/index.html`

Optional HTTP URL if serving with `python scripts/serve_visualization.py`:

- `http://127.0.0.1:8094/data/processed/visualization/`

The companion priority table is:

- `data/processed/visualization/highest_priority_segments.csv`

Recommended layer:

- `data/processed/scoring/safety_scored_network.geojson`

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
