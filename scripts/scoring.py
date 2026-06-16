from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    confusion_matrix,
    mean_absolute_error,
    precision_recall_fscore_support,
    r2_score,
    recall_score,
)
from sklearn.model_selection import GroupKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


DEFAULT_CONFIG = Path("configs/scoring.json")


NUMERIC_FEATURES = [
    "road_length_m",
    "speed_limit_kmh",
    "median_speed_kmh",
    "v85_speed_kmh",
    "speed_variance_kmh",
    "speeding_pressure",
    "vru_exposure_index",
    "sample_confidence",
    "feature_completeness",
    "alignment_confidence",
    "urban_percent",
]
CATEGORICAL_FEATURES = [
    "source_area",
    "road_class",
    "land_use_norm",
    "feature_quality_flag",
    "spatial_alignment_status",
]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def clamp_series(series: pd.Series, low: float, high: float) -> pd.Series:
    return series.clip(lower=low, upper=high)


def safe_percentile(series: pd.Series, value: float, fallback: float) -> float:
    cleaned = series.dropna()
    if cleaned.empty:
        return fallback
    result = float(np.percentile(cleaned, value))
    if not math.isfinite(result) or result <= 0:
        return fallback
    return result


def build_target(dataframe: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    target_config = config["target"]
    frame = dataframe.copy()
    p95_variance = safe_percentile(frame["speed_variance_kmh"], 95, 1.0)
    speed_variance_component = clamp_series(frame["speed_variance_kmh"].fillna(0) / p95_variance, 0, 1) * 100
    speeding_pressure_component = clamp_series(frame["speeding_pressure"].fillna(0), 0, 100)
    vru_component = clamp_series(frame["vru_exposure_index"].fillna(0), 0, 100)
    frame["risk_target"] = (
        target_config["speed_variance_weight"] * speed_variance_component
        + target_config["speeding_pressure_weight"] * speeding_pressure_component
        + target_config["vru_exposure_weight"] * vru_component
    ).round(3)
    frame["critical_label"] = (
        (frame["risk_target"] >= target_config["critical_threshold"])
        | (
            (frame["speed_variance_kmh"].fillna(0) >= 25)
            & (frame["vru_exposure_index"].fillna(0) >= 70)
        )
        | (frame["speeding_pressure"].fillna(0) >= 70)
    )
    frame["moderate_label"] = frame["risk_target"] >= target_config["moderate_threshold"]
    return frame


def prepare_model_frame(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    trainable = dataframe[
        dataframe["feature_quality_flag"].isin(["usable", "low_sample", "partial_features"])
        & dataframe["risk_target"].notna()
    ].copy()
    groups = (
        trainable["source_area"].astype(str)
        + "_"
        + (trainable["source_feature_index"].fillna(0).astype(int) // 1000).astype(str)
    )
    return trainable[MODEL_FEATURES], trainable["risk_target"], groups


def make_pipeline(config: dict[str, Any]) -> Pipeline:
    model_config = config["model"]
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", "passthrough", NUMERIC_FEATURES),
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    model = HistGradientBoostingRegressor(
        random_state=model_config["random_state"],
        max_iter=model_config["max_iter"],
        learning_rate=model_config["learning_rate"],
        max_leaf_nodes=model_config["max_leaf_nodes"],
        l2_regularization=model_config["l2_regularization"],
    )
    return Pipeline([("preprocess", preprocessor), ("model", model)])


def evaluate_spatial_cv(
    X: pd.DataFrame,
    y: pd.Series,
    groups: pd.Series,
    config: dict[str, Any],
) -> dict[str, Any]:
    unique_groups = groups.nunique()
    splits = max(2, min(config["evaluation"]["max_cv_splits"], unique_groups))
    group_kfold = GroupKFold(n_splits=splits)
    rows: list[dict[str, float | int]] = []
    for fold, (train_index, test_index) in enumerate(group_kfold.split(X, y, groups), start=1):
        pipeline = make_pipeline(config)
        baseline = DummyRegressor(strategy="median")
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]
        pipeline.fit(X_train, y_train)
        baseline.fit(X_train, y_train)
        prediction = pipeline.predict(X_test)
        baseline_prediction = baseline.predict(X_test)
        rows.append(
            {
                "fold": fold,
                "rows": int(len(test_index)),
                "mae": float(mean_absolute_error(y_test, prediction)),
                "r2": float(r2_score(y_test, prediction)),
                "baseline_mae": float(mean_absolute_error(y_test, baseline_prediction)),
                "baseline_r2": float(r2_score(y_test, baseline_prediction)),
            }
        )
    return {
        "n_splits": splits,
        "folds": rows,
        "mean_mae": float(np.mean([row["mae"] for row in rows])),
        "mean_r2": float(np.mean([row["r2"] for row in rows])),
        "mean_baseline_mae": float(np.mean([row["baseline_mae"] for row in rows])),
        "mean_baseline_r2": float(np.mean([row["baseline_r2"] for row in rows])),
    }


def risk_band(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 46:
        return "Moderate"
    return "Low"


def score_all_segments(dataframe: pd.DataFrame, pipeline: Pipeline) -> pd.DataFrame:
    scored = dataframe.copy()
    prediction = pipeline.predict(scored[MODEL_FEATURES])
    scored["predicted_operational_risk"] = np.clip(prediction, 0, 100).round(3)
    policy_floor = np.where(
        (
            (scored["speeding_pressure"].fillna(0) >= 70)
            | (
                (scored["speed_variance_kmh"].fillna(0) >= 25)
                & (scored["vru_exposure_index"].fillna(0) >= 70)
            )
        ),
        75.0,
        0.0,
    )
    scored["policy_guardrail_floor"] = policy_floor
    scored["speed_safety_score"] = np.maximum(
        scored["predicted_operational_risk"],
        scored["policy_guardrail_floor"],
    ).round(3)
    scored["risk_band"] = scored["speed_safety_score"].apply(risk_band)
    scored["critical_prediction"] = scored["speed_safety_score"] >= 75
    return scored


def classification_metrics(scored: pd.DataFrame, threshold: float) -> dict[str, Any]:
    observed = scored[scored["feature_quality_flag"].isin(["usable", "low_sample", "partial_features"])].copy()
    y_true = observed["critical_label"].astype(bool)
    y_pred = observed["speed_safety_score"] >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        average="binary",
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=[False, True])
    return {
        "critical_threshold": threshold,
        "precision": float(precision),
        "critical_recall": float(recall),
        "f1": float(f1),
        "confusion_matrix": {
            "true_negative": int(matrix[0][0]),
            "false_positive": int(matrix[0][1]),
            "false_negative": int(matrix[1][0]),
            "true_positive": int(matrix[1][1]),
        },
        "observed_rows": int(len(observed)),
    }


def compute_importance(pipeline: Pipeline, X: pd.DataFrame, y: pd.Series, config: dict[str, Any]) -> pd.DataFrame:
    _, X_valid, _, y_valid = train_test_split(
        X,
        y,
        test_size=0.25,
        random_state=config["model"]["random_state"],
    )
    result = permutation_importance(
        pipeline,
        X_valid,
        y_valid,
        n_repeats=5,
        random_state=config["model"]["random_state"],
        scoring="neg_mean_absolute_error",
    )
    importance = pd.DataFrame(
        {
            "feature": MODEL_FEATURES,
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
        }
    )
    return importance.sort_values("importance_mean", ascending=False)


def enrich_geojson(scored: pd.DataFrame, config: dict[str, Any]) -> None:
    feature_geojson = Path(config["feature_geojson"])
    output_path = Path(config["outputs"]["scored_geojson"])
    with feature_geojson.open("r", encoding="utf-8") as file:
        geojson = json.load(file)
    selected_columns = [
        "road_id",
        "risk_target",
        "critical_label",
        "predicted_operational_risk",
        "speed_safety_score",
        "risk_band",
        "critical_prediction",
    ]
    rows_by_id = scored[selected_columns].set_index("road_id").to_dict(orient="index")
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        score_row = rows_by_id.get(props.get("road_id"), {})
        props.update(score_row)
        feature["properties"] = props
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(geojson, file, ensure_ascii=False, separators=(",", ":"))
        file.write("\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_scoring(config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    outputs = config["outputs"]
    Path(outputs["scoring_dir"]).mkdir(parents=True, exist_ok=True)
    dataframe = pd.read_parquet(config["features_parquet"])
    dataframe = build_target(dataframe, config)
    X, y, groups = prepare_model_frame(dataframe)
    spatial_cv = evaluate_spatial_cv(X, y, groups, config)
    pipeline = make_pipeline(config)
    pipeline.fit(X, y)
    scored = score_all_segments(dataframe, pipeline)
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "train_rows": int(len(X)),
        "scored_rows": int(len(scored)),
        "spatial_cross_validation": spatial_cv,
        "policy_weighted_classification": classification_metrics(
            scored,
            config["evaluation"]["critical_threshold"],
        ),
        "risk_band_counts": scored["risk_band"].value_counts().to_dict(),
        "quality_flag_counts": scored["feature_quality_flag"].value_counts().to_dict(),
    }
    importance = compute_importance(pipeline, X, y, config)

    scored.to_csv(outputs["scored_csv"], index=False, quoting=csv.QUOTE_MINIMAL)
    scored.to_parquet(outputs["scored_parquet"], index=False)
    importance.to_csv(outputs["feature_importance_csv"], index=False)
    scored.sort_values("speed_safety_score", ascending=False).head(1000).to_csv(
        outputs["critical_segments_csv"],
        index=False,
        quoting=csv.QUOTE_MINIMAL,
    )
    with Path(outputs["model_pickle"]).open("wb") as file:
        pickle.dump(pipeline, file)
    write_json(Path(outputs["metrics_json"]), metrics)
    enrich_geojson(scored, config)

    manifest = {
        "stage": "Interpretable ML & Safety Scoring",
        "generated_at": metrics["generated_at"],
        "outputs": outputs,
        "feature_count": int(len(scored)),
        "train_rows": int(len(X)),
        "critical_segments": int((scored["risk_band"] == "Critical").sum()),
    }
    write_json(Path(outputs["manifest_json"]), manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the safety model and score all road segments.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    manifest = run_scoring(args.config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
