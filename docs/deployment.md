# Deployment

Everything is infrastructure as code (AWS SAM). Deploying to your own account takes two commands plus an
optional third for the copilot's fallback model.

## Prerequisites

- An AWS account with credentials configured (`aws configure`), region `us-east-1`
- Docker running (the ingest Lambda is a container image)
- AWS SAM CLI, Node.js 22+, Python 3.12+

## First deploy

```bash
make deploy-backend     # sam build && sam deploy; config is committed in infra/samconfig.toml
make deploy-frontend    # builds against the stack's ApiUrl output and publishes to Amplify Hosting
```

The stack creates the S3 bucket, EventBridge rule, Step Functions state machine, five Lambdas, three DynamoDB tables,
the REST API, the SNS topic and the log groups. `deploy-frontend` creates the Amplify app on first run and sets a
rewrite rule so client-side routes such as `/dashboard` work on a direct hit or refresh.

Check it works: open the printed Amplify URL, go to `/dashboard`, and drop `data/sample/demo_loan_tape.csv` on the upload area.

## Alerts (optional)

The state machine publishes to an SNS topic when a run finds high-risk loans or exceptions. Subscribe an address
(you will get a confirmation email to click):

```bash
aws sns subscribe --region us-east-1 --protocol email --notification-endpoint you@example.com \
  --topic-arn "$(aws cloudformation describe-stacks --stack-name loanlens --region us-east-1 \
       --query "Stacks[0].Outputs[?OutputKey=='AlertTopicArn'].OutputValue" --output text)"
```

## The copilot's language model

The copilot tries Amazon Bedrock first. If your account does not have Bedrock access (new accounts can be blocked
by account verification), configure any OpenAI-compatible model. Groq and Gemini both have free tiers.

```bash
scripts/configure_llm.sh groq      # or: gemini | openai
LLM_BASE_URL=https://api.example.com/v1 scripts/configure_llm.sh custom
```

The script asks for the key with a hidden prompt, checks it and the model with real requests, then stores the
endpoint, model and key (as a SecureString) in SSM Parameter Store. The copilot picks them up within about 20 seconds
without a redeploy. Until a model is available the copilot returns clearly labelled template answers.

## Redeploying

`make deploy-backend` after backend or infrastructure changes, `make deploy-frontend` after frontend changes. Pushing to
GitHub runs CI but does not deploy.

## Tear down

```bash
# CloudFormation cannot delete a non-empty bucket, so empty the tape bucket first
aws s3 rm "s3://loanlens-tapes-$(aws sts get-caller-identity --query Account --output text)-us-east-1" --recursive
cd infra && sam delete --stack-name loanlens --region us-east-1
aws amplify delete-app --app-id "$(aws amplify list-apps --query "apps[?name=='loanlens'].appId | [0]" --output text)"
# the copilot's fallback-model settings are not part of the stack
aws ssm delete-parameters --region us-east-1 --names /loanlens/llm/api_key /loanlens/llm/base_url /loanlens/llm/model
```

SAM also keeps a small `aws-sam-cli-managed-default` stack (artifact bucket and image repository) shared by all your SAM projects.

## Cost

Everything scales to zero and bills per use. There is no idle compute, so a demo weekend costs a few dollars at most
(Lambda, DynamoDB on-demand, API Gateway, Step Functions, S3, Amplify, and Bedrock or the fallback model per call).
Log retention, tape expiry and API throttling exist specifically so nothing can quietly accumulate cost.

## Troubleshooting

**`sam build` hangs at "Setting DockerBuildArgs" with no output.** On macOS this can be Docker's credential helper
blocking (typically a locked keychain), which SAM's Docker client calls before building. Check for stuck processes with
`ps aux | grep docker-credential-desktop`. Either restart Docker Desktop and unlock the keychain, or build with a Docker
config that has no `credsStore` (the base image is public, so no credentials are needed):

```bash
mkdir -p /tmp/dc && python3 -c "import json,os; c=json.load(open(os.path.expanduser('~/.docker/config.json'))); c.pop('credsStore',None); json.dump(c,open('/tmp/dc/config.json','w'))"
ln -sf ~/.docker/contexts /tmp/dc/contexts; ln -sf ~/.docker/cli-plugins /tmp/dc/cli-plugins
DOCKER_CONFIG=/tmp/dc make deploy-backend
```

**Bedrock returns "Your account is currently being verified" or "Operation not allowed".** The AWS account has not
passed Bedrock's verification. This is on the AWS side: open an *Account and billing* support case. The copilot keeps
working through the fallback chain in the meantime.

**A direct link to `/dashboard` returns 404.** Re-run `make deploy-frontend`, which sets the Amplify rewrite rule.

**An upload shows "Pipeline failed".** The message names what is wrong, for example missing columns. The tape must have the
columns of `data/sample/demo_loan_tape.csv`.
