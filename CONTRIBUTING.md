# Contributing

## Frontend (no AWS account needed)

The dashboard runs against the deployed API, so frontend work needs no AWS
credentials.

```bash
git clone https://github.com/ac265640/LoanLens.git
cd LoanLens/frontend
cp .env.example .env     # points the dev server at the deployed API (gitignored)
npm ci
npm run dev              # http://localhost:5173
npm run build            # tsc type-check + production build; run before pushing
```

| Path | What it holds |
|---|---|
| `src/Root.tsx` | App shell: router (`/` landing page, `/dashboard`), navigation pill, light/dark theme |
| `src/pages/` | `Home` (landing), `ArchitectureDiagram`, `HexBackground` |
| `src/App.tsx` | The dashboard itself (route `/dashboard`) |
| `src/api.ts` | Typed API client, response types, the LTV-band to integer helper the Cedar gate needs |
| `src/components/` | `PortfolioTable`, `LoanDrawer`, `ShockwavePanel`, `CopilotChat`, `CoverageCard`, `UploadDropzone`, `RiskBadge`, `RichText` (safe renderer for the copilot's markdown) |
| `src/index.css` | Design tokens for both themes (CSS variables under `[data-theme]`) and shared surface styles |

To see loans in the dashboard, drop `data/sample/demo_loan_tape.csv` on the upload area.

## Workflow

- Commit with your own git identity. The email must be one attached to your GitHub
  account for the commits to count as your contributions:
  `git config user.name "..." && git config user.email "..."`.
- Branch from `main`, keep commits small, and open a pull request into `main`.
- Commit messages follow Conventional Commits with a technical subject:
  `feat(ui): ...`, `fix(ui): ...`, `refactor(ui): ...`, `test: ...`.
- Pushing to GitHub does not deploy anything. The live site is published manually with
  `scripts/deploy_frontend.sh`, which needs the account owner's AWS credentials.

## Secrets

Never commit credentials. `.env`, `.env.*` (except `*.example`), key files and IAM access-key
CSV exports are gitignored. AWS credentials belong in `~/.aws/credentials`
(`aws configure`) or `AWS_*` environment variables, never in the repo.

## Checks

```bash
make test         # pytest: feature engineering, rules, splitter, DynamoDB writes, portfolio API
make cedar-test   # Cedar authorization policies
```
