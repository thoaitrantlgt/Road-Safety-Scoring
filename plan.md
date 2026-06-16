# Speed Safety Score Pipeline Plan

## Muc tieu

Xay dung pipeline tu du lieu road network hien co thanh bo diem **Speed Safety Score 0-100** cho tung road segment, co giai thich, co danh gia robustness, co ban do tuong tac va goi deliverables de dua vao ArcGIS/bao cao.

## Kien truc da hien thuc

| Buoc | Script | Config | Output chinh |
| --- | --- | --- | --- |
| ETL va spatial alignment | `scripts/alignment.py` | `configs/scope.json` | `data/processed/alignment/road_network_aligned.geojson` |
| Feature engineering | `scripts/features.py` | `configs/features.json` | `data/processed/features/features.parquet` |
| ML scoring | `scripts/scoring.py` | `configs/scoring.json` | `data/processed/scoring/scored_segments.parquet` |
| Visualization | `scripts/visualization.py` | `configs/visualization.json` | `data/processed/visualization/index.html` |
| Deliverables | `scripts/package_outputs.py` | `configs/package.json` | `deliverables/` |

Chay toan bo pipeline:

```bash
python scripts/run_pipeline.py
```

Chay lai tu buoc scoring:

```bash
python scripts/run_pipeline.py --from-step scoring
```

## Bang ke hoach chi tiet

| Buoc | Muc tieu | Cong viec da hien thuc | Dau vao | Dau ra | Tieu chi hoan thanh |
| --- | --- | --- | --- | --- | --- |
| 1.1. Xac dinh pham vi du lieu | Chot khu vuc va loai duong can phan tich | Cau hinh Thailand va Maharashtra, loc `motorway`, `trunk`, `primary`, `secondary`, target CRS `EPSG:4326` | `ADB_Innovation_Thailand.geojson`, `ADB_Innovation_Maharashtra.geojson` | `configs/scope.json` | Pham vi tai lap duoc bang config |
| 1.2. Nap road layers | Tao road network base layer | Doc hai GeoJSON, kiem tra GPKG metadata, loai geometry khong hop le | GeoJSON/GPKG local | Road features trong memory | Doc duoc 69,966 road segments |
| 1.3. Chuan hoa schema | Tao schema chung cho cac vung | Chuan hoa `road_id`, `road_class`, speed fields, land use, sample fields, geometry type | Raw properties | `road_network_aligned.geojson` | Co schema chung va CRS metadata |
| 1.4. Alignment quality | Danh dau muc do day du cua tung segment | Gan `spatial_alignment_status`, `alignment_confidence`, `missing_alignment_fields` | Road features da chuan hoa | `schema_report.json`, `road_network_aligned_summary.csv` | Co thong ke `aligned`, `partial`, `geometry_only` |
| 2.1. Speed variance | Do bien dong toc do tren segment | Tinh `speed_variance_kmh = max(v85_speed_kmh - median_speed_kmh, 0)` | `v85_speed_kmh`, `median_speed_kmh` | `features.parquet` | 15,143 segment co speed variance |
| 2.2. Speeding pressure | Do ap luc vuot toc do co trong so | Chuan hoa `percent_over_limit` ve 0-100 va nhan `sample_confidence` tu `weighted_sample` | `percent_over_limit`, `weighted_sample` | `speeding_pressure` | Chi so nam trong 0-100 |
| 2.3. VRU exposure | Uoc tinh phoi nhiem cua nguoi tham gia giao thong de ton thuong | Ket hop `road_class`, `land_use_norm`, `urban_percent` bang rule-based weights | Road class, land use, urban proxy | `vru_exposure_index` | Chi so nam trong 22.5-93.25 |
| 2.4. Feature table | Tao bang dac trung cho model | Xuat CSV, Parquet, GeoJSON da enrich, data dictionary va summary | Alignment output | `data/processed/features/` | 69,966 rows, 15,499 usable |
| 3.1. Risk target | Tao target co y nghia chinh sach | Tao `risk_target` tu speed variance, speeding pressure, VRU exposure va critical label | Feature table | `risk_target`, `critical_label` | Target nam trong 0-100 |
| 3.2. Baseline va spatial CV | Danh gia dung cach theo khong gian | Dung grouped split theo area va index block; so sanh voi median baseline | Trainable features | `model_metrics.json` | Co MAE/R2 theo fold va baseline |
| 3.3. Gradient-boosted model | Score operational risk cho tat ca segments | Train `HistGradientBoostingRegressor`, luu model pickle, predict all segments | Trainable feature rows | `safety_model.pkl`, `scored_segments.parquet` | 69,966 segments duoc score |
| 3.4. Interpretability | Giai thich driver cua model | Tinh permutation importance tren validation split | Model + feature matrix | `feature_importance.csv` | Co ranking feature importance |
| 3.5. Speed Safety Score | Tao diem 0-100 va risk band | Gan `speed_safety_score`, `risk_band`, policy guardrail floor cho truong hop critical ro rang | Prediction + policy rules | `safety_scored_network.geojson` | Critical recall 99.1% |
| 4.1. GIS layer | Tao lop ban do policy-ready | Join score vao geometry va xuat scored GeoJSON | Feature GeoJSON + score table | `safety_scored_network.geojson` | Mo duoc bang GIS/web tooling |
| 4.2. Interactive map | Tao demo tuong tac khong can dependency ngoai | Tao HTML canvas map, filter risk band, zoom/pan, hover detail, render 18,000 segments uu tien | Scored GeoJSON | `index.html`, `safety_score_map.html` | Mo landing page hoac map HTML la xem duoc |
| 4.3. ArcGIS handoff | Chuan bi publish workflow | Tao ArcGIS publish notes voi symbology va popup fields | Scored GeoJSON | `arcgis_publish_notes.md` | Co huong dan publish layer |
| 5.1. Spatial evaluation | Kiem tra tong quat hoa theo khong gian | GroupKFold theo area/index block | Trainable features | Spatial CV metrics | Mean MAE 0.254, mean R2 0.9985 |
| 5.2. Policy-weighted evaluation | Uu tien khong bo sot segment nguy hiem | Tinh confusion matrix va critical recall | Critical labels + score | `model_metrics.json` | Critical recall 99.1%, false negative 6 |
| 5.3. Scalability note | Ho tro vung thieu telemetry | Duy tri `geometry_only` va `feature_quality_flag` de scoring/flag ro rang | Full feature table | Quality counts | Khong mat segment khi thieu speed data |
| 6.1. Deliverables | Dong goi ket qua | Tao executive summary, technical report, publish notes va manifest | Tat ca manifest/metrics | `deliverables/` | Bao cao va file publish san sang dung |

