# Historical test snapshots

`tests/archive/` is an append-only evidence store for test contracts that were active in earlier releases. It is not part of the default pytest collection and must not be used as current release evidence.

Rules:

- preserve a test byte-for-byte before changing an existing active test;
- suffix the snapshot filename with the source release version;
- never edit, format, rename, move, or overwrite an existing snapshot;
- create a new snapshot when another historical state must be retained;
- run a snapshot only by passing its exact path to pytest;
- keep active tests in `tests/`, outside this directory.

The repository-level `tests/conftest.py` still applies when a snapshot is run explicitly, so runtime workspace state remains isolated.

Initial provenance:

| Active source at merge-base | Immutable snapshot | Git blob |
| --- | --- | --- |
| `tests/test_memory_rebuild_source_union.py` | `test_memory_rebuild_source_union_v16_3_25_3_1.py` | `5d2adf9af04fadec4c68ea7628068e920156b243` |
| `tests/test_memory_rebuild_test00_source_fidelity.py` | `test_memory_rebuild_test00_source_fidelity_v16_3_25_3_1.py` | `927916642ca2cb1afd39cd4d2eaa6fbabb8c4844` |
| `tests/test_memory_rebuild_v24_unified.py` | `test_memory_rebuild_v24_unified_v16_3_25_3_1.py` | `3f40d2e39fc803976beb3c3f1b8dd5b0d0a19085` |

All three initial snapshots come from merge-base `3884bed3d8445924c6783a1cc87d15e91b8fcbe2`.

Additional append-only provenance:

| Active source before change | Immutable snapshot | Git blob |
| --- | --- | --- |
| `tests/test_release_metadata_semantics_v163253.py` from master release `16.3.25.3.4` | `test_release_metadata_semantics_v163253_v16_3_25_3_4.py` | `280fe1dbfc838fe4afe36666f4b81c0a3831a46b` |
| `tests/test_version_consistency_audit_v163254.py` from target release `16.3.25.4` before current-master integration follow-up | `test_version_consistency_audit_v163254_v16_3_25_4.py` | `dab2b6cd1a429064752a04808d1c5fcb935ec010` |
