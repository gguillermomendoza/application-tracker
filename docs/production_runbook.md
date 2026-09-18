# Job Application Agent — Production Runbook

## Production Architecture

```text
Cloud Scheduler
→ Cloud Run Job
→ Gmail / Sheets OAuth
→ Vertex AI
→ deterministic decision engine
→ Google Sheets / Firestore
→ exit
```

Cloud Run is a one-shot Job, not an HTTP service.

## Production Resources

```text
Project:
job-application-tracker-508819

Region:
us-west2

Cloud Run Job:
job-application-agent

Scheduler:
job-application-agent-every-15-min

Runtime service account:
job-application-agent-runner@job-application-tracker-508819.iam.gserviceaccount.com

Scheduler service account:
job-agent-scheduler@job-application-tracker-508819.iam.gserviceaccount.com

Firestore database:
(default)

Firestore collections:
processed_messages
review_queue
```

## Scheduler

The production schedule is:

```text
*/15 10-21 * * MON-FRI
```

Timezone:

```text
America/Los_Angeles
```

This runs every 15 minutes from 10:00 AM through 9:45 PM Pacific Time, Monday through Friday.

Check Scheduler configuration:

```powershell
gcloud scheduler jobs describe job-application-agent-every-15-min `
  --location=us-west2 `
  --project=job-application-tracker-508819 `
  --format="yaml(schedule,timeZone,state)"
```

## Manually Run the Agent

```powershell
gcloud run jobs execute job-application-agent `
  --region=us-west2 `
  --project=job-application-tracker-508819 `
  --wait
```

A healthy run should ultimately produce:

```text
run_started
run_succeeded
```

and the Cloud Run execution should succeed.

## Inspect Recent Cloud Run Executions

```powershell
gcloud run jobs executions list `
  --job=job-application-agent `
  --region=us-west2 `
  --project=job-application-tracker-508819
```

Inspect a particular execution:

```powershell
gcloud run jobs executions describe EXECUTION_NAME `
  --region=us-west2 `
  --project=job-application-tracker-508819
```

## Inspect Execution Logs

Structured application events include:

```text
run_started
run_succeeded
run_failed
extraction_failed
message_skipped_already_processed
message_extracted
decision_made
write_intent_prepared
decision_handling_failed
```

Query application lifecycle logs:

```text
resource.type="cloud_run_job"
resource.labels.job_name="job-application-agent"
jsonPayload.event=*
```

Query fatal run failures:

```text
resource.type="cloud_run_job"
resource.labels.job_name="job-application-agent"
jsonPayload.event="run_failed"
```

Query extraction failures:

```text
resource.type="cloud_run_job"
resource.labels.job_name="job-application-agent"
jsonPayload.event="extraction_failed"
```

Production logs should not routinely contain email subjects, sender addresses, raw email bodies, company names, or role names.

## Failure Semantics

### Extraction failure

```text
extraction failure
→ no Sheet write
→ Gmail message NOT marked processed
→ batch continues
→ message can retry on a future run
```

A single extraction failure is not a fatal batch failure.

Repeated extraction failures are monitored separately.

### Decision/write failure

```text
Sheet write failure
or
review persistence failure
→ message NOT marked processed
→ eligible for retry
```

### Fatal orchestration failure

Examples:

```text
configuration failure
OAuth credentials unavailable
fatal Gmail API failure
fatal Sheets API failure
Firestore persistence failure
unhandled orchestration exception
container/runtime failure
```

Fatal failures must propagate and cause:

```text
run_failed
→ nonzero process exit
→ failed Cloud Run execution
```

## REVIEW Semantics

```text
ambiguous
→ REVIEW

