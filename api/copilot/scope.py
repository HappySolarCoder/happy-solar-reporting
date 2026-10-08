# -*- coding: utf-8 -*-
"""Deterministic scope checks. Ambiguous company questions clarify; they do not call a model."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from copilot.periods import (
    TimezoneUnconfirmed,
    _relative_period_wins,
    applied_period_covers,
    implied_current_range,
    message_names_explicit_month,
    month_spans_covering,
    named_calendar_range,
    named_period_unserved,
    quarter_spans_covering,
    _FULL_MONTH_NUMBERS,
    _within_one_edit,
)


ALLOWED_INTENTS = frozenset(
    {
        "greeting",
        "help",
        "definition",
        "company_summary",
        "compare",
        "source_performance",
        "knowledge",
        "challenge",
        "clarify",
        "deny",
        "mixed",
    }
)

_DENY_PATTERNS = (
    r"\bignore (your |all |previous |the )?(rules|instructions|policy)\b",
    r"\bscreenplay\b",
    r"\bhomework\b",
    r"\bpoem\b",
    r"\bjoke\b",
    r"\brecipe\b",
    r"\bwrite (me )?(a |an )?(story|novel|song|essay|email to)\b",
    r"\bsolve my\b",
    r"\bpersonal advice\b",
    r"\bwho should i vote\b",
    r"\bpython script\b",
    r"\bwrite (the )?code\b",
    r"\bdrop table\b",
    r"\bselect \* from\b",
    r"\bunion select\b",
    r"\breveal (your |the )?(system prompt|hidden instructions|secrets)\b",
    r"\banother team'?s private\b",
    r"\bshow (me )?(all )?private records\b",
    r"\bexport the database\b",
    r"\bignore previous instructions\b",
)

_SUBSTANTIVE = re.compile(
    r"\b(sales|sale|ran|sit|sits|demo|demos|opp2prelim|opp|opps|opportunity|opportunities|"
    r"lead|source|sources|doors|phones|virtual|self[\s-]?gen|inbound|3pl|funnel|"
    r"trend|dashboard|metric|definition|terminology|pipeline|"
    r"changed|versus|compare|comparison|market|markets|operate|operations|timezone|process)\b",
    re.I,
)
_COMPANY = re.compile(
    _SUBSTANTIVE.pattern + r"|\b(happy solar|goose)\b",
    re.I,
)
_DEFINITION = re.compile(r"\b(what is|what's|define|explain|meaning|mean)\b", re.I)
_COMPARE = re.compile(r"\b(compare|versus|vs\.?|changed|change|last month|previous)\b", re.I)
_SOURCE = re.compile(r"\b(source|doors|phones|self[\s-]?gen|inbound|3pl)\b", re.I)
_GREETING = re.compile(r"^\s*(hi|hello|hey|good morning|good afternoon|thanks|thank you)\b", re.I)
_HELP = re.compile(r"\b(help|how do i use|what can you do|what can goose do)\b", re.I)
_CHALLENGE = re.compile(r"\b(wrong|incorrect|that can't|does not match|doesn't match|recheck)\b", re.I)
_FRUSTRATED = re.compile(r"\b(useless|stupid|this sucks|hate this|idiot)\b", re.I)
_FIGURE = re.compile(
    r"\b(how many|how much|what(?:'s| is) our|what(?:'s| is) the|this month|last month|"
    r"today|yesterday|this week|so far|right now)\b",
    re.I,
)
_EXPLAIN = re.compile(
    r"\b(define|explain|meaning|mean|what does|what counts|what is a|what is an)\b",
    re.I,
)
_VALUE_TERMS = frozenset({"sales", "demo_rate", "opp2prelim", "ran", "created"})
_CURRENT_PERIOD = re.compile(
    r"\b(?:our|today|mtd|current|so far|this (?:month|week|year))\b",
    re.I,
)
_LAST_MONTH = re.compile(r"\blast month\b", re.I)
_ASKS_TO_COMPARE = re.compile(r"\b(?:compare|versus|vs\.?|changed|change)\b", re.I)
_LOOSE_PERIOD = re.compile(
    r"\b(?:ytd|year to date|this year|last year|last week|yesterday|tomorrow|q[1-4]|"
    r"last\s+\d+\s+days?|since|first week of|fortnight|two months|past week|"
    r"week before last|last quarter|next week|next month|previous week)\b",
    re.I,
)
_SOURCE_NEGATION = re.compile(
    r"\b(?:everything but|but not|excluding|except|without)\b",
    re.I,
)
_NEAR_SOURCE_NEGATION = re.compile(
    r"\b(?:not counting|other than|aside from|apart from|minus|besides|but|not|non)\b",
    re.I,
)
_GLUED_NON_SOURCE = re.compile(
    r"\bnon[-\s]?(?:doors?|phones?|virtual|self[\s-]?gen|inbound|3\s*pl|nondoors)\b",
    re.I,
)
_DEMO_METRIC = re.compile(
    r"\b(?:demo\s+rate|demos|demo|demorate|demo[\s-]?rat|"
    r"dmeo(?:\s+rat(?:e)?)?|deom(?:\s+rat(?:e)?)?|demmo(?:\s+rat(?:e)?)?)\b",
    re.I,
)
_PURE_DEMO_DEFINITION = re.compile(
    r"^(?:what(?:'s| is)|define|explain)\s+(?:a\s+|the\s+)?demo(?:\s+rate)?\s*\??$"
    r"|^(?:how|what)\s+(?:is|does)\s+demo(?:\s+rate)?\s+"
    r"(?:calculated|defined|computed|measured|mean|meaning)\s*\??$",
    re.I,
)
_BARE_DEMO = re.compile(r"^(?:the\s+)?demo(?:\s+rate)?\s*\??$", re.I)
_FIGURE_FRAGMENT = re.compile(
    r"\b(?:not counting|other than|aside from|apart from|everything but|but not|"
    r"week of|weekends?|this quarter|past\s+(?:\d+\s+)?months?|last\s+\d+\s+weeks?|"
    r"new reps|how did|all sources but)\b"
    r"|\b(?:in|for|during)\s+(?:19|20)\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}\b"
    r"|\bbetween\s+[a-z]+\s+\d",
    re.I,
)
_FILLER_WORDS = frozenset(
    {
        "a",
        "about",
        "am",
        "an",
        "and",
        "are",
        "at",
        "be",
        "by",
        "can",
        "company",
        "current",
        "did",
        "do",
        "doing",
        "during",
        "everybody",
        "everyone",
        "far",
        "for",
        "from",
        "get",
        "give",
        "goose",
        "happy",
        "here",
        "how",
        "hows",
        "i",
        "im",
        "in",
        "is",
        "it",
        "its",
        "just",
        "let",
        "like",
        "looking",
        "many",
        "me",
        "mtd",
        "number",
        "numbers",
        "my",
        "need",
        "now",
        "of",
        "on",
        "our",
        "ours",
        "over",
        "overall",
        "please",
        "really",
        "right",
        "see",
        "show",
        "so",
        "solar",
        "team",
        "tell",
        "that",
        "the",
        "there",
        "this",
        "to",
        "today",
        "total",
        "us",
        "want",
        "was",
        "we",
        "were",
        "what",
        "whats",
        "with",
        "you",
        "your",
    }
)
_FILLER_RE = re.compile(r"\b(" + "|".join(sorted(_FILLER_WORDS, key=len, reverse=True)) + r")\b", re.I)
_METRIC_WORDS = re.compile(
    r"\bdemo[\s-]?rat(?:e)?\b|\bdemorate\b|\bdemos\b|\bdemo\b|"
    r"\b(?:dmeo|deom|demmo)(?:\s+rat(?:e)?)?\b|\brate\b|\bpercent\b|%",
    re.I,
)
_APOSTROPHE_SUFFIX = re.compile(r"['’](?:s|re|m|ll|ve|d)\b|n['’]t\b", re.I)
_TERM_WORDS = {
    "sales": re.compile(r"\bsales?\b", re.I),
    "created": re.compile(r"\b(?:created|opportunities|opportunity)\b", re.I),
    "ran": re.compile(r"\bran\b", re.I),
    "demo_rate": _METRIC_WORDS,
    "opp2prelim": re.compile(r"\bopp\s*2\s*prelim\b|\bopp2prelim\b", re.I),
    "sit": re.compile(r"\bdemos?\b", re.I),
}
_SOURCE_WORD = {
    "self_gen": re.compile(r"\bself[\s-]?gen\b", re.I),
    "phones": re.compile(r"\b(?:phones?|virtual)\b", re.I),
    "doors": re.compile(r"\bdoors?\b", re.I),
    "3pl": re.compile(r"\b3\s*pl\b", re.I),
    "inbound": re.compile(r"\binbound\b", re.I),
}
_NEGATION_FILLERS = frozenset(
    {
        "this",
        "last",
        "our",
        "the",
        "a",
        "an",
        "demo",
        "rate",
        "what",
        "please",
        "in",
        "on",
        "during",
        "month",
        "for",
    }
)
_UNAPPLIED_PERIOD = re.compile(
    r"\b(?:last\s+\d+\s+days?|first week of(?:\s+[a-z]+)?|since\s+[a-z]+|year to date|"
    r"week before last|last week|last year|this year|yesterday|tomorrow|ytd|q[1-4]|"
    r"fortnight|two months|past week|last quarter|next week|next month|previous week)\b",
    re.I,
)
_DAY_LEVEL_PHRASE = re.compile(
    r"\b(on\s+)?(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\s+"
    r"(\d{1,2})\b",
    re.I,
)
_THIS_WEEK = re.compile(r"\bthis week\b", re.I)


@dataclass(frozen=True)
class ScopeDecision:
    intent: str
    company_text: str
    denial_text: str
    clarification: str
    matched_term: str | None
    uncertain: bool = False
    uncertainty_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "company_text": self.company_text,
            "denial_text": self.denial_text,
            "clarification": self.clarification,
            "matched_term": self.matched_term,
            "uncertain": self.uncertain,
            "uncertainty_reason": self.uncertainty_reason,
        }


_FIGURE_INTENTS = frozenset({"company_summary", "compare", "source_performance"})
_TERRITORIES = {
    "buffalo": "Buffalo",
    "rochester": "Rochester",
    "syracuse": "Syracuse",
}
_SOURCE_PATTERNS = (
    (r"self[\s-]?gen", "self_gen"),
    (r"\bphones?\b", "phones"),
    (r"\bvirtual\b", "phones"),
    (r"\bdoors?\b", "doors"),
    (r"\b3\s*pl\b", "3pl"),
    (r"\binbound\b", "inbound"),
)
_NOT_A_QUALIFIER = frozenset(
    {
        "doors",
        "door",
        "self",
        "gen",
        "phones",
        "phone",
        "virtual",
        "inbound",
        "3pl",
        "pl",
        "the",
        "a",
        "an",
        "our",
        "this",
        "that",
        "me",
        "my",
        "all",
        "every",
        "each",
        "month",
        "week",
        "year",
        "today",
        "yesterday",
        "last",
        "next",
        "current",
        "mtd",
        "now",
        "far",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sept",
        "sep",
        "oct",
        "nov",
        "dec",
        "company",
        "everything",
        "new",
        "reps",
        "other",
        "counting",
        "except",
        "excluding",
        "without",
        "minus",
        "besides",
        "weekend",
        "weekends",
        "between",
        "sources",
        "source",
        "versus",
        "compare",
        "what",
        "it",
        "who",
        "how",
        "where",
        "when",
        "let",
        "here",
        "there",
        "goose",
        "us",
        "everyone",
        "everybody",
        "team",
        "overall",
        "happy",
        "solar",
        "demo",
        "demos",
        "rate",
        "sales",
        "sale",
        "ran",
        "created",
        "source",
        "sources",
        *tuple(_TERRITORIES),
    }
)
_SOURCE_LABELS = {
    "doors": "Doors",
    "self_gen": "Self Gen",
    "phones": "Phones",
    "inbound": "Inbound",
    "3pl": "3PL",
}


def _deny_hit(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _DENY_PATTERNS)


def _term_hint(text: str) -> str | None:
    lowered = text.lower()
    if "opp2prelim" in lowered.replace(" ", "").replace("-", "").replace("_", "") or "opp2prelim" in lowered:
        return "opp2prelim"
    if "opp 2 prelim" in lowered or "opp-to-prelim" in lowered:
        return "opp2prelim"
    if "demo rate" in lowered or re.search(r"\bdemo\b", lowered):
        return "demo_rate"
    if "self gen" in lowered or "selfgen" in lowered or "self-gen" in lowered:
        return "self_gen"
    if re.search(r"\bphones?\b", lowered) or re.search(r"\bvirtual\b", lowered):
        return "phones"
    if re.search(r"\bdoors?\b", lowered):
        return "doors"
    if "3pl" in lowered or "3 pl" in lowered:
        return "three_pl"
    if "inbound" in lowered:
        return "inbound"
    if re.search(r"\bsales?\b", lowered):
        return "sales"
    if re.search(r"\bran\b", lowered):
        return "ran"
    if re.search(r"\b(sits|sit|sat|demos)\b", lowered):
        return "sit"
    if "created" in lowered or "opportunities" in lowered:
        return "created"
    return None


def _negation_before_source(text: str) -> bool:
    """not / but / other than sitting in front of a lead source."""
    for pattern, _source_id in _SOURCE_PATTERNS:
        for match in re.finditer(pattern, text or "", re.I):
            prefix = (text or "")[max(0, match.start() - 48) : match.start()]
            if _NEAR_SOURCE_NEGATION.search(prefix):
                return True
    return False


def message_source_negated(text: str) -> bool:
    """A source named in order to leave it out. Never filter TO that source."""
    raw = text or ""
    return (
        bool(_SOURCE_NEGATION.search(raw))
        or _negation_before_source(raw)
        or bool(_GLUED_NON_SOURCE.search(raw))
    )


def message_sources_are_exact(text: str) -> bool:
    """'phones and doors' can be summed. 'phones or doors' cannot."""
    return not re.search(r"\bor\b", text or "", re.I)


def message_sources(text: str) -> list[str]:
    """Lead sources named in the message, in the order they appear. Virtual is Phones."""
    hits: list[tuple[int, str]] = []
    for pattern, source_id in _SOURCE_PATTERNS:
        for match in re.finditer(pattern, text or "", re.I):
            hits.append((match.start(), source_id))
    hits.sort()
    ordered: list[str] = []
    for _, source_id in hits:
        if source_id not in ordered:
            ordered.append(source_id)
    return ordered


def message_source(text: str) -> str | None:
    """First lead source named in the message. None when the source is excluded or ambiguous."""
    if message_source_negated(text) or not message_sources_are_exact(text):
        return None
    found = message_sources(text)
    return found[0] if found else None


def _source_list_label(source_ids: list[str]) -> str | None:
    labels: list[str] = []
    for source_id in source_ids:
        label = _SOURCE_LABELS.get(source_id)
        if label and label not in labels:
            labels.append(label)
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + ", and " + labels[-1]


def _applied_source_ids(text: str) -> list[str]:
    if message_source_negated(text) or not message_sources_are_exact(text):
        return []
    return message_sources(text)


def _title_name(word: str) -> str:
    return word[:1].upper() + word[1:]


def _name_stopped(word: str) -> bool:
    """True when the word is a filler, a lead source, a month, or a month typo. Not a person."""
    lower = word.lower().replace("’", "'")
    if lower in _NOT_A_QUALIFIER or lower in _FILLER_WORDS:
        return True
    if lower.startswith("non"):
        return True
    if re.search(r"doors?|phones?|virtual|inbound|self[\s-]?gen|3\s*pl", lower):
        return True
    return any(_within_one_edit(lower, name) for name in _FULL_MONTH_NUMBERS)


def _unapplied_name(text: str) -> str | None:
    """Territory or person the reporting tools cannot filter. Virtual is a lead source.

    Any capitalized or possessive name counts. There is no list of people.
    """
    raw = text or ""
    found: list[str] = []
    for match in re.finditer(r"\b(buffalo|rochester|syracuse)\b", raw, re.I):
        found.append(_TERRITORIES[match.group(1).lower()])
    for match in re.finditer(r"\bfor\s+([A-Za-z][A-Za-z'-]*)\b", raw, re.I):
        word = match.group(1)
        if _name_stopped(word):
            continue
        parts = [word]
        rest = raw[match.end() :]
        while len(parts) < 3:
            following = re.match(r"\s+([A-Za-z][A-Za-z'-]*)\b", rest)
            if not following or _name_stopped(following.group(1)):
                break
            parts.append(following.group(1))
            rest = rest[following.end() :]
        found.append(" ".join(_title_name(part) for part in parts))
    for match in re.finditer(r"\b([A-Za-z]+)['’]s\b", raw):
        word = match.group(1)
        if _name_stopped(word):
            continue
        found.append(_title_name(word))
    for match in re.finditer(r"\b([A-Z][a-z]+)\b", raw):
        word = match.group(1)
        prefix = raw[: match.start()]
        if not prefix.strip() or re.search(r"[.!?][\"')\]]*\s*$", prefix):
            continue
        if _name_stopped(word):
            continue
        parts = [word]
        rest = raw[match.end() :]
        while len(parts) < 3:
            following = re.match(r"\s+([A-Z][a-z]+)\b", rest)
            if not following or _name_stopped(following.group(1)):
                break
            parts.append(following.group(1))
            rest = rest[following.end() :]
        found.append(" ".join(parts))
    ordered: list[str] = []
    for name in sorted(set(found), key=len, reverse=True):
        if any(name != kept and name in kept.split(" or ") or f" {name} " in f" {kept} " or kept.startswith(name + " ") for kept in ordered):
            continue
        ordered.append(name)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    return " or ".join(ordered)


def _negation_phrase(text: str) -> str:
    match = _SOURCE_NEGATION.search(text or "")
    if not match:
        return "that exclusion"
    window = (text or "")[match.start() : match.start() + 48]
    words = re.findall(r"[A-Za-z0-9']+", window)
    negation_words = match.group(0).split()
    kept = list(negation_words)
    extras = 0
    for word in words[len(negation_words) :]:
        if word.lower() in _NEGATION_FILLERS:
            if extras:
                break
            continue
        kept.append(word)
        extras += 1
        if extras >= 3:
            break
    return " ".join(kept).lower()


def _clean_phrase(raw: str) -> str:
    phrase = " ".join((raw or "").split())
    if re.fullmatch(r"q[1-4]", phrase, re.I):
        return phrase.upper()
    return phrase.lower()


def _specific_day_phrase(text: str) -> str | None:
    """A calendar day the month-long reading would hide. 'may 1' is not one."""
    match = _DAY_LEVEL_PHRASE.search(text or "")
    if not match:
        return None
    day = int(match.group(2))
    if day > 1 or match.group(1):
        return _clean_phrase(match.group(0))
    return None


def _period_phrase(text: str) -> str | None:
    match = _UNAPPLIED_PERIOD.search(text or "")
    if match:
        return _clean_phrase(match.group(0))
    return _specific_day_phrase(text)


def _source_phrase(text: str, source_ids: list[str]) -> str:
    labels: list[str] = []
    for source_id in source_ids:
        label = _SOURCE_LABELS.get(source_id, source_id)
        if label not in labels:
            labels.append(label)
    joiner = " or " if re.search(r"\bor\b", text or "", re.I) else " and "
    if len(labels) == 2:
        return (labels[0] + joiner + labels[1]).lower()
    if len(labels) > 2:
        return (", ".join(labels[:-1]) + ", and " + labels[-1]).lower()
    return labels[0].lower() if labels else "those sources"


def uncovered_request(
    message: str,
    start: str,
    end: str,
    sources: list[str] | None,
    timezone_name: str | None,
    now,
) -> str | None:
    """Period, source, or negation the applied filters did not fully honor.

    None when the filters match the question. Person and territory names are a
    separate caveat, so this stays quiet when that sentence will already be used.
    One phrase, so the reply gets one line.
    """
    text = message or ""
    if _SOURCE_NEGATION.search(text):
        return _negation_phrase(text)
    asked = message_sources(text)
    applied = [str(item) for item in (sources or [])]
    if len(asked) >= 2 and set(asked) != set(applied):
        return _source_phrase(text, asked)
    served = None
    unserved = None
    try:
        served = named_calendar_range(text, timezone_name, now)
        if served is None:
            unserved = named_period_unserved(text, timezone_name, now)
    except TimezoneUnconfirmed:
        served = None
        unserved = None
    if unserved:
        return None
    if served and served == (start or "", end or ""):
        return None
    if (
        served
        and _ASKS_TO_COMPARE.search(text)
        and _LAST_MONTH.search(text)
        and not message_names_explicit_month(text)
    ):
        # A comparison already builds the prior month from the page window.
        return None
    if served:
        return _period_phrase(text) or "that period"
    if _relative_period_wins(text):
        day_phrase = _specific_day_phrase(text)
        if day_phrase:
            return day_phrase
        if _THIS_WEEK.search(text):
            implied = None
            try:
                implied = implied_current_range(text, timezone_name, now)
            except TimezoneUnconfirmed:
                implied = None
            if implied != (start or "", end or ""):
                return "this week"
        return None
    return _period_phrase(text)


def unconsumed_phrase(
    message: str,
    start: str,
    end: str,
    sources: list[str] | None,
    timezone_name: str | None,
    now,
    intent: str = "company_summary",
    compared: tuple[str, str] | None = None,
    matched_term: str | None = None,
) -> str | None:
    """Words still in the question after the applied metric, period, and sources are removed.

    None means the question was fully consumed. Anything left is one caveat.
    """
    text = message or ""
    if not text.strip():
        return None
    chars = list(text)

    def blank(span: tuple[int, int]) -> None:
        left, right = span
        left = max(0, left)
        right = min(len(chars), right)
        for index in range(left, right):
            chars[index] = " "

    # Drop the suffix of what's / how's / Sarah's before "what" is removed and "'s" is left behind.
    for match in _APOSTROPHE_SUFFIX.finditer(text):
        blank(match.span())
    for match in _METRIC_WORDS.finditer(text):
        blank(match.span())
    term_pattern = _TERM_WORDS.get(matched_term or "")
    if term_pattern is not None:
        for match in term_pattern.finditer(text):
            blank(match.span())
    for source_id in sources or []:
        pattern = _SOURCE_WORD.get(str(source_id))
        if pattern is None:
            continue
        for match in pattern.finditer(text):
            blank(match.span())
    try:
        covers = applied_period_covers(text, timezone_name, now, start or "", end or "")
    except TimezoneUnconfirmed:
        covers = []
    for span in covers:
        blank(span)
    if compared and compared[0] and compared[1] and (compared[0], compared[1]) != (start or "", end or ""):
        for span in month_spans_covering(text, compared[0], compared[1]):
            blank(span)
        try:
            for span in quarter_spans_covering(text, timezone_name, now, compared[0], compared[1]):
                blank(span)
        except TimezoneUnconfirmed:
            pass
    try:
        for span in quarter_spans_covering(text, timezone_name, now, start or "", end or ""):
            blank(span)
    except TimezoneUnconfirmed:
        pass
    if intent == "compare":
        for match in re.finditer(r"\b(?:compare|versus|vs\.?|against|changed|change)\b", text, re.I):
            blank(match.span())
        if _LAST_MONTH.search(text) and not message_names_explicit_month(text):
            match = _LAST_MONTH.search(text)
            if match:
                blank(match.span())
    relative = _relative_period_wins(text)
    for match in re.finditer(r"\bmay\b", text, re.I):
        modal = bool(re.match(r"\s+i\b", text[match.end() :], re.I))
        if modal or relative:
            blank(match.span())
    # "all" is filler in "for all of us", but it belongs in "all sources but doors".
    keep_all = message_source_negated(text)
    for match in _FILLER_RE.finditer(text):
        if keep_all and match.group(0).lower() == "all":
            continue
        blank(match.span())
    for match in re.finditer(r"\b([A-Za-z])\b", text):
        blank(match.span())
    indexes = [index for index, char in enumerate(chars) if char != " " and char.isalnum()]
    if not indexes:
        return None
    phrase = " ".join(text[indexes[0] : indexes[-1] + 1].split())
    phrase = phrase.strip(" .,!?:;\"'").lower()
    if not phrase or re.fullmatch(r"[a-z]", phrase) or phrase in {"but", "and", "or"}:
        return None
    return phrase


def _with_qualifier(decision: ScopeDecision, message: str) -> ScopeDecision:
    if decision.intent not in _FIGURE_INTENTS or decision.uncertain:
        return decision
    name = _unapplied_name(message)
    if not name:
        return decision
    label = _source_list_label(_applied_source_ids(message))
    if label:
        reason = f"I couldn't filter to {name}, so this is {label} only."
    else:
        reason = f"I couldn't filter to {name}, so this is company-wide."
    return replace(decision, uncertain=True, uncertainty_reason=reason)


def classify(message: str) -> ScopeDecision:
    return _with_qualifier(_classify(message), message)


def _classify(message: str) -> ScopeDecision:
    text = " ".join((message or "").split())
    if not text:
        return ScopeDecision("clarify", "", "", "Which Happy Solar metric or period should I look at?", None)
    company = bool(_COMPANY.search(text))
    substantive = bool(_SUBSTANTIVE.search(text))
    denied = _deny_hit(text)
    if denied and substantive:
        # Keep the company clause. The server still ignores embedded instructions.
        return ScopeDecision("mixed", text, "denied_unrelated", "", _term_hint(text))
    if denied:
        # Naming Happy Solar does not bring an unrelated request into scope.
        return ScopeDecision("deny", "", "denied", "", None)
    if _FRUSTRATED.search(text) and not company:
        return ScopeDecision("help", text, "", "", None)
    if _GREETING.search(text) and not company:
        return ScopeDecision("greeting", text, "", "", None)
    if _HELP.search(text) and not (_DEFINITION.search(text) and company):
        return ScopeDecision("help", text, "", "", None)
    if _CHALLENGE.search(text):
        return ScopeDecision("challenge", text, "", "", _term_hint(text))
    if re.search(r"\b(how are we|how did we)\b", text, re.I):
        term = _term_hint(text)
        if term == "sit":
            term = "demo_rate"
        if term in _VALUE_TERMS:
            return ScopeDecision("company_summary", text, "", "", term)
        return ScopeDecision(
            "clarify",
            text,
            "",
            "Which metric should I summarize, and should I use the dates already selected on the dashboard?",
            None,
        )
    if _PURE_DEMO_DEFINITION.search(text) or _BARE_DEMO.search(text):
        return ScopeDecision("definition", text, "", "", "demo_rate")
    if re.search(r"source performance", text, re.I):
        return ScopeDecision("source_performance", text, "", "", _term_hint(text) or "phones")
    asks_compare = bool(_ASKS_TO_COMPARE.search(text)) and not re.search(r"\b(?:changed|change)\b", text, re.I)
    figureish = bool(
        _DEMO_METRIC.search(text) or _FIGURE_FRAGMENT.search(text) or message_source_negated(text)
    )
    if asks_compare and (figureish or message_names_explicit_month(text)):
        return ScopeDecision("compare", text, "", "", "demo_rate")
    if figureish and not _EXPLAIN.search(text) and not _ASKS_TO_COMPARE.search(text):
        # A demo-rate question, or a fragment that names a period or an exclusion, is a number.
        # The definition is only the bare "what is demo rate" form.
        return ScopeDecision("company_summary", text, "", "", "demo_rate")
    if not company:
        return ScopeDecision("deny", "", "denied", "", None)
    term = _term_hint(text)
    if re.search(r"source performance", text, re.I):
        return ScopeDecision("source_performance", text, "", "", term or "phones")
    if re.search(r"\b(how many|what were|show (me )?the numbers|totals?)\b", text, re.I):
        return ScopeDecision("company_summary", text, "", "", term)
    if (
        term in _VALUE_TERMS
        and not _ASKS_TO_COMPARE.search(text)
        and not _EXPLAIN.search(text)
        and (
            _LAST_MONTH.search(text)
            or message_names_explicit_month(text)
            or _unapplied_name(text)
            or _LOOSE_PERIOD.search(text)
            or message_sources(text)
        )
    ):
        # "What was our demo rate last month?" and "demo rate in march" ask for that period.
        return ScopeDecision("company_summary", text, "", "", term)
    if (
        term in _VALUE_TERMS
        and _CURRENT_PERIOD.search(text)
        and not _COMPARE.search(text)
        and not _EXPLAIN.search(text)
    ):
        return ScopeDecision("company_summary", text, "", "", term)
    if _DEFINITION.search(text) or (term and len(text) < 40 and not _COMPARE.search(text)):
        # "What is Demo Rate?" stays a definition. "What is our demo rate this month?" asks for a figure.
        if term and _FIGURE.search(text) and not _EXPLAIN.search(text):
            return ScopeDecision("company_summary", text, "", "", term)
        if term is None:
            return ScopeDecision(
                "clarify",
                text,
                "",
                "Which term should I explain: Opp2Prelim, Demo Rate, a lead source, Sales, Ran, or Demo?",
                None,
            )
        return ScopeDecision("definition", text, "", "", term)
    if _COMPARE.search(text):
        if term is None and not re.search(r"\bsource", text, re.I):
            return ScopeDecision(
                "clarify",
                text,
                "",
                "Which metric should I compare for that period?",
                None,
            )
        return ScopeDecision("compare", text, "", "", term)
    if _SOURCE.search(text) and re.search(r"\b(performance|breakdown|by source|funnel)\b", text, re.I):
        return ScopeDecision("source_performance", text, "", "", term)
    if re.search(r"\b(how are we|how did we|status|overview|summary)\b", text, re.I) and term is None:
        return ScopeDecision(
            "clarify",
            text,
            "",
            "Which metric should I summarize, and should I use the dates already selected on the dashboard?",
            None,
        )
    if term in {"doors", "phones", "self_gen", "inbound", "three_pl"} and "performance" not in text.lower():
        return ScopeDecision("definition", text, "", "", term)
    if term:
        return ScopeDecision("company_summary", text, "", "", term)
    return ScopeDecision("knowledge", text, "", "", None)
