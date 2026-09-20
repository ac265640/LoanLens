import { useId, useState, type ReactNode } from 'react';

/**
 * LoanLens architecture, drawn as a pathway.
 * - Zero dependencies: plain SVG + CSS, icons are inline.
 * - Text uses currentColor, so it works in light and dark themes.
 * - The road is masked out around each station, so no background color is assumed.
 * - Edit STATIONS / BRANCHES / MAIN_PATH and the diagram redraws itself.
 */

type Kind = 'ingest' | 'compute' | 'data' | 'api' | 'ai' | 'gov' | 'ui';

const COLORS: Record<Kind, string> = {
    ingest: '#818cf8',
    compute: '#a78bfa',
    data: '#34d399',
    api: '#38bdf8',
    ai: '#fbbf24',
    gov: '#fb7185',
    ui: '#94a3b8',
};

interface Station {
    id: string;
    x: number;
    y: number;
    kind: Kind;
    title: string;
    lines: string[];
    step?: number; // numbered stops on the main road
}

const R = 34; // station radius
const KNOCKOUT = 44; // road is hidden inside this radius

const STATIONS: Station[] = [
    // road, lane 1: ingest and score (left to right)
    { id: 's3', x: 100, y: 120, kind: 'ingest', title: 'S3', lines: ['raw/ prefix', 'triggers pipeline'], step: 1 },
    { id: 'eb', x: 290, y: 120, kind: 'ingest', title: 'EventBridge', lines: ['routes upload event'], step: 2 },
    { id: 'sf', x: 480, y: 120, kind: 'compute', title: 'Step Functions', lines: ['orchestrates the run', 'alerts via SNS'], step: 3 },
    { id: 'lam', x: 670, y: 120, kind: 'compute', title: 'Lambda ingest', lines: ['arm64 container'], step: 4 },
    { id: 'ml', x: 860, y: 120, kind: 'compute', title: 'Scoring models', lines: ['LightGBM x5, IsolationForest', 'VR001 to VR005'], step: 5 },
    // road, lane 2: serve (right to left)
    { id: 'ddb', x: 780, y: 310, kind: 'data', title: 'DynamoDB', lines: ['on-demand billing'], step: 6 },
    { id: 'api', x: 590, y: 310, kind: 'api', title: 'API Gateway', lines: ['REST'], step: 7 },
    { id: 'ui', x: 400, y: 310, kind: 'ui', title: 'React + Vite', lines: ['Amplify Hosting'], step: 8 },
    // side lanes that feed the API
    { id: 'br', x: 470, y: 540, kind: 'ai', title: 'Bedrock', lines: ['Nova Lite', 'reviewer copilot'] },
    { id: 'ssm', x: 250, y: 540, kind: 'data', title: 'SSM Parameter Store', lines: ['LLM key (SecureString)', 'fallback model settings'] },
    { id: 'cedar', x: 710, y: 540, kind: 'gov', title: 'Cedar policy gate', lines: ['Node.js Lambda', 'cedar-wasm'] },
];

// One continuous road: through lane 1, a U-turn on the right, back through lane 2.
const MAIN_PATH = 'M100 120 H900 C985 120 985 310 900 310 H400';
const MAIN_ORDER = ['s3', 'eb', 'sf', 'lam', 'ml', 'ddb', 'api', 'ui'];

const BRANCHES: { from: string; to?: string; d: string }[] = [
    { from: 'br', d: 'M470 540 C470 440 470 390 564 344' },
    { from: 'ssm', to: 'br', d: 'M284 540 H436' },
    { from: 'cedar', d: 'M710 540 C710 440 710 390 616 344' },
];

const BY_ID = Object.fromEntries(STATIONS.map((s) => [s.id, s]));

// Which stations light up together on hover.
const NEIGHBORS: Record<string, string[]> = {};
const link = (a: string, b: string) => {
    (NEIGHBORS[a] ||= []).push(b);
    (NEIGHBORS[b] ||= []).push(a);
};
MAIN_ORDER.forEach((id, i) => i > 0 && link(MAIN_ORDER[i - 1], id));
BRANCHES.forEach((b) => link(b.from, b.to ?? 'api'));

