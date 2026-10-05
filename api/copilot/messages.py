# -*- coding: utf-8 -*-
"""Fixed employee-facing sentences. Do not paraphrase these in callers."""

DISPLAY_NAME = "Goose"
ROLE_NAME = "Happy Solar Data Copilot"
UI_TITLE = "Goose · Happy Solar Data Copilot"

WELCOME = (
    "Ask me about Happy Solar performance, metric definitions or documented "
    "company operations. I use the data you are authorized to view. What would "
    "you like to understand?"
)

SCOPE_DENIAL = (
    "I can help with Happy Solar data, metric definitions and documented "
    "company operations. Try asking about sales, lead sources or a performance "
    "trend."
)

BUDGET_LIMIT = (
    "The company's monthly AI allowance has been reached. You can still use "
    "the dashboard and metric dictionary."
)

PAUSED = (
    "Goose is paused. You can still use the dashboard and metric dictionary."
)

NARROW = (
    "That request is too large for one turn. Narrow the period, the metric, "
    "or the question and try again."
)

NO_APPROVED_DEFINITION = (
    "I do not have an approved definition for that yet."
)

NO_APPROVED_DOCUMENT = (
    "I do not have an approved company document for that."
)

TIMEZONE_UNCONFIRMED = (
    "The company reporting timezone is not confirmed, so I cannot treat those "
    "dates as a reporting period."
)

SIGN_IN_REQUIRED = (
    "Goose can only answer for a signed-in authorized employee. This dashboard "
    "does not have per-employee sign-in yet."
)

MODEL_UNAVAILABLE = (
    "The language model is not connected. Figures below, when present, come "
    "only from the reporting functions."
)

WHY_UNKNOWN = "The current data does not establish why."

LEDGER_UNAVAILABLE = (
    "I cannot reach the spending ledger, so I am not calling the model."
)

RATES_UNAVAILABLE = (
    "Model pricing is not verified, so I am not calling the model."
)
