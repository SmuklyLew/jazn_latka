job_status=failure
stage=decode_and_verify
target_branch=update/v15.1.0.3.90-runtime-hardening
base_sha=30a30593901e0b8d24ba6f443f8f67d91d5078e1
payload_blob_sha=ed54cb7abc503d5116a5c67988ffdba3b75e7c34

```text
payload_blob_sha=ed54cb7abc503d5116a5c67988ffdba3b75e7c34
Traceback (most recent call last):
  File "<stdin>", line 10, in <module>
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/gzip.py", line 649, in decompress
    decompressed = do.decompress(data[fp.tell():])
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
zlib.error: Error -3 while decompressing data: invalid distance too far back
```
