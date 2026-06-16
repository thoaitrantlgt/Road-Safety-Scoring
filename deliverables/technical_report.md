# Technical Report

## Pipeline

1. ETL and spatial alignment standardizes local road layers to a shared segment schema.
2. Feature engineering derives `speed_variance_kmh`, `speeding_pressure`, and `vru_exposure_index`.
3. Model scoring trains a gradient-boosted tree regressor using observed segments and scores all segments.
4. Visualization exports a standalone interactive HTML map identifying the highest-priority road segments for speed-limit review or intervention, plus a policy-ready scored GeoJSON.

## Target Definition

The current implementation uses a policy-derived surrogate target because direct crash labels are not present in the local input files. The target combines speed variance, speeding pressure, and VRU exposure, then applies a critical-segment guardrail for segments with clearly unsafe operating conditions.

## Feature Summary

```json
{
  "speed_variance_kmh": {
    "count": 15143,
    "mean": 13.6164,
    "min": 0.0,
    "max": 51.1
  },
  "speeding_pressure": {
    "count": 15554,
    "mean": 19.0148,
    "min": 0.0,
    "max": 100.0
  },
  "vru_exposure_index": {
    "count": 69966,
    "mean": 54.9304,
    "min": 22.5,
    "max": 93.25
  },
  "feature_completeness": {
    "count": 69966,
    "mean": 0.4161,
    "min": 0.25,
    "max": 1.0
  },
  "sample_confidence": {
    "count": 69966,
    "mean": 0.1704,
    "min": 0.0,
    "max": 1.0
  }
}
```

## Spatial Cross-Validation

```json
{
  "n_splits": 5,
  "folds": [
    {
      "fold": 1,
      "rows": 3118,
      "mae": 0.3255607350539674,
      "r2": 0.9964809029832319,
      "baseline_mae": 10.205177998717128,
      "baseline_r2": -0.015706532332123047
    },
    {
      "fold": 2,
      "rows": 3122,
      "mae": 0.24193013167034919,
      "r2": 0.9991361769017699,
      "baseline_mae": 10.386934657270979,
      "baseline_r2": -0.0032850768867118685
    },
    {
      "fold": 3,
      "rows": 3125,
      "mae": 0.2290395173870094,
      "r2": 0.9993467145171211,
      "baseline_mae": 10.02554336,
      "baseline_r2": -0.020525479684203818
    },
    {
      "fold": 4,
      "rows": 3124,
      "mae": 0.24361570782066075,
      "r2": 0.9985279656618519,
      "baseline_mae": 12.042274007682458,
      "baseline_r2": -0.130468547306118
    },
    {
      "fold": 5,
      "rows": 3117,
      "mae": 0.2301198975399972,
      "r2": 0.999178326786712,
      "baseline_mae": 10.286445941610523,
      "baseline_r2": -0.02237701551940874
    }
  ],
  "mean_mae": 0.2540531978943968,
  "mean_r2": 0.9985340173701374,
  "mean_baseline_mae": 10.589275193056219,
  "mean_baseline_r2": -0.038472530345713095
}
```

## Policy-Weighted Critical Segment Evaluation

```json
{
  "critical_threshold": 75.0,
  "precision": 0.9863429438543247,
  "critical_recall": 0.9908536585365854,
  "f1": 0.9885931558935361,
  "confusion_matrix": {
    "true_negative": 14941,
    "false_positive": 9,
    "false_negative": 6,
    "true_positive": 650
  },
  "observed_rows": 15606
}
```

## Risk Band Definition

| Score | Band | Suggested action |
| --- | --- | --- |
| 0-45 | Low | Monitor under normal planning cycles. |
| 46-74 | Moderate | Review passive calming, monitoring, and speed-management options. |
| 75-100 | Critical | Prioritize immediate review and speed-management intervention. |
