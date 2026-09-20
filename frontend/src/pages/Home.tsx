import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import ArchitectureDiagram from './ArchitectureDiagram';
import HexBackground from './HexBackground';

/* ------------------------------------------------------------------ */
/* Hero visual: an illustrative 400-loan portfolio (20 x 20 dots).     */
/* Every number in the caption is computed from these sets, so the     */
/* text can never disagree with the dots.                              */
/* ------------------------------------------------------------------ */
const TOTAL_DOTS = 400;
const COLS = 20;

const HIGH_RISK_INDICES = new Set([14, 28, 45, 67, 89, 112, 134, 156, 178, 203, 225, 248, 270, 292, 315, 338, 360, 382]);
const EXCEPTION_INDICES = new Set([23, 58, 94, 142, 187, 231, 285, 349]);
const PROBLEMS = HIGH_RISK_INDICES.size + EXCEPTION_INDICES.size; // 26

// 5% sample = 20 loans, spread across the grid (not a single row)
const SAMPLE = new Set(Array.from({ length: 20 }, (_, k) => 11 + 19 * k));
const CAUGHT = [...SAMPLE].filter((i) => HIGH_RISK_INDICES.has(i) || EXCEPTION_INDICES.has(i)).length;

type Mode = 'sample' | 'all';

export default function Home() {
    const [mode, setMode] = useState<Mode>('sample');
    const touched = useRef(false);
    const rootRef = useRef<HTMLElement>(null);

    const choose = (m: Mode) => {
        touched.current = true;
        setMode(m);
    };

    // One orchestrated moment: show today's sample, then sweep across the rest.
    // Skipped if the visitor already clicked the toggle.
    useEffect(() => {
        const t = setTimeout(() => {
            if (!touched.current) setMode('all');
        }, 1800);
        return () => clearTimeout(t);
    }, []);

    // Reveal-on-scroll, used only on the hero and the diagram.
    useEffect(() => {
        const targets = rootRef.current?.querySelectorAll('.reveal-on-scroll');
        if (!targets || targets.length === 0) return;

        if (typeof IntersectionObserver === 'undefined') {
            targets.forEach((el) => el.classList.add('is-revealed'));
            return;
        }

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('is-revealed');
                        observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
        );
        targets.forEach((el) => observer.observe(el));
        return () => observer.disconnect();
    }, []);

    // Works with BrowserRouter and HashRouter (a plain #anchor would break under HashRouter)
    const scrollToArchitecture = (e: React.MouseEvent<HTMLAnchorElement>) => {
        e.preventDefault();
        document.getElementById('architecture')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const checked = mode === 'all' ? TOTAL_DOTS : SAMPLE.size;
    const found = mode === 'all' ? PROBLEMS : CAUGHT;

    return (
        <main className="home" ref={rootRef}>
            <HexBackground />

            {/* ---------------- hero ---------------- */}
            <section className="hero reveal-on-scroll">
                <div className="hero-copy">
                    <div className="hero-brand">
                        Loan<span>Lens</span>
                    </div>
                    <h1>Every loan scored, not just 5%.</h1>
                    <p>
                        Manual review often covers only a sample of each month's loan tape (5% in the example below), so most of the portfolio goes unreviewed.
                        LoanLens scores all of it on AWS: five risk predictions per loan, anomaly detection, live macro
                        stress testing and a Cedar policy gate.
                    </p>
                    <div className="hero-actions">
                        <Link to="/dashboard" className="btn primary">
                            Open the dashboard
                        </Link>
                        <a href="#architecture" className="btn ghost" onClick={scrollToArchitecture}>
                            See the architecture
                        </a>
                    </div>
                </div>

                <figure className="hero-viz">
                    <div className="seg" role="group" aria-label="Review method">
                        <button type="button" aria-pressed={mode === 'sample'} onClick={() => choose('sample')}>
                            5% sample
                        </button>
                        <button type="button" aria-pressed={mode === 'all'} onClick={() => choose('all')}>
                            LoanLens, 100%
                        </button>
                    </div>

                    <div
                        className={`dots ${mode === 'all' ? 'is-all' : ''}`}
                        role="img"
                        aria-label={`${TOTAL_DOTS} loans. ${checked} checked, ${found} of ${PROBLEMS} problem loans found.`}
                    >
                        {Array.from({ length: TOTAL_DOTS }, (_, i) => {
                            const kind = HIGH_RISK_INDICES.has(i) ? 'hr' : EXCEPTION_INDICES.has(i) ? 'ex' : '';
                            const cls = mode === 'all' ? kind : SAMPLE.has(i) ? 'sample' : '';
                            const delay = ((i % COLS) + Math.floor(i / COLS)) * 22;
                            return <div key={i} className={`dot ${cls}`} style={{ transitionDelay: `${delay}ms` }} />;
                        })}
                    </div>

                    <figcaption aria-live="polite">
                        <strong>
                            {checked} of {TOTAL_DOTS}
                        </strong>{' '}
                        loans checked.{' '}
                        <strong>
                            {found} of {PROBLEMS}
                        </strong>{' '}
                        problem loans found.
                        <span className="legend">
                            <span className="k hr" /> High risk (20%+ default probability)
                            <span className="k ex" /> Exception or anomaly
                        </span>
                        <span className="note">Illustrative portfolio of {TOTAL_DOTS} loans.</span>
                    </figcaption>
                </figure>
            </section>

            {/* ---------------- features ---------------- */}
            <section className="block">
                <div className="narrow">
                    <h2>Built to replace manual loan-tape sampling</h2>
                    <p className="lede">
                        Underwriting teams review a small sample of the portfolio each month because they do not have the
                        hours to review more. LoanLens scores every loan when the tape is uploaded, using serverless ML,
                        deterministic rules and policy-as-code governance.
                    </p>
                    <dl className="rows">
                        <div className="row">
                            <dt>Five risk predictions</dt>
                            <dd>
                                LightGBM models predict 3-month delinquency, 6-month delinquency, 12-month default, 12-month
                                prepayment and next-month state transitions. The four probabilities are Platt-calibrated on held-out
                                validation cohorts.
                            </dd>
                        </div>
                        <div className="row">
                            <dt>Hybrid exception detection</dt>
                            <dd>
                                An unsupervised Isolation Forest combined with deterministic validation rules (VR001 to VR005)
                                flags records that contradict themselves: out-of-order dates, paid-off loans that still carry a balance, defaults with too few days past due, missing documents on modified loans and runaway balances.
                            </dd>
                        </div>
                        <div className="row">
                            <dt>Cedar policy gate</dt>
                            <dd>
                                Approval permissions are written as policy, evaluated with{' '}
                                <code>@cedar-policy/cedar-wasm</code>, across junior underwriters, senior underwriters and risk
                                committees. A junior can approve only when risk is 25% or less, LTV is 80 or less and the amount is $2.5M or less.
                            </dd>
                        </div>
                        <div className="row">
                            <dt>Shockwave stress simulator</dt>
                            <dd>
                                Push interest rates and unemployment around and see the portfolio's expected loss, capital
                                buffer impact and Value-at-Risk recalculate immediately.
                            </dd>
                        </div>
                        <div className="row">
                            <dt>Grounded reviewer copilot</dt>
                            <dd>
                                A reviewer assistant that answers from the scored portfolio only, using Amazon Bedrock when the
                                account has access and an OpenAI-compatible model otherwise. Every call is logged to an audit
                                table in DynamoDB.
                            </dd>
                        </div>
                    </dl>
                </div>
            </section>

            {/* ---------------- architecture ---------------- */}
            <section id="architecture" className="block">
                <div className="narrow">
                    <h2>Serverless architecture on AWS</h2>
                    <p className="lede">
                        Scale-to-zero by design: no idle EC2, no persistent clusters, no SageMaker endpoint. Hover or tab to a
                        service to see what it connects to.
                    </p>
                </div>
                <div className="diagram reveal-on-scroll">
                    <ArchitectureDiagram />
                </div>
            </section>

            {/* ---------------- services ---------------- */}
            <section className="block">
                <div className="narrow">
                    <h2>AWS services used</h2>
                    <div className="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Service</th>
                                    <th>Role</th>
                                    <th>Implementation</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <th>Amazon S3</th>
                                    <td>Raw ingestion</td>
                                    <td>
                                        Receives uploaded loan tape CSVs under the <code>raw/</code> prefix.
                                    </td>
                                </tr>
                                <tr>
                                    <th>Amazon EventBridge</th>
                                    <td>Event routing</td>
                                    <td>Catches S3 ObjectCreated events and starts the pipeline.</td>
                                </tr>
                                <tr>
                                    <th>AWS Step Functions</th>
                                    <td>Orchestration</td>
                                    <td>
                                        Runs the scoring workflow, retries transient failures, and publishes an alert when a run
                                        finds high-risk loans or data exceptions.
                                    </td>
                                </tr>
                                <tr>
                                    <th>Amazon SNS</th>
                                    <td>Alerts</td>
                                    <td>Step Functions publishes to a topic; subscribe an email address to be told when a tape needs attention.</td>
                                </tr>
                                <tr>
                                    <th>AWS Lambda</th>
                                    <td>Compute and scoring</td>
                                    <td>
                                        A containerized arm64 Python 3.12 function running LightGBM and Isolation Forest, other Python
                                        functions for the API, and a Node.js function for Cedar WASM.
                                    </td>
                                </tr>
                                <tr>
                                    <th>Amazon DynamoDB</th>
                                    <td>Storage and audit log</td>
                                    <td>
                                        On-demand tables for scored loans (<code>loanlens-loans</code>), runs and copilot audit
                                        trails.
                                    </td>
                                </tr>
                                <tr>
                                    <th>Amazon API Gateway</th>
                                    <td>REST API</td>
                                    <td>Public REST endpoints in front of the backend, with CORS enabled.</td>
                                </tr>
                                <tr>
                                    <th>Amazon Bedrock</th>
                                    <td>Reviewer copilot, first choice</td>
                                    <td>
                                        Nova Lite, grounded in the scored portfolio. If the account has no Bedrock access the copilot
                                        falls back to an OpenAI-compatible model, then to a deterministic template. The UI always
                                        shows which one answered.
                                    </td>
                                </tr>
                                <tr>
                                    <th>AWS Systems Manager Parameter Store</th>
                                    <td>Secrets and settings</td>
                                    <td>Holds the fallback model's endpoint and API key (SecureString), so no key lives in code or the repo.</td>
                                </tr>
                                <tr>
                                    <th>AWS Amplify Hosting</th>
                                    <td>Frontend delivery</td>
                                    <td>Hosts the React + Vite dashboard behind a CDN.</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <p className="table-note">
                        Cedar is an open-source policy language, not an AWS service. It runs inside Lambda through
                        cedar-wasm.
                    </p>
                </div>
            </section>

            {/* ---------------- limitations ---------------- */}
            <section className="block">
                <div className="narrow">
                    <h2>What it does not do</h2>
                    <ul className="limits">
                        <li>
                            <strong>It runs on synthetic data.</strong> The portfolio is generated, with monthly panel
                            history, so no real borrower data is involved. It also means model metrics show how the pipeline
                            behaves, not how it would perform on a real lender's book.
                        </li>
                        <li>
                            <strong>Scores are estimates, not credit decisions.</strong> A human reviewer stays in the loop,
                            and the Cedar gate limits who can approve what.
                        </li>
                        <li>
                            <strong>Risk capital is illustrative.</strong> Expected loss uses a fixed 35% Loss Given Default,
                            and capital impact and VaR use parameterized z-score approximations.
                        </li>
                        <li>
                            <strong>The copilot can still be wrong.</strong> It only sees the scored portfolio, but it is a
                            language model. Check its answers against the table before acting on them.
                        </li>
                        <li>
                            <strong>Cedar works in whole numbers.</strong> Default probabilities are scaled by 100 and LTV
                            thresholds are applied as conservative upper bounds.
                        </li>
                        <li>
                            <strong>Cold starts.</strong> Scale-to-zero means the first request after a quiet period waits for
                            a Lambda cold start.
                        </li>
                    </ul>
                </div>
            </section>

            {/* ---------------- closing ---------------- */}
            <section className="closing">
                <h2>Try it on a loan tape</h2>
                <p className="lede">
                    Audit the high-risk loans, run a macro shock, or ask the copilot about the portfolio.
                </p>
                <div className="hero-actions">
                    <Link to="/dashboard" className="btn primary">
                        Open the dashboard
                    </Link>
                </div>
            </section>
        </main>
    );
}