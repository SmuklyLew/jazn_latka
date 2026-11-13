# TPA Live ROOT authority test baseline

- Source: `tests/test_tpa_live_root_authority_scoping.py`
- Source commit: `fc9819070cd699c697daa4acfe873af251181fb8`
- Original Git blob: `eb7ce73588a3fcc728396f1b4e1874aa7041ad3d`
- Archive preserves the original test content unchanged.
- Reason: initial synthetic fixture missed the `.settings/` marker required to authorize ROOT-local operator acceptance. Preserve the failing baseline for review.
