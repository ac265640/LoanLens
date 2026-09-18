// LoanLens Credit Governance Policies
// ====================================
// Cedar policy-as-code guardrails for loan approval / anomaly override actions.
// Risk and LTV are expressed as integer percentages (0-100) since Cedar has no
// native floating-point comparison operators.

// A Junior Underwriter may approve a loan only when it is low-risk and within
// conservative LTV bounds.
permit(
  principal in Role::"JuniorUnderwriter",
  action == Action::"ApproveLoan",
  resource
) when {
  resource.risk_score_pct <= 25 &&
  resource.ltv_pct <= 80 &&
  resource.loan_amount_usd <= 2500000
};

// A Senior Underwriter has a wider approval band.
permit(
  principal in Role::"SeniorUnderwriter",
  action == Action::"ApproveLoan",
  resource
) when {
  resource.risk_score_pct <= 50 &&
  resource.ltv_pct <= 90
};

// Only the Risk Committee may approve a loan already flagged high-risk.
permit(
  principal in Role::"RiskCommittee",
  action == Action::"ApproveLoan",
  resource
);

// No one below the Risk Committee may override an anomaly flag on a loan
// that has a fraud signal — this is an explicit, non-negotiable guardrail.
forbid(
  principal,
  action == Action::"OverrideAnomaly",
  resource
) when {
  resource.has_fraud_flag == true
} unless {
  principal in Role::"RiskCommittee"
};

// The Risk Committee may always override an anomaly flag.
permit(
  principal in Role::"RiskCommittee",
  action == Action::"OverrideAnomaly",
  resource
);
