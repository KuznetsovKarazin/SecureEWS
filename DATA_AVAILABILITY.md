# Data and artifact availability

The public package is deliberately aggregate-only. It contains no raw or processed student-level records, individual model predictions, trained model bundles, or XuetangX files.

## Official inputs and pinned outer hashes

| Dataset | Official source | SHA-256 used in the clean-room |
| --- | --- | --- |
| OULAD / UCI 349 | https://archive.ics.uci.edu/dataset/349/open+university+learning+analytics+dataset | `f2ed1902616c1fe8d2824d872c0b7d2d72be435bf0124d077044fe4be2c6d3e4` |
| UCI 697 | https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success | `e90e55fd65ec462ae283ebeb2cca409319e3460ed898d8754f62fb35cc83a65d` |
| UCI 320 | https://archive.ics.uci.edu/dataset/320/student+performance | `82ae9d66437b9808df42e8c89d2bb179c46e9cfbcf06f38abc1d20b3b747e177` |

The private archival anchor was `SecureEWS_C14G_CLEANROOM_PROJECT.zip`, SHA-256 `c5772af7e3017fbb20019c2ac9a223f247292d5724dab9815eb4a9b8fed5b47e`. It is not part of the public release.

## Publicly reproducible checks

- C14B queue algebra and multi-budget aggregate outputs;
- C14E paired intervals and multiplicity from 42 hashed bootstrap draw files;
- C14F tables, figures, PDFs, provenance hashes, and page-level QA record;
- aggregate C14C and C14D inventories and verification gates.

Full row-level replay is retained outside the public release and may be made available subject to dataset licenses, institutional policy, privacy review, and a technically justified request.
