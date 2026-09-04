# SecureEWS v0.6.0

This release adds the complete C14 stress-test extension to the provenance-corrected C13E analysis.

## Added

- frozen multi-budget protocol for 5%, 10%, 20%, and 30% review capacity;
- budget sensitivity calculated from saved out-of-fold predictions without model refitting;
- fixed proxy-persistence probes for directly excluded fields;
- harmonized sex/gender and socioeconomic/family exclusion blocks with exact same-run controls;
- paired cluster/row bootstrap inference with family-wise multiplicity control;
- revised academic article and supplementary materials;
- public aggregate-only release verifier and provenance manifest.

## Verification summary

- C14B: 150 configurations, 600 budget rows, zero fitted models;
- C14C: 44 probe configurations and 250,044 held-out predictions verified in the private clean-room;
- C14D: 28 new HGB bundles, 30 harmonized pairs, and 274,004 paired prediction rows verified in the private clean-room;
- C14E: 151 contrasts, 42 resampling tasks, and 2,869 interval rows independently recalculated;
- C14F: 21-page article plus 10-page supplement; all 31 pages visually inspected;
- XuetangX C05: preserved but not extracted, retrained, or used as demographic evidence.

## Public-release boundary

Raw/processed row-level data, individual predictions, trained models, the private full clean-room, XuetangX, legacy v0.1 material, and DP experiments are excluded.
