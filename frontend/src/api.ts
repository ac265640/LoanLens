const API_BASE = import.meta.env.VITE_API_URL || "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export interface Loan {
  loan_id: string;
  reporting_month: string;
  state: string;
  current_status: string;
  days_past_due: number;
  current_balance: number;
  credit_score_band: string;
  prob_next_3m_delinquency: number;
  prob_next_6m_delinquency: number;
  prob_next_12m_default: number;
  prob_next_12m_prepayment: number;
  next_state: string;
  exception_required: number;
  exception_type: string;
  anomaly_score: number;
  top_driver_1: string;
  top_driver_2: string;
  top_driver_3: string;
  recommended_action: string;
  confidence: number;
}

export interface PortfolioSummary {
  total_loans: number;
  high_risk_count: number;
  exception_count: number;
  total_exposure_usd: number;
}

export function listLoans(params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  return request<{ summary: PortfolioSummary; loans: Loan[] }>(`/loans${qs ? `?${qs}` : ""}`);
}

export function getRun(runId: string) {
  return request<{ run_id: string; status: string; loans_scored?: number; high_risk_count?: number; exception_count?: number; error?: string }>(
    `/runs/${runId}`
  );
}

export async function requestUploadUrl() {
  return request<{ upload_url: string; bucket: string; key: string }>("/upload-url", { method: "POST" });
}

export async function uploadTape(file: File, onProgress?: (pct: number) => void) {
  const { upload_url, key } = await requestUploadUrl();
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", upload_url);
    xhr.setRequestHeader("Content-Type", "text/csv");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`upload failed: ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("upload failed"));
    xhr.send(file);
  });
  return key;
}

export interface StressResult {
  rate_shock_bps: number;
  unemployment_delta_pct: number;
  mean_default_prob_pct: number;
  mean_prepay_mult: number;
  mean_delinq_mult: number;
  expected_loss_usd: number;
  expected_loss_pct_of_portfolio: number;
  car_impact_pct: number;
  var99_usd: number;
  portfolio_total_exposure_usd: number;
  loan_count: number;
}

export function queryStress(rate_shock_bps: number, unemployment_delta_pct: number) {
  return request<StressResult>("/stress", {
    method: "POST",
    body: JSON.stringify({ rate_shock_bps, unemployment_delta_pct }),
  });
}

export interface CedarResult {
  decision: "allow" | "deny";
  determining_policies: string[];
}

export function cedarAuthorize(userId: string, role: string, action: string, loan: Loan) {
  return request<CedarResult>("/cedar/authorize", {
    method: "POST",
    body: JSON.stringify({ userId, role, action, loan }),
  });
}

export interface CopilotResult {
  mode: string;
  model_name: string;
  output: string;
  disclaimer: string;
}

export function copilotMemo(loan_id: string) {
  return request<CopilotResult>("/copilot", { method: "POST", body: JSON.stringify({ mode: "memo", loan_id }) });
}

export function copilotAsk(question: string, filters: Record<string, unknown> = {}) {
  return request<CopilotResult>("/copilot", {
    method: "POST",
    body: JSON.stringify({ mode: "portfolio_qa", question, filters }),
  });
}
