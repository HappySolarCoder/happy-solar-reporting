# Goose · Happy Solar Data Copilot

Goose is the chat name. The role is Happy Solar Data Copilot. The feature ships **off**. `COPILOT_ENABLED` defaults to false, and paid calls stay closed until the launch checks at `/api/copilot/admin` are clear.

This guide is the remaining setup. It does not contain secret values.

## What the code reuses

Starting page: `/api/company_overview`.

The page still loads `/api/metrics/company_snapshot` and `/api/metrics/company_trends`. Those handlers were not modified. Snapshot fans out to the existing sales, opportunities-created, opportunities-ran, and demo-rate metric modules and caches about 60 seconds. Trends cache about 6 hours. The overview cards sum lead-source aliases in the browser.

Goose numeric tools call those same metric modules through `api/copilot/metrics_port.py`. They do not reimplement the formulas and they do not change report responses. Source cards sum the same alias lists the overview uses (`Phones`+`Virtual`, the Self Gen spellings, and the single-label cards).

Company overview itself has no per-employee session. Settings pages use one shared `SETTINGS_PASSWORD` over HTTP basic auth. Goose uses that same password. The username is ignored, so every successful login is the actor `settings_admin`. A `user_id` or `role` in the JSON body is discarded.

The metric modules hardcode `America/New_York`. If `COPILOT_COMPANY_TIMEZONE` is set to anything else, Goose refuses the numeric tools instead of relabeling those results.

## Unresolved business definitions

Every terminology and knowledge seed is **DRAFT**. Approving a seed in the admin UI publishes that text, including the ambiguities listed on the record. Edit the plain-language definition first when the observation is not the policy you want.

| Term | What the code shows | Still needs an owner |
| --- | --- | --- |
| Opp2Prelim | Overview cards use Sales / Ran × 100 and an em dash when Ran is 0. The trend route uses 0.0 when Ran is 0. | Cohort versus period basis. Which zero-denominator rule is policy. |
| Demo Rate | `demo_rate.py` uses sit count / (Sit or No Sit). Overview cards recompute sit/ran and use 0 when Ran is 0. | Confirm sit and ran eligibility. |
| Phones | Overview sums Phones and Virtual. `sales.py` does not fold Virtual into a Phones filter. | Is Virtual an alias everywhere? |
| Self Gen | Overview sums `Self Gen`, `self gen`, `selfgen`, `SelfGen`. | Canonical source id. |
| Doors, Inbound, 3PL | Observed labels. `sc_overview` folds `3pl/inbound` into Inbound. | Business meanings. Do not expand 3PL by guessing. |
| Sales | Distinct contacts in Sold or Sale Cancelled, dated by sold-date field `P9oBjgbZjJdeE0OkBj9T`. | Should Sale Cancelled stay in Sales? |
| Ran | `opportunities_ran.py` counts a non-empty appointment disposition. Demo rate's denominator is Sit or No Sit. | Are those the same set? |
| Sit | Disposition value Sit. The overview label is Demos. | Confirm Sit versus Demo. |
| Created | Overview requests `pipeline_scope=all`. | Qualifying statuses and the event date. |

Knowledge seeds record the same gaps: markets, team structure, lead-to-sale process, sync frequency, and targets are not in the repository. Goose will not answer those until an admin approves a document. Draft documents are excluded from search.

There is no approved company timezone in the repo. Several contracts comment that `America/New_York` is mandatory. The overview default month uses `datetime.utcnow()`.

## Routes

| Route | Purpose |
| --- | --- |
| `POST /api/copilot/chat` | Authenticated chat. Read-only tools only. |
| `GET /api/copilot/status` | Enabled flag, pause flag, and launch problems. No model call. |
| `GET/POST /api/copilot/admin` | Dictionary, knowledge, ledger, pause. Settings password. |
| `POST /api/copilot/feedback` | Stores a review item. Does not change definitions. |

Chat tools: `get_metric_definition`, `get_company_summary`, `compare_periods`, `get_source_performance`, `get_supporting_records`, `search_company_knowledge`. There is no SQL, shell, web, or write tool.

## Environment variables

Set these in the Vercel project. Do not commit them.

| Name | Rule |
| --- | --- |
| `COPILOT_ENABLED` | Leave unset or `false` until launch checks pass. |
| `COPILOT_COMPANY_TIMEZONE` | IANA zone the owner approves. Required before dates are treated as reporting periods. |
| `COPILOT_BILLING_TIMEZONE` | IANA zone of the Google billing month. Required. This is not inferred. |
| `COPILOT_ALLOWED_ROLES` | `settings_admin` matches the only role this app can prove. Do not invent finer roles. |
| `COPILOT_RANKING_ROLES` | Leave empty. Owner and setter rankings stay out of the model payload. |
| `GOOGLE_CLOUD_PROJECT` | Dedicated inference project. Do not reuse `GCP_PROJECT_ID` for this. |
| `GOOGLE_CLOUD_LOCATION` | `global`, matching the pinned rate card. |
| `COPILOT_MODEL_ID` | `gemini-3.1-flash-lite`. Any other id disables paid calls. |
| `COPILOT_GOOGLE_CREDENTIALS_JSON` | Inference service-account JSON. Inference permission only. Not the Firestore admin key. |
| `COPILOT_MONTHLY_MODEL_USD` | Defaults to 15. Cannot be raised above 15 by env. |
| `COPILOT_INCREMENTAL_NON_MODEL_USD` | Other new monthly cost. The model cap shrinks so model plus this stays within 20. |
| `COPILOT_OUTPUT_CAP_ENFORCED` | Leave false until an owner proves `max_output_tokens` caps response plus reasoning. |
| `FIREBASE_SERVICE_ACCOUNT_JSON`, `GCP_PROJECT_ID`, `FIRESTORE_DATABASE_ID` | Existing data-center Firestore. Required for the ledger. Missing values fail closed. |
| `SETTINGS_PASSWORD` | Existing settings gate. Required for chat and admin. |