## Ket qua hien tai

| Metric | Gia tri |
| --- | --- |
| Tong road segments | 69,966 |
| Trainable observed rows | 15,606 |
| Usable feature rows | 15,499 |
| Critical segments | 659 |
| Moderate segments | 9,954 |
| Low-risk segments | 59,353 |
| Critical recall | 99.1% |
| Critical precision | 98.6% |
| Spatial CV mean MAE | 0.254 |
| Spatial CV mean R2 | 0.9985 |

## Output quan trong

| File | Vai tro |
| --- | --- |
| `data/processed/alignment/schema_report.json` | Bao cao schema va metadata nguon |
| `data/processed/features/data_dictionary.md` | Tu dien du lieu cho feature table |
| `data/processed/scoring/model_metrics.json` | Metrics model, spatial CV, confusion matrix |
| `data/processed/scoring/feature_importance.csv` | Feature importance de giai thich model |
| `data/processed/scoring/critical_segments.csv` | Top critical segments can uu tien review |
| `data/processed/scoring/safety_scored_network.geojson` | Lop GIS chinh de publish |
| `data/processed/visualization/index.html` | Landing page cho working URL cua ban do tuong tac |
| `data/processed/visualization/safety_score_map.html` | Ban do tuong tac tu chua |
| `data/processed/visualization/highest_priority_segments.csv` | Bang 50 road segments uu tien cao nhat cho speed-limit review/intervention |
| `deliverables/executive_summary.md` | Tom tat dieu hanh |
| `deliverables/technical_report.md` | Bao cao ky thuat |
| `deliverables/geospatial_visualization.md` | Mo ta output ban do va working URL |
| `deliverables/arcgis_publish_notes.md` | Ghi chu publish len ArcGIS |

## Ghi chu ky thuat

- Moi file script/config/output moi da duoc dat ten theo chuc nang, khong dung ten theo giai doan.
- Moi truong hien tai khong co `geopandas`, `shapely`, `fiona`, `pyogrio`, `xgboost`, `shap`, `folium`, nen pipeline dung Python standard library, `pandas`, `pyarrow`, va `scikit-learn`.
- `risk_target` la policy-derived surrogate target duoc tao tu cac proxy an toan hien co, phu hop khi chua co crash labels truc tiep.
- Ban do HTML khong can server; co the mo truc tiep `file:///C:/Thoai/Road/data/processed/visualization/index.html`.