not
→ guess
```

Gemini interprets email content.

Deterministic Python controls:

```text
validation
matching
duplicate detection
CREATE / UPDATE / REVIEW / IGNORE
writes
```

REVIEW cases must not be automatically resolved.

## Monitoring and Alerts

Three production alert layers exist.

### Cloud Run execution failure

Policy:

```text
Job Application Agent - Cloud Run execution failed
```

Detects failed Cloud Run Job executions.

### Repeated extraction failures

Policy:

```text
Job Application Agent - Repeated extraction failures
```

Metric:

```text
logging.googleapis.com/user/job_agent_extraction_failures
```

Semantics:

```text
1 failure in 30 minutes → no alert
2 failures in 30 minutes → no alert
3+ failures in 30 minutes → alert
```

### Scheduler invocation failure

Policy:

```text
Job Application Agent - Scheduler invocation failed
```

This catches failures that happen before Cloud Run creates an execution.

Relevant Scheduler log filter:

```text
resource.type="cloud_scheduler_job"
AND resource.labels.job_id="job-application-agent-every-15-min"
AND jsonPayload."@type"="type.googleapis.com/google.cloud.scheduler.logging.AttemptFinished"
AND severity>=ERROR
```

## Distinguishing Failure Types

If Scheduler reports an error and no Cloud Run execution exists:

```text
Scheduler / invocation problem
```

Investigate Scheduler authentication, target configuration, and permissions.

If a Cloud Run execution exists and fails:

```text
Cloud Run / application problem
```

Inspect:

```text
run_failed
error_type
container exit status
```

If Cloud Run succeeds but repeated `extraction_failed` events occur:

```text
Vertex / extraction problem
```

The affected messages remain unprocessed and retry later.

## OAuth Boundaries

### Gmail

Only:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Never grant:

```text
send
compose
modify
delete
label
```

The Gmail account is determined by the OAuth token at:

```text
GMAIL_TOKEN_PATH
```

It is not determined by the Cloud deployer or runtime service account.

### Sheets

Read:

```text
https://www.googleapis.com/auth/spreadsheets.readonly
```

Write:

```text
https://www.googleapis.com/auth/spreadsheets
```

Read and write OAuth credentials remain separate.

### Google Cloud APIs

Vertex AI and Firestore use Application Default Credentials from the runtime service account.

Do not use production service-account JSON keys.

Do not set:

```text
GOOGLE_APPLICATION_CREDENTIALS
```

in production.

## Production Secret Mounts

```text
/secrets/oauth-client/credentials.json
/secrets/gmail/token.json
/secrets/sheets-read/token.json
/secrets/sheets-write/token.json
```

Environment variables:

```text
GOOGLE_OAUTH_CLIENT_SECRETS_PATH=/secrets/oauth-client/credentials.json
GMAIL_TOKEN_PATH=/secrets/gmail/token.json
SHEETS_READONLY_TOKEN_PATH=/secrets/sheets-read/token.json
SHEETS_WRITE_TOKEN_PATH=/secrets/sheets-write/token.json
```

Never commit OAuth credentials or include them in the container image.

## Firestore

Production backend:

```text
PROCESSED_MESSAGE_BACKEND=firestore
```

Production collections:

```text
processed_messages
review_queue
```

Durable persistence failures must fail closed.

Never switch production back to local JSON persistence.

## Verify Alert Policies

```powershell
gcloud monitoring policies list `
  --project=job-application-tracker-508819 `
  --format="table(displayName,enabled)"
```

Expected policies:

```text
Job Application Agent - Cloud Run execution failed
Job Application Agent - Repeated extraction failures
Job Application Agent - Scheduler invocation failed
```

## Deployment

Build a versioned image:

```powershell
$IMAGE="us-west2-docker.pkg.dev/job-application-tracker-508819/job-application-agent/job-application-agent:TAG"

gcloud builds submit `
  --tag=$IMAGE `
  --project=job-application-tracker-508819
```

Deploy:

```powershell
gcloud run jobs update job-application-agent `
  --image=$IMAGE `
  --region=us-west2 `
  --project=job-application-tracker-508819
```

Smoke-test:

```powershell
gcloud run jobs execute job-application-agent `
  --region=us-west2 `
  --project=job-application-tracker-508819 `
  --wait
```

Only treat the deployment as complete after a successful smoke test.

## Rollback

List recent images:

```powershell
gcloud artifacts docker images list `
  us-west2-docker.pkg.dev/job-application-tracker-508819/job-application-agent `
  --include-tags
```

Select a previously known-good image and update the Job:

```powershell
gcloud run jobs update job-application-agent `
  --image=KNOWN_GOOD_IMAGE `
  --region=us-west2 `
  --project=job-application-tracker-508819
```

Then manually execute the Job and verify success.

## Safety Invariants

Never:

```text
broaden Gmail OAuth
allow Gmail sending or modification
store raw email bodies
commit OAuth secrets
bundle OAuth files into Docker
create service-account JSON keys
allow Gemini to decide matches
allow Gemini to choose CREATE or UPDATE
allow Gemini to write
lower confidence thresholds to avoid REVIEW
auto-resolve REVIEW
mark messages processed after failed durable persistence
make one extraction failure abort the entire batch
turn the workload into an HTTP server
replace Cloud Scheduler with an always-running process
```

Core rule:

```text
Gemini interprets.
Python decides.
Python validates.
Python writes.
```

