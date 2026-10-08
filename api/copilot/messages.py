# -*- coding: utf-8 -*-
"""Fixed employee-facing sentences. Do not paraphrase these in callers."""

DISPLAY_NAME = "Goose"
ROLE_NAME = "Happy Solar Data Copilot"
UI_TITLE = "Goose · Happy Solar Data Copilot"

WELCOME = (
    "Ask me about Happy Solar performance, metric definitions, or how the company runs. "
    "What would you like to look at?"
)

SPEND_RESTRICTED = (
    "Marketing spend, including inbound CAC, Lead Locker spend, and cost per lead, "
    "is limited to leadership. I can still look at demos, appointments, sales, and lead sources."
)

SPEND_UNAVAILABLE = (
    "I don't have marketing spend figures in this chat. "
    "I can still look at demos, appointments, sales, and lead sources."
)

SCOPE_DENIAL = (
    "I can help with Happy Solar data, metric definitions, and documented "
    "company operations. Try asking about sales, lead sources, or a performance trend."
)

BUDGET_LIMIT = (
    "The company's monthly AI allowance has been used up. You can still use "
    "the dashboard and the metric dictionary."
)

PAUSED = (
    "Goose is paused right now. You can still use the dashboard and the metric dictionary."
)

NARROW = (
    "That's too much for one question. Try a shorter period, one metric, or a simpler question."
)

NO_APPROVED_DEFINITION = (
    "I do not have an approved definition for that yet."
)

NO_APPROVED_DOCUMENT = (
    "I do not have an approved company document for that."
)

TIMEZONE_UNCONFIRMED = (
    "The company reporting timezone isn't confirmed, so I can't treat those "
    "dates as a reporting period."
)

ROLE_NOT_AUTHORIZED = "This role isn't allowed to use Goose."

EMPLOYEE_UNCONFIRMED = "Goose couldn't confirm an authorized employee for this request."

SESSION_EXPIRED = "Your Goose session expired. Refresh the page."

MODEL_UNAVAILABLE = (
    "I can't reach the language model right now. Any figures below come straight from the reports."
)

WHY_UNKNOWN = "The current data doesn't show why."

LEDGER_UNAVAILABLE = (
    "I can't reach the spending ledger, so I'm not calling the model."
)

RATES_UNAVAILABLE = (
    "Model pricing isn't verified, so I'm not calling the model."
)

QUOTA_ACTIVE = "You already have a question in progress. Give it a second and try again."
QUOTA_COMPANY = "Goose is busy with other questions right now. Try again in a moment."
QUOTA_DAY = "You've reached today's question limit. You can still use the dashboard."
QUOTA_MONTH = "You've reached this month's question limit. You can still use the dashboard."
QUOTA_MINUTE = "That's a lot of questions at once. Wait a minute and try again."

FEEDBACK_SAVED = "Thanks, I saved that for review."
FEEDBACK_FAILED = "I couldn't save that because the ledger is unavailable."
REQUEST_UNREADABLE = "I couldn't read that. Try sending it again."

UNCERTAINTY = (
    "I'm not 100% sure on this one, since {reason}. "
    "If the number looks off, let me know what you meant and I'll recheck."
)


def uncertainty_sentence(reason: str) -> str:
    cleaned = (reason or "").strip().rstrip(".")
    # "I couldn't filter to Rochester, so this is company-wide" is already a sentence.
    # Wrapping it in "since ... so" is the grammar we do not want.
    if cleaned.lower().startswith("i couldn't"):
        return f"{cleaned}. If that number looks off, let me know."
    # "I'm not sure if you mean Pat or Sam. Which rep did you mean?" is already the one line.
    if cleaned.lower().startswith("i'm not sure") or cleaned.lower().startswith("i am not sure"):
        original = (reason or "").strip()
        if original.endswith((".", "?")):
            return original
        return f"{cleaned}."
    return UNCERTAINTY.format(reason=cleaned)
