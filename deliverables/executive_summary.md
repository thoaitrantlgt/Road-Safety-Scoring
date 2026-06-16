# Executive Summary

The pipeline produces a policy-ready Speed Safety Score for 69,966 road segments across Thailand and Maharashtra.

## Key Outputs

| Item | Value |
| --- | --- |
| Total scored road segments | 69,966 |
| Trainable observed segments | 15,606 |
| Critical segments | 659 |
| Moderate segments | 9,954 |
| Low-risk segments | 59,353 |
| Spatial CV MAE | 0.2540531978943968 |
| Spatial CV R2 | 0.9985340173701374 |
| Critical recall | 0.9908536585365854 |

The main feature table contains 69,966 rows and includes speed variance, speeding pressure, VRU exposure, feature quality, and final safety score fields.

The interactive map output is `data/processed/visualization/index.html`. It identifies the highest-priority road segments for speed-limit review or intervention and can be opened at `file:///C:/Thoai/Road/data/processed/visualization/index.html` during local review.