`COPILOT_STORE=memory` is for local tests only. Production must not set it.

## Model and rates

Pinned on 4 October 2026 from Google Cloud Agent Platform pricing:

- Model: `gemini-3.1-flash-lite`
- Location: `global`
- Input: USD 0.25 / 1M tokens
- Output, including reasoning: USD 1.50 / 1M tokens
- Documented max output: 65,536 tokens
- Thinking: `thinking_level=MINIMAL` (`thinking_budget` is not used)
- Rate version: `vertex-gemini-3.1-flash-lite-global-2026-10-04`
- Review expires: 2026-11-03

The illustrative brief prices (USD 1.50 input / USD 9 output) are not the rates in code. At the verified rates, one worst-case call with a 65,536 output ceiling fits under the USD 0.15 turn cap. Three calls do not. Paid turns therefore reserve one call until `COPILOT_OUTPUT_CAP_ENFORCED=true` is justified. After 2026-11-03 the rate card is expired and paid calls stop.

Accounting is integer micro-USD. The server reserves the upper bound, with a 25% margin, in one ledger transaction before the provider call. Unknown usage keeps the reservation. The client cannot raise the cap.

## Firestore collections

No SQL migration. The existing Firestore database gains these collections on first write:

`copilot_ledger`, `copilot_reservations`, `copilot_quota`, `copilot_active`, `copilot_revisions`, `copilot_audit`, `copilot_conversations`, `copilot_config`, `copilot_preferences`, `copilot_idempotency`, `copilot_feedback`, `copilot_suggestions`, `copilot_terminology`, `copilot_knowledge`.

Seed drafts without approving them:

```bash
python scripts/copilot_seed.py
python scripts/copilot_seed.py --apply
```

`--apply` skips documents that are already `APPROVED`. Chat reads the JSON seeds plus `copilot_revisions`, so the admin approval path works even before the seed script runs. The script is the idempotent copy into Firestore.

## Google Cloud checklist

1. Create a dedicated inference project. Enable the Vertex AI / Gemini API and attach billing.
2. Confirm `gemini-3.1-flash-lite` is offered in `global` and that the prices above are still current. If they moved, update `api/copilot/rates.py` and set a new review date. Do not point `COPILOT_MODEL_ID` at a floating alias.
3. Create a runtime service account with only the inference permission the Gen AI SDK needs. Do not grant project owner or billing admin.
4. Store its JSON in `COPILOT_GOOGLE_CREDENTIALS_JSON`. Do not commit it. Do not reuse the Firestore service account for inference.
5. If the billing account supports spend caps, set a USD 18 cap on the inference service as backup. Google treats spend caps as a preview, they are not instant, and they are not the primary stop. The ledger is the primary stop.
6. Record the billing timezone in `COPILOT_BILLING_TIMEZONE`. A provider cap can stay tripped after the app month rolls; lifting it is a console action.

## Enable, pause, rollback

1. Open `/api/copilot/admin` with the settings password.
2. Save draft definitions, then approve only the metrics that should answer numbers. Approve knowledge documents the same way.
3. Set the timezone and project variables. Leave `COPILOT_ENABLED` false and read the launch-check list.
4. When that list is empty, set `COPILOT_ENABLED=true` and redeploy that env change. This pull request does not deploy production.
5. Pause from the admin page sets `copilot_config/runtime.paused`. The dashboard keeps working. Clearing pause does not enable the feature by itself.
6. Rollback of a bad prompt or knowledge revision is a new revision, or `COPILOT_ENABLED=false`. Do not delete `copilot_ledger`, `copilot_reservations`, or `copilot_audit`.

## Tests

```bash
python -m unittest tests.test_copilot
```

Budget and security tests use an in-memory ledger and a fake model. They do not call Google.

## Remaining owner decisions

- Dedicated inference project id, and a least-privilege service account JSON in `COPILOT_GOOGLE_CREDENTIALS_JSON`.
- Confirm `COPILOT_COMPANY_TIMEZONE`. The metric code assumes `America/New_York` until you say otherwise.
- Confirm `COPILOT_BILLING_TIMEZONE` against the Google billing account.
- Approve, edit, or leave draft each terminology row. Unapproved metrics return no figure.
- Decide Sale Cancelled inside Sales, Virtual inside Phones, the 3PL expansion, and Opp2Prelim's zero-denominator rule before approving those rows.
- Approve company-profile and process documents, or leave those questions unanswered.
- Set the USD 18 inference spend cap in Google billing if the account allows it.
- Re-verify the rate card before 2026-11-03.
- Name the agent owner, data owner, and budget admin. One person can hold more than one of those.
