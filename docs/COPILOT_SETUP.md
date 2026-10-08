# Goose · Happy Solar Data Copilot

Goose is the chat name. The role is Happy Solar Data Copilot. The feature ships **off**. `COPILOT_ENABLED` defaults to false, and paid calls stay closed until the launch checks at `/api/copilot/admin` are clear.

This guide is the remaining setup. It does not contain secret values.

## What the code reuses

Starting page: `/api/company_overview`.

The page still loads `/api/metrics/company_snapshot` and `/api/metrics/company_trends`. Snapshot fans out to the existing sales, opportunities-created, opportunities-ran, and demo-rate metric modules and caches about 60 seconds. Trends cache about 6 hours. Opp2Prelim on the trend is null when Ran is 0, matching the blank card. The sales contract is unchanged. The overview cards sum lead-source aliases in the browser.

Goose numeric tools call those same metric modules through `api/copilot/metrics_port.py`. They do not reimplement the formulas and they do not change report responses. Source cards sum the same alias lists the overview uses (`Phones`+`Virtual`, the Self Gen spellings, and the single-label cards).

Direct dashboard and admin use still share one `SETTINGS_PASSWORD` over HTTP basic auth. The username is ignored, so that login is the actor `settings_admin`. A `user_id` or `role` in the JSON body is discarded.

Company Overview is also framed inside Bloom Data Center. Bloom's `hs_session` cookie is httpOnly and does not cross into this origin, and Bloom does not use Firebase. The framed Goose panel asks the Bloom parent for a short-lived HMAC token (`postMessage`, type `happy-solar-goose`) and sends it as `Authorization: Bearer`. Reporting verifies that token with `COPILOT_BLOOM_TOKEN_SECRET`. The signed portal role is used when it is already listed in `COPILOT_ALLOWED_ROLES`. Otherwise an active employee is mapped to `settings_admin` when that role is listed. The actor id is `bloom:<user id>`, not the admin actor. Bearer does not open `/api/copilot/admin`. Unset the shared secret to turn the Bloom path off without touching the password path.

`COPILOT_COMPANY_TIMEZONE` defaults to `America/New_York`. That zone was approved on 2026-10-04. Company overview dates, filter chips, and Goose answer periods use it. They do not use the server clock or UTC. `COPILOT_BILLING_TIMEZONE` is still unset. Do not copy America/New_York into it.

## Unresolved business definitions

Every terminology and knowledge seed is **DRAFT**. Approving a seed in the admin UI publishes that text, including the ambiguities listed on the record. Edit the plain-language definition first when the observation is not the policy you want.

| Term | What the code shows | Still needs an owner |
| --- | --- | --- |
| Opp2Prelim | Cards and the trend chart leave the rate blank when Ran is 0. | Still draft. The blank-versus-zero note is not approved policy. Cohort versus period is still open. |
| Demo Rate | Zero denominator is N/A. Labels say demo, demos, demo rate, or no demo. | Still draft. The raw disposition value Sit is data only. |
| Phones | Virtual belongs in Phones. The demo-rate normalizer maps Virtual and virt to Phones, and the overview card adds Phones and Virtual. | Still draft. Do not treat them as separate sources. The row is not approved. |
| Self Gen | Canonical Lead Gen Source string is `Self Gen`. Other casings are the same source. | Still draft. |
| Doors | Observed label. | Still draft. |
| Inbound | Overview card key is Inbound. | Still draft. Do not use the paid-social Inbound lead rule as this definition. |
| 3PL | Observed label. | Still draft. Do not define the acronym. |
| Sales | Existing dashboards include Sold and Sale Cancelled, sold date `P9oBjgbZjJdeE0OkBj9T`, date-only, distinct contactId, America/New_York. That contract is unchanged. | Still draft. Do not state the note as new policy. |
| Ran | Non-empty appointment disposition in `opportunities_ran.py`. | Still draft. |
| Demo | Labels say demo. Raw value Sit stays in the data. | Still draft. |
| Created | Overview requests `pipeline_scope=all`. | Still draft. |

