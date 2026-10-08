# -*- coding: utf-8 -*-
"""Deterministic scope checks. Ambiguous company questions clarify; they do not call a model."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace


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


def message_source(text: str) -> str | None:
    """Lead source named in the message. Virtual is the Phones source, not a territory."""
    earliest = None
    chosen = None
    for pattern, source_id in _SOURCE_PATTERNS:
        match = re.search(pattern, text or "", re.I)
        if match and (earliest is None or match.start() < earliest):
            earliest = match.start()
            chosen = source_id
    return chosen


def _unapplied_name(text: str) -> str | None:
    """Territory or person the reporting tools cannot filter. Virtual is a lead source."""
    found: list[str] = []
    for match in re.finditer(r"\b(buffalo|rochester|syracuse)\b", text or "", re.I):
        found.append(_TERRITORIES[match.group(1).lower()])
    for match in re.finditer(r"\bfor\s+([A-Za-z][A-Za-z'-]*)\b", text or "", re.I):
        word = match.group(1)
        if word.lower() in _NOT_A_QUALIFIER:
            continue
        found.append(word[:1].upper() + word[1:])
    ordered: list[str] = []
    for name in found:
        if name not in ordered:
            ordered.append(name)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    return " or ".join(ordered)


def _with_qualifier(decision: ScopeDecision, message: str) -> ScopeDecision:
    if decision.intent not in _FIGURE_INTENTS or decision.uncertain:
        return decision
    name = _unapplied_name(message)
    if not name:
        return decision
    source_id = message_source(message)
    if source_id:
        label = _SOURCE_LABELS.get(source_id, "that lead source")
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
    if not company:
        return ScopeDecision("deny", "", "denied", "", None)
    term = _term_hint(text)
    if re.search(r"source performance", text, re.I):
        return ScopeDecision("source_performance", text, "", "", term or "phones")
    if re.search(r"\b(how many|what were|show (me )?the numbers|totals?)\b", text, re.I):
        return ScopeDecision("company_summary", text, "", "", term)
    if term in _VALUE_TERMS and _LAST_MONTH.search(text):
        return ScopeDecision("compare", text, "", "", term)
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
