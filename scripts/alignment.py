from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("configs/scope.json")


def first_present(properties: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        value = properties.get(name)
        if value not in (None, ""):
            return value
    return None


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_road_class(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip().lower()


def geometry_type(geometry: dict[str, Any] | None) -> str | None:
    if not geometry:
        return None
    return geometry.get("type")


def geometry_has_coordinates(geometry: dict[str, Any] | None) -> bool:
    if not geometry:
        return False
    coordinates = geometry.get("coordinates")
    return bool(coordinates)


def geometry_bbox(geometry: dict[str, Any]) -> list[float] | None:
    coords: list[tuple[float, float]] = []

    def collect(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            coords.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, list):
            for item in value:
                collect(item)

    collect(geometry.get("coordinates"))
    if not coords:
        return None
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def merge_bbox(left: list[float] | None, right: list[float] | None) -> list[float] | None:
    if not left:
        return right
    if not right:
        return left
    return [
        min(left[0], right[0]),
        min(left[1], right[1]),
        max(left[2], right[2]),
        max(left[3], right[3]),
    ]


def normalize_feature(
    feature: dict[str, Any],
    area: str,
    source_file: str,
    feature_index: int,
    target_classes: set[str],
    quality_fields: list[str],
) -> tuple[dict[str, Any] | None, dict[str, int], list[float] | None]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry")
    road_class = normalize_road_class(first_present(properties, ["RoadClass", "class"]))
    stats: dict[str, int] = defaultdict(int)

    if road_class not in target_classes:
        stats["filtered_non_target_class"] += 1
        return None, stats, None

    gtype = geometry_type(geometry)
    if gtype not in {"LineString", "MultiLineString"} or not geometry_has_coordinates(geometry):
        stats["filtered_invalid_geometry"] += 1
        return None, stats, None

    raw_road_id = first_present(properties, ["OvertureID", "DISSOLVE_ID", "OBJECTID"])
    road_id = f"{area.lower()}:{raw_road_id or feature_index}"
    speed_limit = as_float(first_present(properties, ["SpeedLimit", "SpeedLimitFloor"]))
    median_speed = as_float(first_present(properties, ["MedianSpeed"]))
    v85_speed = as_float(first_present(properties, ["F85thPercentileSpeed", "V85"]))
    percent_over_limit = as_float(first_present(properties, ["PercentOverLimit", "Percent_"]))
    weighted_sample = as_float(first_present(properties, ["WeightedSample", "SampleSize_avg"]))
    sample_size_total = as_float(first_present(properties, ["SampleSizeTotal", "Sample_Size_Total"]))
    road_length_m = as_float(first_present(properties, ["Shape_Length", "RoadLength"]))

    normalized_properties = {
        "source_area": area,
        "source_file": source_file,
        "source_feature_index": feature_index,
        "source_crs": "EPSG:4326",
        "target_crs": "EPSG:4326",
        "road_id": road_id,
        "source_road_id": raw_road_id,
        "road_name": first_present(properties, ["english_ro", "names_primary"]),
        "road_class": road_class,
        "road_subtype": first_present(properties, ["subtype"]),
        "land_use": first_present(properties, ["LandUse"]),
        "urban_percent": as_float(first_present(properties, ["UrbanPC"])),
        "speed_limit_kmh": speed_limit,
        "median_speed_kmh": median_speed,
        "v85_speed_kmh": v85_speed,
        "percent_over_limit": percent_over_limit,
        "weighted_sample": weighted_sample,
        "sample_size_total": sample_size_total,
        "number_over_limit": as_float(first_present(properties, ["NumberOverLimit"])),
        "road_length_m": road_length_m,
        "analysis_status": first_present(properties, ["AnalysisStatus"]),
        "for_analysis": first_present(properties, ["ForAnalysis", "Pass"]),
        "exclude_from_speed_spi": first_present(properties, ["ExcludeFromSpeedSPI"]),
        "percentile_band": first_present(properties, ["PercentileBand"]),
        "ranked_percentile": as_float(first_present(properties, ["RankedPercentile"])),
        "street_image_link": first_present(properties, ["StreetImageLink"]),
        "geometry_type": gtype,
    }

    present_quality_count = sum(
        1 for field in quality_fields if normalized_properties.get(field) not in (None, "")
    )
    normalized_properties["alignment_confidence"] = round(
        present_quality_count / max(len(quality_fields), 1), 3
    )

    missing_quality_fields = [
        field for field in quality_fields if normalized_properties.get(field) in (None, "")
    ]
    if not missing_quality_fields:
        normalized_properties["spatial_alignment_status"] = "aligned"
    elif {"speed_limit_kmh", "median_speed_kmh", "v85_speed_kmh"}.issubset(
        set(missing_quality_fields)
    ):
        normalized_properties["spatial_alignment_status"] = "geometry_only"
    else:
        normalized_properties["spatial_alignment_status"] = "partial"
    normalized_properties["missing_alignment_fields"] = ",".join(missing_quality_fields)

    stats["kept_features"] += 1
    bbox = geometry_bbox(geometry)
    normalized_feature = {
        "type": "Feature",
        "id": road_id,
        "properties": normalized_properties,
        "geometry": geometry,
    }
    return normalized_feature, stats, bbox


def inspect_gpkg(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    report: dict[str, Any] = {"path": str(path), "exists": True}
    try:
        with sqlite3.connect(path) as connection:
            report["contents"] = [
                {
                    "table_name": row[0],
                    "data_type": row[1],
                    "identifier": row[2],
                    "srs_id": row[3],
                }
                for row in connection.execute(
                    "select table_name, data_type, identifier, srs_id from gpkg_contents"
                ).fetchall()
            ]
            report["geometry_columns"] = [
                {
                    "table_name": row[0],
                    "column_name": row[1],
                    "geometry_type": row[2],
                    "srs_id": row[3],
                }
                for row in connection.execute(
                    "select table_name, column_name, geometry_type_name, srs_id "
                    "from gpkg_geometry_columns"
                ).fetchall()
            ]
    except sqlite3.Error as exc:
        report["error"] = str(exc)
    return report


def load_geojson(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any], *, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        if pretty:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))
        file.write("\n")


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source_area",
        "total_input_features",
        "kept_features",
        "filtered_non_target_class",
        "filtered_invalid_geometry",
        "aligned",
        "partial",
        "geometry_only",
        "motorway",
        "trunk",
        "primary",
        "secondary",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, 0) for field in fieldnames})