/* Icons are drawn in a 24x24 box with a stroke, then scaled into the station disc. */
const ICONS: Record<string, ReactNode> = {
    s3: (
        <>
            <path d="M4 7h16l-2 12.5c-.2 1-2.7 1.8-6 1.8s-5.8-.8-6-1.8z" />
            <ellipse cx="12" cy="7" rx="8" ry="3" />
        </>
    ),
    eb: <path d="M13 2.5 5 13.5h6l-1 8 8-11h-6z" />,
    sf: (
        <>
            <rect x="9" y="3" width="6" height="5" rx="1" />
            <rect x="3" y="16" width="6" height="5" rx="1" />
            <rect x="15" y="16" width="6" height="5" rx="1" />
            <path d="M12 8v4M6 16v-4h12v4" />
        </>
    ),
    lam: <path d="M6 4h3l8.5 16M11.6 11.6 6.5 20" />,
    ml: (
        <>
            <circle cx="5" cy="7" r="2" />
            <circle cx="5" cy="17" r="2" />
            <circle cx="12" cy="12" r="2" />
            <circle cx="19" cy="7" r="2" />
            <circle cx="19" cy="17" r="2" />
            <path d="m6.8 8 3.4 2.9M6.8 16l3.4-2.9M13.8 10.9 17.2 8M13.8 13.1l3.4 2.9" />
        </>
    ),
    ddb: (
        <>
            <ellipse cx="12" cy="6" rx="8" ry="3" />
            <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
        </>
    ),
    api: <path d="m8 7-5 5 5 5M16 7l5 5-5 5M13.5 5l-3 14" />,
    ui: (
        <>
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M3 9h18M6.5 6.5h.01M9.5 6.5h.01" />
        </>
    ),
    br: (
        <>
            <path d="m10 3 1.8 5.2L17 10l-5.2 1.8L10 17l-1.8-5.2L3 10l5.2-1.8z" />
            <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />
        </>
    ),
    ssm: (
        <>
            <circle cx="8" cy="12" r="4" />
            <path d="M12 12h9M18 12v3M15 12v2" />
        </>
    ),
    cedar: (
        <>
            <path d="M12 3 20 6v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z" />
            <path d="m8.5 12 2.5 2.5 4.5-5" />
        </>
    ),
};

