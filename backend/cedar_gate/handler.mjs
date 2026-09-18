// Cedar Policy Gate Lambda
// ========================
// Evaluates every loan approval / anomaly-override action against the
// declarative Cedar policies in policies/underwriting.cedar before the
// action is allowed to happen. Returns the decision plus which policy
// clause drove it, for display as a "Cedar Compliance Gate" in the UI.

import * as cedar from "@cedar-policy/cedar-wasm/nodejs";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const POLICIES = readFileSync(join(__dirname, "policies", "underwriting.cedar"), "utf8");

export const handler = async (event) => {
  const body = typeof event.body === "string" ? JSON.parse(event.body) : (event.body || event);
  const { userId, role, action, loan } = body;

  if (!userId || !role || !action || !loan || !loan.loan_id) {
    return respond(400, { error: "userId, role, action, and loan (with loan_id) are required" });
  }

  const call = {
    principal: { type: "User", id: String(userId) },
    action: { type: "Action", id: String(action) },
    resource: { type: "Loan", id: String(loan.loan_id) },
    context: {},
    policies: { staticPolicies: POLICIES },
    entities: [
      { uid: { type: "User", id: String(userId) }, attrs: {}, parents: [{ type: "Role", id: String(role) }] },
      { uid: { type: "Role", id: String(role) }, attrs: {}, parents: [] },
      {
        uid: { type: "Loan", id: String(loan.loan_id) },
        attrs: {
          risk_score_pct: Math.round((loan.risk_score_pct ?? (loan.prob_next_12m_default ?? 0) * 100)),
          ltv_pct: Math.round(loan.ltv_pct ?? 0),
          loan_amount_usd: Math.round(loan.loan_amount_usd ?? loan.current_balance ?? 0),
          has_fraud_flag: Boolean(loan.has_fraud_flag ?? loan.exception_required === 1),
        },
        parents: [],
      },
    ],
  };

  const result = cedar.isAuthorized(call);

  if (result.type !== "success") {
    return respond(500, { decision: "deny", reason: "policy_evaluation_error", errors: result.errors });
  }

  return respond(200, {
    decision: result.response.decision,
    determining_policies: result.response.diagnostics.reason,
    errors: result.response.diagnostics.errors,
  });
};

function respond(statusCode, bodyObj) {
  return {
    statusCode,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    body: JSON.stringify(bodyObj),
  };
}
