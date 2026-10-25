# Growth Command Center validation

Direct URL: `/growth` and `/api/growth_command_center`. JSON: `/api/metrics/growth_command_center`.

This page is not on the main dashboard nav, same pattern as Inbound CAC. It is not on the warm-cache URL list. The handler is GET-only. There is no path that creates, edits, pauses, or budgets an ad.

## Demo fixture (default)

Scope is Nov 1–15, 2026, completed days. As-of is Nov 16, 2026 00:00 America/New_York. The badge stays `SAMPLE DATA`.

| Check | Result |
| --- | --- |
| Spend | $240 = 120 + 80 + 40 |
| Impressions / outbound clicks | 24,000 / 400 |
| Click rate | 400 / 24,000 = 1.666…% → funnel label 1.7% (not 16%) |
| Landing visits / form starts | 320 / 40 |
| Visit → start | 12.5%. Recommendation text reviews that rate and does not call 80% of visitors a non-start. |
| Leads | 8. Daily counts `[0,1,0,1,0,0,1,1,0,1,0,1,1,0,1]` |
| Pace | 20 × 15 / 30 = 10 expected. 8 actual, 2 behind, 40% attained |
| CPL | 240 / 8 = $30, $5 over the $25 goal. Goal line is $25 |
| Demos / demo cost | 4 demos, 240 / 4 = $60, $10 over $50 |
| Sold / sold CPA | 1 distinct contact, 240 / 1 = $240, $40 over $200 |
| Active / rejected | 3 / 0 |
| Spend cap | Not configured |
| Row CPL | Local 120/4 = $30, Solar 80/2 = $40, Homeowner 40/2 = $20 |
| Total CTR / CPL | Recomputed from summed counts, not the average of row rates |

Charts read that same daily spend and lead list. Nov 1 CPL is blank because the lead denominator is 0. Nov 15 cumulative CPL is $30.

## Goals

| Month | Leads created |
| --- | --- |
| 2026-10 | 10 |
| 2026-11 | 20 |
| Any other month | Not configured. November is not copied forward. |

CPL ≤ $25, demo cost ≤ $50, sold CPA ≤ $200. A range that is not one month, and is not a set of complete months, shows pace N/A until a goal month is chosen. Oct 1–Nov 30 uses 10 + 20 = 30.

## Field mapping

| UI metric | Source in demo | Live source |
| --- | --- | --- |
| Ad spend, impressions, outbound clicks | Fixture daily rows. Period totals are the sums. | Read-only Meta insights `GET /{act}/insights` at ad level, `time_increment=1`. Same env as Inbound CAC: `META_ADS_ACCESS_TOKEN`, `META_ADS_ACCOUNT_ID`. Missing env or a failed GET → spend null, status unavailable. |
| Landing visits | Fixture | `web_funnel_daily_v1.visits_total` (else `sessions`) |
| Form starts | Fixture | `estimate_start` (else `starts`). A missing day withholds the total instead of pretending the partial sum is complete. |
| Leads created | Fixture form fills | Live `web_funnel_named_fills_v1` rows that pass `inbound_named_fill_is_live` (test address, test name, and test email excluded). This is not a count of every opportunity on pipeline `7nSEgeoBYXZiIS7x41Jy`. |
| Accepted submissions | Same count as leads in the fixture, all marked delivered | Named-fill count. Delivery to CRM is not inferred from the fill document, so live delivery stays unavailable. |
| Demos | Fixture outcomes on Buffalo `GQtUlcTmLJ61HZjrGEPC`, Rochester `qJNvqKWp8Xc7DaBr8QYc`, Syracuse `etLURrEVxupngZZRlISG`, Virtual `r1b9pwgliYj7WyWBchTV` | Not substituted from calendar demos. Named fills do not carry a GHL contact id, so the cohort join stays `lead_to_crm_contact_join_not_validated`. |
| Sold deals | Distinct `contactId`, Sold Date `P9oBjgbZjJdeE0OkBj9T`, date-only, America/New_York. Stage IDs are the eight Sold and Sale Cancelled IDs from `sales.SalesMetricContract`. Sale Cancelled stays in the count. A missing Sold Date does not count. | Same gap as demos. Calendar sold deals are not divided into the ad spend. |
| CPL | Range spend / leads created | Account or ad spend / named fills when both sources are ok. Otherwise null. |
| Demo cost and sold CPA | Cohort spend / cohort outcomes. Blank when the outcome count is 0. | Null until the contact join is validated. |
| Opp | Not an Overview KPI. An opp is a separate opportunity on the contact in the four territory pipelines only. | Not shown. |

Duplicate flags are excluded from leads. Invalid flags stay in the lead denominator and are counted beside it. Test fills are excluded.

## Live gaps

- Demo is the default. Live is `?mode=live` or Settings → Load live sources.
- The `SAMPLE DATA` badge is removed only for a validated live adapter. Live responses use `LIVE · UNVALIDATED` because this build has not been checked against Ads Manager.
- Effective ad status is not read, so a live active-ad count stays unknown rather than treating every insight row as Active.
- Creative thumbnails in demo are neutral placeholders. Live rows use the same placeholder.
- Bot audit log is not connected. Activity says the log is unavailable.
- Goal editing is not on the page. October and November goals live in `LEADS_GOAL_BY_MONTH`.
- No monthly spend cap is stored. The card says Not configured.

## States checked

- No activity in October 2026: 0 leads, CPL blank, pace 10 behind a goal of 10.
- December 2026: goal not configured.
- Last 30 days from the demo clock: pace N/A.
- Zero demos: demo cost is null, not $0.
- Ad with spend and no lead: CPL is N/A.
- Sale observed after the cutoff: excluded.
- Two sold rows for one contact: one sold deal. Sale Cancelled still counts.
- A demo on the Inbound/Lead Locker pipeline does not count.
- Live loader failure: null KPIs, bot `UNKNOWN`, no fabricated $240.
