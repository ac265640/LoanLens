const API_BASE = import.meta.env.VITE_API_URL || "";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Transient failures are retried; a definite answer (any other 4xx/5xx) is not.
const RETRYABLE_STATUS = new Set([429, 502, 503, 504]);
const RETRY_DELAYS_MS = [600, 1500];
const ATTEMPT_TIMEOUT_MS = 28_000; // API Gateway cuts a request off at 29s

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let lastError: unknown = new Error("Network error");

  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
    if (attempt > 0) await new Promise((r) => setTimeout(r, RETRY_DELAYS_MS[attempt - 1]));
    const last = attempt === RETRY_DELAYS_MS.length;

    try {
      const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        signal: AbortSignal.timeout(ATTEMPT_TIMEOUT_MS),
      });
      if (res.ok) return res.json();

      const text = await res.text().catch(() => "");
      const err = new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`);
      if (!RETRYABLE_STATUS.has(res.status) || last) throw err;
      lastError = err;
    } catch (e) {
      if (e instanceof ApiError) throw e; // an HTTP answer we should not retry
      lastError = e; // connection reset, DNS, timeout: worth another attempt
      if (last) break;
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Network error");
}

export interface Loan {
  loan_id: string;
  reporting_month: string;
  state: string;
  current_status: string;
  days_past_due: number;
  current_balance: number;
  credit_score_band: string;
  ltv_band?: string | null;
  dti_band?: string | null;
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
  attention_count: number;
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
  baseline?: Partial<StressResult>;
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

// Cedar has no floating point, so policies compare integer percentages. The
// tape only carries an LTV *band*; use the band's upper bound (the
// conservative reading) as the loan's LTV.
export function ltvPct(band?: string | null): number {
  if (!band) return 0;
  const nums = (band.match(/\d+/g) ?? []).map(Number);
  if (band.startsWith(">")) return 100;
  return nums.length ? Math.max(...nums) : 0;
}

export function cedarAuthorize(userId: string, role: string, action: string, loan: Loan) {
  return request<CedarResult>("/cedar/authorize", {
    method: "POST",
    body: JSON.stringify({ userId, role, action, loan: { ...loan, ltv_pct: ltvPct(loan.ltv_band) } }),
  });
}

export interface CopilotResult {
  mode: string;
  model_name: string;
  provider?: string;
  fallback?: boolean;
  fallback_reason?: string | null;
  output: string;
  disclaimer: string;
}

export function copilotMemo(loan_id: string) {
  return request<CopilotResult>("/copilot", { method: "POST", body: JSON.stringify({ mode: "memo", loan_id }) });
}

export function copilotAsk(question: string) {
  return request<CopilotResult>("/copilot", {
    method: "POST",
    body: JSON.stringify({ mode: "portfolio_qa", question }),
  });
}

export function copilotExplainStress(scenario: StressResult) {
  return request<CopilotResult>("/copilot", {
    method: "POST",
    body: JSON.stringify({ mode: "stress_explain", scenario_result: scenario }),
  });
}