export default function ArchitectureDiagram({ className = '' }: { className?: string }) {
    const uid = useId().replace(/:/g, '');
    const [active, setActive] = useState<string | null>(null);

    const lit = new Set<string>();
    if (active) {
        lit.add(active);
        (NEIGHBORS[active] ?? []).forEach((n) => lit.add(n));
    }
    const dimmed = (id: string) => active !== null && !lit.has(id);

    const id = (name: string) => `ll-${uid}-${name}`;

    return (
        <div className={className}>
            <style>{`
        .ll-flow { stroke-dasharray: 10 10; animation: ll-dash 1.4s linear infinite; }
        @keyframes ll-dash { to { stroke-dashoffset: -20; } }
        .ll-node { transition: opacity .2s ease; outline: none; cursor: default; }
        .ll-disc { transition: transform .2s ease; transform-box: fill-box; transform-origin: center; }
        .ll-node.on .ll-disc { transform: scale(1.1); }
        .ll-halo { opacity: 0; transition: opacity .2s ease; }
        .ll-node.on .ll-halo { opacity: 1; }
        .ll-node:focus-visible .ll-ring { stroke-width: 3.5; }
        @media (prefers-reduced-motion: reduce) {
          .ll-flow { animation: none; }
          .ll-packet { display: none; }
          .ll-disc, .ll-node, .ll-halo { transition: none; }
        }
      `}</style>

            <svg
                viewBox="0 0 1000 700"
                role="img"
                aria-label="LoanLens serverless architecture. A loan tape uploaded to S3 triggers EventBridge and Step Functions. A Lambda ingests it, models score it, and results land in DynamoDB. API Gateway serves the React frontend, and is fed by a Bedrock reviewer copilot and a Cedar policy gate."
                style={{ width: '100%', height: 'auto', display: 'block' }}
            >
                <defs>
                    <linearGradient id={id('grad')} gradientUnits="userSpaceOnUse" x1="100" y1="0" x2="900" y2="0">
                        <stop offset="0" stopColor="#818cf8" />
                        <stop offset="0.5" stopColor="#a78bfa" />
                        <stop offset="1" stopColor="#34d399" />
                    </linearGradient>
                    {/* hides the road around every station so it reads as stops on a path */}
                    <mask id={id('knock')} maskUnits="userSpaceOnUse" x="0" y="0" width="1000" height="700">
                        <rect width="1000" height="700" fill="white" />
                        {STATIONS.map((s) => (
                            <circle key={s.id} cx={s.x} cy={s.y} r={KNOCKOUT} fill="black" />
                        ))}
                    </mask>
                </defs>

                {/* lane labels */}
                <g fill="currentColor" opacity="0.5" fontSize="13" fontFamily="inherit">
                    <text x="60" y="52">Ingest and score</text>
                    <text x="30" y="258">Serve</text>
                    <text x="30" y="540">Intelligence and governance</text>
                </g>

                {/* the road */}
                <g mask={`url(#${id('knock')})`}>
                    <path d={MAIN_PATH} id={id('road')} fill="none" stroke="currentColor" strokeOpacity="0.05" strokeWidth="34" strokeLinecap="round" />
                    <path d={MAIN_PATH} fill="none" stroke="currentColor" strokeOpacity="0.09" strokeWidth="18" strokeLinecap="round" />
                    <path
                        d={MAIN_PATH}
                        fill="none"
                        stroke={`url(#${id('grad')})`}
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        className="ll-flow"
                    />

                    {BRANCHES.map((b, i) => {
                        const color = COLORS[BY_ID[b.from].kind];
                        return (
                            <g key={b.from}>
                                <path d={b.d} id={id(`br${i}`)} fill="none" stroke="currentColor" strokeOpacity="0.09" strokeWidth="12" strokeLinecap="round" />
                                <path d={b.d} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" className="ll-flow" />
                                <circle r="4" fill={color} className="ll-packet">
                                    <animateMotion dur="2.6s" begin={`${i * 1.1}s`} repeatCount="indefinite">
                                        <mpath href={`#${id(`br${i}`)}`} />
                                    </animateMotion>
                                </circle>
                            </g>
                        );
                    })}

                    {/* packets travelling the whole road */}
                    {[0, 1, 2].map((i) => (
                        <circle key={i} r="4" fill="currentColor" opacity="0.85" className="ll-packet">
                            <animateMotion dur="14s" begin={`${i * 4.7}s`} repeatCount="indefinite">
                                <mpath href={`#${id('road')}`} />
                            </animateMotion>
                        </circle>
                    ))}
                </g>

                {/* stations */}
                {STATIONS.map((s) => {
                    const color = COLORS[s.kind];
                    const on = active !== null && lit.has(s.id);
                    return (
                        <g
                            key={s.id}
                            className={`ll-node${active === s.id ? ' on' : ''}`}
                            tabIndex={0}
                            role="group"
                            aria-label={`${s.title}: ${s.lines.join(', ')}`}
                            opacity={dimmed(s.id) ? 0.25 : 1}
                            onMouseEnter={() => setActive(s.id)}
                            onMouseLeave={() => setActive(null)}
                            onFocus={() => setActive(s.id)}
                            onBlur={() => setActive(null)}
                        >
                            <circle className="ll-halo" cx={s.x} cy={s.y} r={KNOCKOUT} fill={color} fillOpacity="0.14" />
                            <g className="ll-disc">
                                <circle
                                    className="ll-ring"
                                    cx={s.x}
                                    cy={s.y}
                                    r={R}
                                    fill={color}
                                    fillOpacity={on ? 0.24 : 0.14}
                                    stroke={color}
                                    strokeWidth="2"
                                />
                                <g
                                    transform={`translate(${s.x - 18} ${s.y - 18}) scale(1.5)`}
                                    fill="none"
                                    stroke={color}
                                    strokeWidth="1.4"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                >
                                    {ICONS[s.id]}
                                </g>
                            </g>

                            {s.step !== undefined && (
                                <g>
                                    <circle cx={s.x + 27} cy={s.y - 27} r="10" fill={color} />
                                    <text
                                        x={s.x + 27}
                                        y={s.y - 23}
                                        textAnchor="middle"
                                        fontSize="11.5"
                                        fontWeight="700"
                                        fill="#0f172a"
                                        fontFamily="inherit"
                                    >
                                        {s.step}
                                    </text>
                                </g>
                            )}

                            <text x={s.x} y={s.y + 62} textAnchor="middle" fill="currentColor" fontSize="15" fontWeight="600" fontFamily="inherit">
                                {s.title}
                            </text>
                            {s.lines.map((l, i) => (
                                <text
                                    key={l}
                                    x={s.x}
                                    y={s.y + 80 + i * 16}
                                    textAnchor="middle"
                                    fill="currentColor"
                                    opacity="0.62"
                                    fontSize="11.5"
                                    fontFamily="inherit"
                                >
                                    {l}
                                </text>
                            ))}
                        </g>
                    );
                })}

                {/* policy rule under the Cedar station */}
                <g>
                    <rect x="540" y="654" width="340" height="28" rx="14" fill={COLORS.gov} fillOpacity="0.1" stroke={COLORS.gov} strokeOpacity="0.5" />
                    <text
                        x="710"
                        y="672"
                        textAnchor="middle"
                        fill={COLORS.gov}
                        fontSize="12"
                        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                    >
                        {'Junior approves only if risk <= 25% and LTV <= 80'}
                    </text>
                </g>

                {/* serverless note */}
                <g>
                    <rect x="30" y="272" width="270" height="86" rx="14" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeDasharray="4 5" />
                    <g fill="currentColor" opacity="0.6" fontSize="13" fontFamily="inherit">
                        <text x="50" y="303">No idle EC2.</text>
                        <text x="50" y="323">No SageMaker endpoint.</text>
                        <text x="50" y="343">Scales to zero.</text>
                    </g>
                </g>
            </svg>
        </div>
    );
}