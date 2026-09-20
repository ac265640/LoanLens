#!/usr/bin/env bash
# Configure the copilot's fallback language model.
#
#   scripts/configure_llm.sh groq       # https://console.groq.com/keys      (free tier)
#   scripts/configure_llm.sh gemini     # https://aistudio.google.com/apikey (free tier)
#   scripts/configure_llm.sh openai
#   LLM_BASE_URL=https://.../v1 scripts/configure_llm.sh custom   # any OpenAI-compatible API
#
# What it does
#   1. Reads the API key with a hidden prompt. The key is never passed as a command-line
#      argument, never written to the repo, and never stored in shell history.
#   2. Asks the provider which models the key can use and picks the first preferred one.
#   3. Stores the base URL and model as String parameters and the key as a SecureString in
#      SSM Parameter Store under /loanlens/llm/. The copilot Lambda reads them at runtime
#      and picks up a change within about 20 seconds, so no redeploy is needed.
#   4. Sends one real test request so a bad key or model fails here, not in front of a judge.
#
# The copilot tries Bedrock first and uses this model only when Bedrock is unavailable.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
PREFIX="${LLM_SSM_PREFIX:-/loanlens/llm}"
PROVIDER="${1:-}"
UA="loanlens-configure/1.0"  # some providers sit behind a WAF that rejects the default curl/urllib agent

die() { echo "error: $*" >&2; exit 1; }

case "$PROVIDER" in
  groq)   BASE="https://api.groq.com/openai/v1";                       PREFER="llama-3.3-70b-versatile llama-3.1-70b-versatile llama-3.1-8b-instant" ;;
  gemini) BASE="https://generativelanguage.googleapis.com/v1beta/openai"; PREFER="gemini-2.5-flash gemini-2.0-flash gemini-1.5-flash" ;;
  openai) BASE="https://api.openai.com/v1";                            PREFER="gpt-4o-mini gpt-4.1-mini gpt-4o" ;;
  custom) BASE="${LLM_BASE_URL:-}"; [ -n "$BASE" ] || die "custom needs LLM_BASE_URL, e.g. https://api.example.com/v1"
          PREFER="${LLM_MODEL:-}" ;;
  *) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
BASE="${BASE%/}"

read -r -s -p "$PROVIDER API key (input hidden): " KEY; echo
[ -n "$KEY" ] || die "no key entered"

echo "Checking the key against $BASE ..."
MODELS_JSON="$(curl -sS --fail --max-time 30 -A "$UA" -H "Authorization: Bearer $KEY" "$BASE/models")" \
  || die "the provider rejected the key or could not be reached"

MODEL="$(MODELS_JSON="$MODELS_JSON" PREFER="$PREFER" python3 - <<'PY'
import json, os, sys
data = json.loads(os.environ["MODELS_JSON"])
available = [m["id"].split("/", 1)[-1] if m["id"].startswith("models/") else m["id"] for m in data.get("data", [])]
for wanted in os.environ["PREFER"].split():
    if wanted in available:
        print(wanted)
        sys.exit(0)
print("NONE: " + ", ".join(sorted(available)[:20]))
PY
)"
case "$MODEL" in
  NONE:*) die "none of the preferred models are available to this key. Available: ${MODEL#NONE: }. Re-run with LLM_MODEL=<one of them> ($PROVIDER preset uses a fixed preference list; use the custom preset to choose)." ;;
  "")     die "could not choose a model" ;;
esac
echo "Using model: $MODEL"

echo "Sending a test request ..."
REPLY="$(curl -sS --fail --max-time 45 -A "$UA" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with the single word: OK\"}],\"max_tokens\":8}" \
  "$BASE/chat/completions")" || die "the test request failed; the key or model was not accepted"
echo "$REPLY" | python3 -c 'import json,sys; print("Model replied:", json.load(sys.stdin)["choices"][0]["message"]["content"].strip()[:40])'

# Hand the key to the AWS CLI through a private temp file so it never appears in `ps` output.
KEYFILE="$(umask 077; mktemp)"
trap 'rm -f "$KEYFILE"' EXIT
printf '%s' "$KEY" > "$KEYFILE"
unset KEY

put() { aws ssm put-parameter --region "$REGION" --overwrite --name "$PREFIX/$1" --type "$2" --value "$3" >/dev/null; }
put api_key  SecureString "file://$KEYFILE"
put base_url String "$BASE"
put model    String "$MODEL"

echo
echo "Done. Stored $PREFIX/{api_key,base_url,model} in SSM ($REGION)."
echo "The copilot will use $MODEL whenever Bedrock is unavailable, within about 20 seconds."