Knowledge seeds record the same gaps: markets, team structure, lead-to-sale process, sync frequency, and targets are not in the repository. Goose will not answer those until an admin approves a document. Draft documents are excluded from search.

The company reporting timezone is `America/New_York` as of 2026-10-04. The Google billing timezone is not approved.

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
| `COPILOT_ENABLED` | Stays false. Do not turn it on from this change. |
| `COPILOT_COMPANY_TIMEZONE` | Defaults to `America/New_York`. Approved 2026-10-04. |
| `COPILOT_BILLING_TIMEZONE` | Leave unset. The Google billing period timezone is not verified. |
| `COPILOT_ALLOWED_ROLES` | When unset or empty, chat allows `settings_admin`, `fma`, `closer`, `coach`, `manager`, and `inbound`. An explicit list replaces that default. `settings_admin` is the password actor. Portal roles Bloom can prove are `fma`, `closer`, `coach`, `manager`, and `inbound`. Chat keeps a portal role only when that role is listed. If it is not listed, an active Bloom employee maps to `settings_admin` when `settings_admin` is listed. That mapping does not open admin. Do not add a role the token did not prove. |
| `COPILOT_RANKING_ROLES` | Leave empty. Owner and setter rankings stay out of the model payload. Do not put `settings_admin` here, or Bloom employees mapped onto that role would receive rankings. The allowed-role default does not copy `settings_admin` into this list. |
| `GOOGLE_CLOUD_PROJECT` | Dedicated inference project. Do not reuse `GCP_PROJECT_ID` for this. |
| `GOOGLE_CLOUD_LOCATION` | `global`, matching the pinned rate card. |
| `COPILOT_MODEL_ID` | `gemini-3.1-flash-lite`. Any other id disables paid calls. |
| `COPILOT_GOOGLE_CREDENTIALS_JSON` | Inference service-account JSON. Inference permission only. Not the Firestore admin key. |
| `COPILOT_MONTHLY_MODEL_USD` | Defaults to 15. Cannot be raised above 15 by env. |
| `COPILOT_INCREMENTAL_NON_MODEL_USD` | Other new monthly cost. The model cap shrinks so model plus this stays within 20. |
| `COPILOT_OUTPUT_CAP_ENFORCED` | Leave false until an owner proves `max_output_tokens` caps response plus reasoning. |
| `FIREBASE_SERVICE_ACCOUNT_JSON`, `GCP_PROJECT_ID`, `FIRESTORE_DATABASE_ID` | Existing data-center Firestore. Required for the ledger. Missing values fail closed. |
| `SETTINGS_PASSWORD` | Existing settings gate. Required for admin, and for chat on the direct dashboard. |
| `COPILOT_BLOOM_TOKEN_SECRET` | Shared HMAC secret with `happy-solar-bloom-portal`. Set the same value on both Vercel projects. Do not commit it. Unset rejects Bearer and leaves basic auth working. |
| `COPILOT_BLOOM_ORIGINS` | Comma-separated HTTPS parent origins that may post the Goose token. Default `https://happy-solar-bloom-portal.vercel.app`. No wildcards. |

`COPILOT_STORE=memory` is for local tests only. Production must not set it.

## Bloom token

Bloom mints the token. This app only verifies it. There is no Firebase project in Bloom auth.

The parent listens for `postMessage` from the reporting iframe:

```json
{ "type": "happy-solar-goose", "action": "request-token" }
```

It answers only that iframe, and only when `event.origin` is the reporting origin:

```json
{ "type": "happy-solar-goose", "action": "token", "token": "<hmac>", "expiresAt": 0, "note": "" }
```

`expiresAt` is unix milliseconds. `note` is optional. When it is non-empty, the panel shows that text under the subtitle. While an admin is viewing someone else, Bloom sends `Goose answers as you (Evan), not as Rueben while viewing.`

When Bloom cannot mint a token, it posts a reason and the panel shows that reason without calling chat:

