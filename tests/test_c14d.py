#!/usr/bin/env python3
"""Small contract tests for C14D feature blocks and stage views."""

from __future__ import annotations

import pandas as pd

from c14d_harmonized_models import OULAD_SES, UCI320_SES, oulad_features, uci320_stage_features


def main() -> int:
    oulad_columns = [
        "code_module", "num_of_prev_attempts", "studied_credits", "registration_lead_days",
        "clicks_total", "gender", "highest_education", "imd_band", "region", "age_band", "disability",
    ]
    oulad = pd.DataFrame({name: ["x"] for name in oulad_columns})
    assert "gender" in oulad_features(oulad, "full_control")
    assert "gender" not in oulad_features(oulad, "no_gender")
    assert not OULAD_SES.intersection(oulad_features(oulad, "no_socioeconomic_family"))

    uci = pd.DataFrame(
        {name: ["x"] for name in ["school", "sex", "Medu", "Fedu", "Mjob", "Fjob", "G1", "G2", "G3", "row_id", "target_risk", "budget_group"]}
    )
    baseline = uci320_stage_features(uci, "baseline", "full_control")
    period1 = uci320_stage_features(uci, "period1", "full_control")
    period2 = uci320_stage_features(uci, "period2", "full_control")
    assert "G1" not in baseline and "G1" in period1 and "G2" not in period1 and "G2" in period2
    assert not UCI320_SES.intersection(uci320_stage_features(uci, "period2", "no_socioeconomic_family"))
    print("C14D unit contracts: 6/6 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
