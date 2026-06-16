from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd


DEFAULT_CONFIG = Path("configs/features.json")


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def percentile(values: list[float], percentile_value: float) -> float | None:
    cleaned = sorted(value for value in values if value is not None and value >= 0)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    position = (len(cleaned) - 1) * (percentile_value / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return cleaned[int(position)]
    weight = position - lower
    return cleaned[lower] * (1 - weight) + cleaned[upper] * weight


def normalized_land_use(value: Any) -> str:
    if value in (None, ""):
        return "unknown"
    text = str(value).strip().lower()
    if "urban" in text:
        return "urban"
    if "suburban" in text:
        return "suburban"
    if "mixed" in text:
        return "mixed"
    if "rural" in text:
        return "rural"
    return "unknown"


def speed_variance(v85: float | None, median: float | None) -> float | None:
    if v85 is None or median is None:
        return None
    if v85 <= 0 and median <= 0:
        return None
    return round(max(v85 - median, 0.0), 3)


def sample_confidence(sample: float | None, p95_sample: float | None) -> float:
    if sample is None or sample <= 0 or p95_sample is None or p95_sample <= 0:
        return 0.0
    return round(clamp(math.log1p(sample) / math.log1p(p95_sample), 0.0, 1.0), 4)


def percent_to_100(value: float | None) -> float | None:
    if value is None:
        return None
    if 0.0 <= value <= 1.0:
        return value * 100.0
    return value


def speeding_pressure(
    percent_over_limit: float | None,
    weighted_sample: float | None,
    p95_sample: float | None,
    output_scale: float,
) -> float | None:
    percent_100 = percent_to_100(percent_over_limit)
    if percent_100 is None:
        return None
    percent = clamp(percent_100, 0.0, output_scale)
    confidence = sample_confidence(weighted_sample, p95_sample)
    return round(percent * confidence, 3)


def urban_percent_norm(value: float | None, land_use_key: str) -> float:
    if value is not None:
        if value > 1:
            return clamp(value / 100.0, 0.0, 1.0)
        return clamp(value, 0.0, 1.0)
    if land_use_key == "urban":
        return 1.0
    if land_use_key == "suburban":
        return 0.65
    if land_use_key == "rural":
        return 0.2
    return 0.45


def vru_exposure_index(
    road_class: str | None,
    land_use: str,
    urban_percent: float | None,
    config: dict[str, Any],
) -> float:
    vru_config = config["vru_exposure"]
    road_weights = vru_config["road_class_weights"]
    land_weights = vru_config["land_use_weights"]
    road_weight = road_weights.get((road_class or "").lower(), 0.45)
    land_use_key = normalized_land_use(land_use)
    land_weight = land_weights.get(land_use_key, land_weights["unknown"])
    urban_weight = urban_percent_norm(urban_percent, land_use_key)
    score = 100.0 * (
        vru_config["road_class_weight"] * road_weight
        + vru_config["land_use_weight"] * land_weight
        + vru_config["urban_percent_weight"] * urban_weight
    )
    return round(clamp(score, 0.0, 100.0), 3)


def completeness_score(row: dict[str, Any], required_fields: list[str]) -> float:
    present = sum(1 for field in required_fields if row.get(field) not in (None, ""))
    return round(present / max(len(required_fields), 1), 3)


def quality_flag(row: dict[str, Any], config: dict[str, Any]) -> str:
    minimum_weighted = config["quality"]["minimum_weighted_sample"]
    minimum_total = config["quality"]["minimum_sample_size_total"]
    if row["spatial_alignment_status"] == "geometry_only":
        return "geometry_only"
    if row["weighted_sample"] is not None and row["weighted_sample"] < minimum_weighted:
        return "low_sample"
    if row["sample_size_total"] is not None and row["sample_size_total"] < minimum_total:
        return "low_sample"
    if row["feature_completeness"] < 0.6:
        return "partial_features"
    return "usable"


def build_feature_rows(features: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    weighted_samples = [
        as_float((feature.get("properties") or {}).get("weighted_sample"))
        for feature in features
    ]
    p95_sample = percentile([value for value in weighted_samples if value is not None], config["speeding_pressure"]["sample_weight_percentile"])
    required_fields = [
        "road_class",
        "road_length_m",
        "speed_limit_kmh",
        "median_speed_kmh",
        "v85_speed_kmh",
        "percent_over_limit",
        "weighted_sample",
        "land_use",
    ]
    rows: list[dict[str, Any]] = []

    for feature in features:
        props = feature.get("properties") or {}
        road_class = props.get("road_class")
        land_use = props.get("land_use")
        median = as_float(props.get("median_speed_kmh"))
        v85 = as_float(props.get("v85_speed_kmh"))
        weighted_sample = as_float(props.get("weighted_sample"))
        row = {
            "road_id": props.get("road_id"),
            "source_area": props.get("source_area"),
            "source_feature_index": props.get("source_feature_index"),
            "road_name": props.get("road_name"),
            "road_class": road_class,
            "land_use": land_use,
            "land_use_norm": normalized_land_use(land_use),
            "urban_percent": as_float(props.get("urban_percent")),
            "road_length_m": as_float(props.get("road_length_m")),
            "speed_limit_kmh": as_float(props.get("speed_limit_kmh")),
            "median_speed_kmh": median,
            "v85_speed_kmh": v85,
            "percent_over_limit": as_float(props.get("percent_over_limit")),
            "weighted_sample": weighted_sample,
            "sample_size_total": as_float(props.get("sample_size_total")),
            "number_over_limit": as_float(props.get("number_over_limit")),
            "analysis_status": props.get("analysis_status"),
            "spatial_alignment_status": props.get("spatial_alignment_status"),
            "alignment_confidence": as_float(props.get("alignment_confidence")),
            "speed_variance_kmh": speed_variance(v85, median),
        }
        row["sample_confidence"] = sample_confidence(weighted_sample, p95_sample)
        row["speeding_pressure"] = speeding_pressure(
            row["percent_over_limit"],
            weighted_sample,
            p95_sample,
            config["speeding_pressure"]["output_scale"],
        )
        row["vru_exposure_index"] = vru_exposure_index(
            road_class=road_class,
            land_use=land_use,
            urban_percent=row["urban_percent"],
            config=config,
        )
        row["feature_completeness"] = completeness_score(row, required_fields)
        row["feature_quality_flag"] = quality_flag(row, config)
        row["has_speed_observation"] = row["speed_variance_kmh"] is not None
        row["has_speed_limit"] = row["speed_limit_kmh"] is not None
        rows.append(row)
    return rows


def enrich_geojson(
    features: list[dict[str, Any]],
    rows_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    enriched_features = []
    feature_fields = {
        "land_use_norm",
        "speed_variance_kmh",
        "sample_confidence",
        "speeding_pressure",
        "vru_exposure_index",
        "feature_completeness",
        "feature_quality_flag",
        "has_speed_observation",
        "has_speed_limit",
    }
    for feature in features:
        props = feature.get("properties") or {}
        road_id = props.get("road_id")
        row = rows_by_id.get(road_id, {})
        enriched_props = dict(props)
        for field in feature_fields:
            enriched_props[field] = row.get(field)
        enriched_features.append(
            {
                "type": "Feature",
                "id": road_id,
                "properties": enriched_props,
                "geometry": feature.get("geometry"),
            }
        )
    return {"type": "FeatureCollection", "name": "road_network_features", "features": enriched_features}


def write_json(path: Path, payload: dict[str, Any], *, pretty: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        if pretty:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))
        file.write("\n")


def write_data_dictionary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = """# Feature Data Dictionary

| Field | Meaning |
| --- | --- |
| `speed_variance_kmh` | `max(F85thPercentileSpeed - MedianSpeed, 0)`. Null when either speed value is missing or both are zero. |
| `sample_confidence` | Log-scaled confidence from `WeightedSample`, capped at the 95th percentile sample size. |
| `speeding_pressure` | `PercentOverLimit` normalized to a 0-100 percent scale, then multiplied by `sample_confidence`. |
| `vru_exposure_index` | 0-100 rule-based exposure proxy combining road class, land use, and urban percentage. Higher means stronger vulnerable road user exposure. |
| `feature_completeness` | Share of required feature fields present for the segment. |
| `feature_quality_flag` | `usable`, `low_sample`, `partial_features`, or `geometry_only`. |
| `has_speed_observation` | True when `speed_variance_kmh` can be computed. |
| `has_speed_limit` | True when `speed_limit_kmh` is present. |
"""
    path.write_text(content, encoding="utf-8")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = {
        "source_area": Counter(),
        "road_class": Counter(),
        "quality_flag": Counter(),
        "alignment_status": Counter(),
    }
    numeric_fields = [
        "speed_variance_kmh",
        "speeding_pressure",
        "vru_exposure_index",
        "feature_completeness",
        "sample_confidence",
    ]
    numeric_summary: dict[str, dict[str, float | int | None]] = {}
    for row in rows:
        counters["source_area"].update([str(row.get("source_area"))])
        counters["road_class"].update([str(row.get("road_class"))])
        counters["quality_flag"].update([str(row.get("feature_quality_flag"))])
        counters["alignment_status"].update([str(row.get("spatial_alignment_status"))])

    for field in numeric_fields:
        values = [row[field] for row in rows if row.get(field) is not None]
        numeric_summary[field] = {
            "count": len(values),
            "mean": round(mean(values), 4) if values else None,
            "min": round(min(values), 4) if values else None,
            "max": round(max(values), 4) if values else None,
        }

    return {
        "row_count": len(rows),
        "counts": {key: dict(counter) for key, counter in counters.items()},
        "numeric_summary": numeric_summary,
    }


def run_features(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    input_geojson = Path(config["input_geojson"])
    with input_geojson.open("r", encoding="utf-8") as file:
        geojson = json.load(file)
    features = geojson.get("features", [])
    rows = build_feature_rows(features, config)
    rows_by_id = {row["road_id"]: row for row in rows}

    outputs = config["outputs"]
    Path(outputs["features_dir"]).mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame(rows)
    dataframe.to_csv(outputs["features_csv"], index=False, quoting=csv.QUOTE_MINIMAL)
    dataframe.to_parquet(outputs["features_parquet"], index=False)

    feature_geojson = enrich_geojson(features, rows_by_id)
    feature_geojson["crs"] = geojson.get("crs")
    feature_geojson["bbox"] = geojson.get("bbox")
    write_json(Path(outputs["feature_geojson"]), feature_geojson, pretty=False)
    write_data_dictionary(Path(outputs["data_dictionary_md"]))

    summary = summarize(rows)
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    summary["input_geojson"] = str(input_geojson)
    summary["formulas"] = {
        "speed_variance_kmh": "max(v85_speed_kmh - median_speed_kmh, 0)",
        "sample_confidence": "log1p(weighted_sample) / log1p(p95_weighted_sample), clipped to 0-1",
        "speeding_pressure": "percent_over_limit normalized to 0-100 * sample_confidence",
        "vru_exposure_index": "100 * weighted combination of road_class, land_use, and urban_percent",
    }
    write_json(Path(outputs["summary_json"]), summary)

    manifest = {
        "stage": "Safe System Feature Engineering",
        "generated_at": summary["generated_at"],
        "input_geojson": str(input_geojson),
        "outputs": outputs,
        "feature_count": len(rows),
        "core_features": [
            "speed_variance_kmh",
            "speeding_pressure",
            "vru_exposure_index",
            "feature_quality_flag",
        ],
    }
    write_json(Path(outputs["manifest_json"]), manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run safe-system feature engineering.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    manifest = run_features(args.config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
