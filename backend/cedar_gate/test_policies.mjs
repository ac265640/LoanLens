// Cedar Policy Test Suite
// =========================
// Exercises underwriting.cedar against the official Cedar engine
// (@cedar-policy/cedar-wasm) with concrete authorization scenarios, so a
// policy change that silently breaks a guardrail fails a test rather than
// getting discovered live in the demo.
//
// Run: node backend/cedar_gate/test_policies.mjs

import * as cedar from "@cedar-policy/cedar-wasm/nodejs";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const POLICIES = readFileSync(join(__dirname, "policies", "underwriting.cedar"), "utf8");

function authorize({ userId, role, action, loanId, attrs }) {
  const call = {
    principal: { type: "User", id: userId },
    action: { type: "Action", id: action },
    resource: { type: "Loan", id: loanId },
    context: {},
    policies: { staticPolicies: POLICIES },
    entities: [
      { uid: { type: "User", id: userId }, attrs: {}, parents: [{ type: "Role", id: role }] },
      { uid: { type: "Role", id: role }, attrs: {}, parents: [] },
      { uid: { type: "Loan", id: loanId }, attrs, parents: [] },
    ],
  };
  const result = cedar.isAuthorized(call);
  if (result.type !== "success") {
    throw new Error(`policy evaluation error: ${JSON.stringify(result.errors)}`);
  }
  return result.response.decision;
}

const cases = [
  {
    name: "Junior Underwriter can approve a low-risk, low-LTV loan",
    args: { userId: "u1", role: "JuniorUnderwriter", action: "ApproveLoan", loanId: "L1",
      attrs: { risk_score_pct: 18, ltv_pct: 75, loan_amount_usd: 400000, has_fraud_flag: false } },
    expect: "allow",
  },
  {
    name: "Junior Underwriter cannot approve a loan above their risk limit",
    args: { userId: "u1", role: "JuniorUnderwriter", action: "ApproveLoan", loanId: "L2",
      attrs: { risk_score_pct: 40, ltv_pct: 75, loan_amount_usd: 400000, has_fraud_flag: false } },
    expect: "deny",
  },
  {
    name: "Junior Underwriter cannot approve a loan above their LTV limit",
    args: { userId: "u1", role: "JuniorUnderwriter", action: "ApproveLoan", loanId: "L3",
      attrs: { risk_score_pct: 10, ltv_pct: 92, loan_amount_usd: 400000, has_fraud_flag: false } },
    expect: "deny",
  },
  {
    name: "Junior Underwriter cannot approve above their loan amount cap",
    args: { userId: "u1", role: "JuniorUnderwriter", action: "ApproveLoan", loanId: "L4",
      attrs: { risk_score_pct: 10, ltv_pct: 60, loan_amount_usd: 3000000, has_fraud_flag: false } },
    expect: "deny",
  },
  {
    name: "Senior Underwriter can approve within their wider risk/LTV band",
    args: { userId: "u2", role: "SeniorUnderwriter", action: "ApproveLoan", loanId: "L5",
      attrs: { risk_score_pct: 45, ltv_pct: 88, loan_amount_usd: 900000, has_fraud_flag: false } },
    expect: "allow",
  },
  {
    name: "Senior Underwriter cannot override a fraud-flagged anomaly",
    args: { userId: "u2", role: "SeniorUnderwriter", action: "OverrideAnomaly", loanId: "L6",
      attrs: { risk_score_pct: 60, ltv_pct: 85, loan_amount_usd: 300000, has_fraud_flag: true } },
    expect: "deny",
  },
  {
    name: "Risk Committee can override a fraud-flagged anomaly",
    args: { userId: "u3", role: "RiskCommittee", action: "OverrideAnomaly", loanId: "L6",
      attrs: { risk_score_pct: 60, ltv_pct: 85, loan_amount_usd: 300000, has_fraud_flag: true } },
    expect: "allow",
  },
  {
    name: "Risk Committee can approve any risk tier",
    args: { userId: "u3", role: "RiskCommittee", action: "ApproveLoan", loanId: "L7",
      attrs: { risk_score_pct: 95, ltv_pct: 99, loan_amount_usd: 5000000, has_fraud_flag: false } },
    expect: "allow",
  },
];

let failures = 0;
for (const c of cases) {
  const decision = authorize(c.args);
  const ok = decision === c.expect;
  console.log(`${ok ? "PASS" : "FAIL"}  ${c.name}  (expected ${c.expect}, got ${decision})`);
  if (!ok) failures += 1;
}

console.log(`\n${cases.length - failures}/${cases.length} passed`);
if (failures > 0) process.exit(1);
