#!/usr/bin/env bash
# Build the dashboard against the deployed API and publish it to Amplify
# Hosting (manual deployment, no git connection needed). Idempotent: creates
# the Amplify app on first run, redeploys on every run after that.
#
#   scripts/deploy_frontend.sh
#
# Env overrides: AWS_REGION, STACK_NAME, AMPLIFY_APP_NAME, AMPLIFY_BRANCH
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Optional overrides (see .env.example). AWS credentials are never read from
# here; the AWS CLI takes them from ~/.aws/credentials or AWS_* variables.
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi

REGION="${AWS_REGION:-us-east-1}"
STACK="${STACK_NAME:-loanlens}"
APP_NAME="${AMPLIFY_APP_NAME:-loanlens}"
BRANCH="${AMPLIFY_BRANCH:-main}"

API_URL="$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)"
[ -n "$API_URL" ] && [ "$API_URL" != "None" ] || { echo "Could not read ApiUrl from stack $STACK" >&2; exit 1; }
echo "API: $API_URL"

(cd "$ROOT/frontend" && VITE_API_URL="$API_URL" npm run build)

APP_ID="$(aws amplify list-apps --region "$REGION" --query "apps[?name=='$APP_NAME'].appId | [0]" --output text)"
if [ -z "$APP_ID" ] || [ "$APP_ID" = "None" ]; then
  echo "Creating Amplify app '$APP_NAME'..."
  APP_ID="$(aws amplify create-app --name "$APP_NAME" --region "$REGION" --query app.appId --output text)"
  aws amplify create-branch --app-id "$APP_ID" --branch-name "$BRANCH" --region "$REGION" >/dev/null
fi

ZIP="$(mktemp -d)/dist.zip"
(cd "$ROOT/frontend/dist" && zip -qr "$ZIP" .)

read -r JOB_ID UPLOAD_URL < <(aws amplify create-deployment --app-id "$APP_ID" --branch-name "$BRANCH" \
  --region "$REGION" --query '[jobId,zipUploadUrl]' --output text)
curl -sS --fail -T "$ZIP" "$UPLOAD_URL"
aws amplify start-deployment --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" --region "$REGION" >/dev/null

for _ in $(seq 1 60); do
  STATUS="$(aws amplify get-job --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" \
    --region "$REGION" --query job.summary.status --output text)"
  echo "deployment: $STATUS"
  case "$STATUS" in
    SUCCEED) echo "Live: https://$BRANCH.$APP_ID.amplifyapp.com"; exit 0 ;;
    FAILED|CANCELLED) echo "Amplify deployment $STATUS" >&2; exit 1 ;;
  esac
  sleep 5
done
echo "Timed out waiting for Amplify deployment" >&2; exit 1