```json
{ "type": "happy-solar-goose", "action": "token-unavailable", "reason": "This role is not authorized to use Goose." }
```

The iframe accepts `token` and `token-unavailable` only when `event.origin` is an allowed Bloom parent. The token itself is `base64url(json).base64url(hmac-sha256)`. The JSON keys, sorted, are `aud`, `exp`, `iat`, `iss`, `role`, `status`, `sub`, and `v`.

Chat answers a missing credential with `Goose could not confirm an authorized employee for this request.` A bearer whose role is outside the allowed list gets `This role is not authorized to use Goose.` A bad or expired signature gets `Your Goose session expired. Refresh the page.`

| Claim | Value |
| --- | --- |
| `iss` | `happy-solar-bloom` |
| `aud` | `goose-copilot` |
| `v` | `1` |
| `sub` | Bloom user id. Stored as actor `bloom:<sub>`. |
| `role` | `fma`, `closer`, `coach`, `manager`, or `inbound`. Not `settings_admin`. |
| `status` | `active` |
| `iat`, `exp` | Unix seconds. Lifetime at most 10 minutes. Bloom mints 5 minutes. |

The sibling change in `HappySolarCoder/happy-solar-bloom-portal` is `lib/goose-token.ts`, `lib/goose-token.test.ts`, `app/api/goose-token/route.ts`, `components/data-center.tsx`, and `components/frame-stage.tsx`. Bloom's env var is the same `COPILOT_BLOOM_TOKEN_SECRET`. Optional `NEXT_PUBLIC_GOOSE_REPORTING_ORIGINS` adds preview reporting origins next to `https://database-migration-chi.vercel.app`. Both pull requests have to be deployed, and the shared secret has to be set, before a signed-in Bloom employee can chat. Rollback of this path is reverting those pull requests or unsetting the secret.

## Model and rates

Public list price read on 4 October 2026. This is not approval to spend and not a permanent pin. Recheck the card before launch. Grounding, image, audio, and a floating latest alias stay off. Paid calls fail closed without `COPILOT_GOOGLE_CREDENTIALS_JSON`.

Pinned from that read:

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
6. Leave `COPILOT_BILLING_TIMEZONE` unset until the Google billing period timezone is verified. Do not copy `America/New_York` into it. A provider cap can stay tripped after the app month rolls; lifting it is a console action.

## Enable, pause, rollback

1. Open `/api/copilot/admin` with the settings password.
2. Save draft definitions, then approve only the metrics that should answer numbers. Approve knowledge documents the same way.
3. Set the inference project variables. Leave `COPILOT_BILLING_TIMEZONE` unset and `COPILOT_ENABLED` false, then read the launch-check list.
4. When that list is empty, set `COPILOT_ENABLED=true` and redeploy that env change. This pull request does not deploy production.
5. Pause from the admin page sets `copilot_config/runtime.paused`. The dashboard keeps working. Clearing pause does not enable the feature by itself.
6. Rollback of a bad prompt or knowledge revision is a new revision, or `COPILOT_ENABLED=false`. Do not delete `copilot_ledger`, `copilot_reservations`, or `copilot_audit`.

## Tests

```bash
python -m unittest tests.test_copilot
```

Budget and security tests use an in-memory ledger and a fake model. They do not call Google.

## Remaining owner decisions

- Dedicated inference project id, and a least-privilege service account JSON in `COPILOT_GOOGLE_CREDENTIALS_JSON`. Without it, paid calls stay closed.
- `COPILOT_BILLING_TIMEZONE` is not approved. Leave it unset until the Google billing period timezone is verified.
- Terminology rows stay DRAFT. The 2026-10-04 notes are on those drafts and are not approval.
- Approve company-profile and process documents, or leave those questions unanswered.
- Set the USD 18 inference spend cap in Google billing if the account allows it.
- Recheck the 2026-10-04 rate card before launch. It is not a permanent pin.
- `COPILOT_ENABLED` stays false.
- Name the agent owner, data owner, and budget admin. One person can hold more than one of those.
