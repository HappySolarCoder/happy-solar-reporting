# -*- coding: utf-8 -*-

"""Website Funnel metric family.

Lead = a completed form submit (America/New_York):
- Calculator: estimate_submit (name/phone/email in contact-complete)
- /contact-me: wix_form_submit (complete Submit)
- /contact-me counts as a completed form.
- Not a CRM contact. Not a pageview.

Scoreboard: sessions → start → completed form.

Primary:
1. Completed form — volume. Goal: baseline pending (14-day).
2. Sessions → completed form — completed_forms / sessions. Goal 2%.
3. Start → completed form — calculator-only:
   estimate_submit / estimate_start. Goal 25%.
   contact-me has no start; it is in volume and sessions→completed form only.
4. Page contribution — share of completed forms by first page_group.
   No % goal.

Secondary (diagnostic only, not scored this week):
- address-complete and bill-complete drop-off
- sessions → start by surface (site 8%, home 6%, city 12%,
  ny-incentives 10%, calculator-direct 70%)

Warehouse: FIRESTORE_DATABASE_ID collection web_funnel_daily_v1,
one doc per America/New_York date (id YYYY-MM-DD).

Yesterday snapshot (8:00 America/New_York routine):
- GET /api/website_funnel_yesterday reads one daily doc.
- Optional write first: GET /api/web_funnel_rollup (yesterday NY).
- The yesterday read does not auto-rollup.
- Lead for that payload is estimate_submit only (calculator / wny).
- Monthly scoreboard still includes /contact-me wix_form_submit.
- Missing doc or ga4 not_configured/failed → ready=false and nulls.
  Do not invent counts. Do not treat a missing source as 0 traffic.

Cost rules:
- Dashboard month view reads ≤31 daily docs.
- Yesterday read is one document get / get_all. No collection stream.
- Rollup pulls optional GA4 event counts for one NY day.
- Does not read CRM opportunity or contact collections.
- Not on warm_cache. Not hourly.

GA4 (optional):
- Measurement ID G-V02RZFR4SZ (locked). Property 408492342 / stream G-V02RZFR4SZ.
- Yadmada G-VTL7ZW6NPN is on the same property; host allowlist drops it.
- Env GA4_PROPERTY_ID = numeric property id (required to pull traffic).
- Env GA4_SERVICE_ACCOUNT_JSON optional; else FIREBASE_SERVICE_ACCOUNT_JSON.
- If creds/property are missing, write nulls and set ga4="not_configured".
  Do not fake traffic.
- Hold page_view (do not switch sessions to session_start).
- One runReport per day. Dimensions: eventName + pagePath + hostName + pageLocation.

Host / QA exclusions (lock):
- Allowlist only: www.happyslr.com, happyslr.com, wny.happyslr.com.
  Drop Vercel preview hosts, localhost, yadmada.com, gtm-msr.appspot.com,
  everything else.
- Drop events where debug_mode is true (dimension or pageLocation).
- Drop events where traffic_type=internal or URL/session flag internal=1
  (pageLocation query or dimension, if present).
- Drop events at 24 Hawkstone Way (standing lock Evan 2026-08-26).
  Reason test_address. Evan testing, not a live lead. Event-level grain
  matches debug/internal (no sessionId). Case-insensitive, collapsed
  whitespace; extra city/state/zip after the street still matches.
  124 Hawkstone Way is not a match. Scan address, estimate_address,
  customEvent:address, pageLocation, and pagePath. Do not add a second
  runReport. Do not invent a GTM parameter as a new Data API dimension.
- debug_mode and traffic_type are not standard Data API dimensions.
  pageLocation can see ?internal=1 when Designer adds that live flag.
  Do not invent a tester IP list.
- visits_total = page_view on www.happyslr.com + happyslr.com.
- visits_wny = page_view on wny.happyslr.com.
- sessions is kept equal to visits_total (scoreboard / yesterday).
- completed_forms = estimate_submit + wix_form_submit after those filters.
  Preview-host QA forms (Aug 19 estimate_* on *.vercel.app) do not count.
  24 Hawkstone Way rows never count in visits/sessions, estimate_start,
  estimate_address_complete, estimate_bill_complete, estimate_submit,
  wix_form_submit, completed_forms, or the 2-week form-goal score.
"""

from __future__ import annotations

import json
import os
import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

from google.cloud import firestore
from google.oauth2 import service_account

METRIC_NAME = "Website Funnel"
TIMEZONE_NAME = "America/New_York"
DAILY_COLLECTION = "web_funnel_daily_v1"

GA4_MEASUREMENT_ID = "G-V02RZFR4SZ"
GA4_PROPERTY_ID = "408492342"
GA4_PROPERTY_ID_ENV = "GA4_PROPERTY_ID"
GA4_SERVICE_ACCOUNT_JSON_ENV = "GA4_SERVICE_ACCOUNT_JSON"
FIREBASE_SERVICE_ACCOUNT_JSON_ENV = "FIREBASE_SERVICE_ACCOUNT_JSON"

HOST_WWW = "www.happyslr.com"
HOST_APEX = "happyslr.com"
HOST_WNY = "wny.happyslr.com"
LIVE_TOTAL_HOSTS = frozenset({HOST_WWW, HOST_APEX})
LIVE_WNY_HOSTS = frozenset({HOST_WNY})
LIVE_FORM_HOSTS = LIVE_TOTAL_HOSTS | LIVE_WNY_HOSTS
EXCLUDED_HOST_EXAMPLES = (
    "yadmada.com",
    "www.yadmada.com",
    "vercel.app",
    "localhost",
    "gtm-msr.appspot.com",
)
GA4_REPORT_DIMENSIONS = ("eventName", "pagePath", "hostName", "pageLocation")
GA4_MISSING_EXCLUSION_DIMENSIONS = ("debug_mode", "traffic_type")
TEST_ADDRESS_STREET = "24 hawkstone way"
TEST_ADDRESS_LOCK_DATE = "2026-08-26"
TEST_ADDRESS_PATTERN = re.compile(r"(?<!\d)24 hawkstone way")
