"""
Portfolio Read API Lambda
==========================
Backs the dashboard: list/filter loans, fetch one loan, poll a run's status,
and mint a presigned S3 upload URL for the drag-drop "drop a tape" flow.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

LOANS_TABLE = os.environ.get("LOANS_TABLE", "loanlens-loans")
RUNS_TABLE = os.environ.get("RUNS_TABLE", "loanlens-runs")
BUCKET_NAME = os.environ.get("TAPES_BUCKET", "")

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")


def _floatify(obj):
    if isinstance(obj, Decimal):
        # whole numbers stay ints (344, not 344.0); DynamoDB returns every number as Decimal
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _floatify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floatify(v) for v in obj]
    return obj


def _respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=str),
    }


def list_loans(params: dict):
    table = dynamodb.Table(LOANS_TABLE)
    resp = table.scan(Limit=1000)
    items = [_floatify(i) for i in resp.get("Items", [])]

    status_filter = params.get("status")
    min_default = params.get("min_default_prob")
    exceptions_only = params.get("exceptions_only")

    if status_filter:
        items = [i for i in items if i.get("current_status") == status_filter]
    if min_default:
        items = [i for i in items if i.get("prob_next_12m_default", 0) >= float(min_default)]
    if exceptions_only == "true":
        items = [i for i in items if i.get("exception_required") == 1]

    items.sort(key=lambda i: i.get("prob_next_12m_default", 0), reverse=True)

    summary = {
        "total_loans": len(items),
        "high_risk_count": sum(1 for i in items if i.get("prob_next_12m_default", 0) >= 0.20),
        "exception_count": sum(1 for i in items if i.get("exception_required") == 1),
        "total_exposure_usd": round(sum(i.get("current_balance", 0) for i in items), 2),
    }

    return _respond(200, {"summary": summary, "loans": items[:500]})


def get_loan(loan_id: str):
    table = dynamodb.Table(LOANS_TABLE)
    resp = table.get_item(Key={"loan_id": loan_id})
    item = resp.get("Item")
    if not item:
        return _respond(404, {"error": f"loan {loan_id} not found"})
    return _respond(200, _floatify(item))


def get_run(run_id: str):
    table = dynamodb.Table(RUNS_TABLE)
    resp = table.get_item(Key={"run_id": run_id})
    item = resp.get("Item")
    if not item:
        return _respond(200, {"run_id": run_id, "status": "IN_PROGRESS"})
    return _respond(200, _floatify(item))


def create_upload_url():
    key = f"raw/{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}.csv"
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET_NAME, "Key": key, "ContentType": "text/csv"},
        ExpiresIn=300,
    )
    return _respond(200, {"upload_url": url, "bucket": BUCKET_NAME, "key": key})


def handler(event, context):
    route = event.get("resource") or event.get("routeKey", "")
    method = event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}

    if "loans/{loan_id}" in route or "loanId" in path_params or "loan_id" in path_params:
        return get_loan(path_params.get("loan_id") or path_params.get("loanId"))
    if "runs/{run_id}" in route or "run_id" in path_params:
        return get_run(path_params.get("run_id"))
    if "upload-url" in route:
        return create_upload_url()
    if "loans" in route:
        return list_loans(query_params)

    return _respond(404, {"error": "not found"})