def run_alignment(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    target_classes = {item.lower() for item in config["target_road_classes"]}
    quality_fields = config["alignment_quality_fields"]
    all_features: list[dict[str, Any]] = []
    source_reports: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    global_bbox: list[float] | None = None

    for source in config["inputs"]:
        area = source["area"]
        geojson_path = Path(source["road_geojson"])
        data = load_geojson(geojson_path)
        features = data.get("features", [])
        source_counter: Counter[str] = Counter()
        class_counter: Counter[str] = Counter()
        status_counter: Counter[str] = Counter()
        source_bbox: list[float] | None = None

        for index, feature in enumerate(features, start=1):
            normalized, stats, bbox = normalize_feature(
                feature=feature,
                area=area,
                source_file=str(geojson_path),
                feature_index=index,
                target_classes=target_classes,
                quality_fields=quality_fields,
            )
            source_counter.update(stats)
            if normalized is None:
                continue
            props = normalized["properties"]
            class_counter.update([props["road_class"]])
            status_counter.update([props["spatial_alignment_status"]])
            all_features.append(normalized)
            source_bbox = merge_bbox(source_bbox, bbox)
            global_bbox = merge_bbox(global_bbox, bbox)

        gpkg_report = inspect_gpkg(Path(source["source_gpkg"]))
        source_report = {
            "area": area,
            "road_geojson": str(geojson_path),
            "top_level_type": data.get("type"),
            "input_feature_count": len(features),
            "kept_feature_count": source_counter["kept_features"],
            "road_class_counts": dict(sorted(class_counter.items())),
            "alignment_status_counts": dict(sorted(status_counter.items())),
            "filtered_counts": {
                "non_target_class": source_counter["filtered_non_target_class"],
                "invalid_geometry": source_counter["filtered_invalid_geometry"],
            },
            "bbox": source_bbox,
            "gpkg_metadata": gpkg_report,
        }
        source_reports.append(source_report)
        summary_rows.append(
            {
                "source_area": area,
                "total_input_features": len(features),
                "kept_features": source_counter["kept_features"],
                "filtered_non_target_class": source_counter["filtered_non_target_class"],
                "filtered_invalid_geometry": source_counter["filtered_invalid_geometry"],
                **dict(status_counter),
                **dict(class_counter),
            }
        )

    output_geojson = {
        "type": "FeatureCollection",
        "name": "road_network_aligned",
        "crs": {
            "type": "name",
            "properties": {"name": config["target_crs"]},
        },
        "bbox": global_bbox,
        "features": all_features,
    }
    output_paths = config["outputs"]
    write_json(Path(output_paths["aligned_geojson"]), output_geojson, pretty=False)
    write_summary_csv(Path(output_paths["summary_csv"]), summary_rows)

    schema_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "feature_count": len(all_features),
        "bbox": global_bbox,
        "sources": source_reports,
        "canonical_fields": sorted(all_features[0]["properties"].keys()) if all_features else [],
    }
    write_json(Path(output_paths["schema_report_json"]), schema_report)

    manifest = {
        "stage": "ETL & Spatial Alignment",
        "generated_at": schema_report["generated_at"],
        "outputs": output_paths,
        "total_aligned_features": len(all_features),
        "target_crs": config["target_crs"],
        "target_road_classes": sorted(target_classes),
    }
    write_json(Path(output_paths["manifest_json"]), manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ETL and spatial alignment for road safety inputs."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the alignment JSON config.",
    )
    args = parser.parse_args()
    manifest = run_alignment(args.config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
