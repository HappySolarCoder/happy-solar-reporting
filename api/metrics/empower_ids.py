# -*- coding: utf-8 -*-

"""Shared EmPower+ ids. Values are pipeline and field ids, not secrets."""

from __future__ import annotations


EMPOWER_PIPELINE_ID = "5hPKCGzAskcC6LEZuc1H"
GHL_LOCATION_ID_DEFAULT = "MMKRDviKggXzlcHQTnvZ"
GHL_API_VERSION = "2021-07-28"

# Funnel metrics read these. EmPower+ tracking must not write them.
# Pipeline exclusion itself lives in a separate change to pipeline_scope.py.
FUNNEL_COLLECTIONS = frozenset(
    {
        "ghl_opportunities_v2",
        "ghl_opportunities",
        "ghl_contacts_v2",
        "ghl_contacts",
        "ghl_appointment_events_v2",
        "ghl_calendar_events_v2",
        "ghl_appointments_v2",
        "ghl_opportunity_stage_history_v1",
        "ghl_selfgen_rebooks_v1",
    }
)

LINKS_COLLECTION = "empower_links"
GHL_STAGE_EVENTS = "ghl_empower_stage_events"
ALERTS_COLLECTION = "empower_alerts"

USER_TYLER = "DzQ6Olr2aQKjYP2Sb5gA"
USER_BROOKE = "XI56R86CcRMeIAwrVdvI"
USER_STEVEN = "y39YIlgRGCJFhZkBzF0h"
USER_JEFF = "b4SOGTyK8QCfQFJfsMtb"
USER_EVAN = "pG8Awr3cG2l1glenBJbp"

OWNER_USER_IDS = {
    "tyler": USER_TYLER,
    "brooke": USER_BROOKE,
    "steven": USER_STEVEN,
    "evan": USER_EVAN,
    "rep": USER_TYLER,
}

# Position is the pipeline order. Shadow sync must not write pipelineStageId.
GHL_STAGES = (
    ("Portal Creation Needed", "81524518-3f46-4944-91e1-bfea838ec3a0"),
    ("Income Documents Needed", "9f3fb3d0-ddfa-48b9-a12c-c7309997f41f"),
    ("Awaiting Income Qualification", "7ae4b98f-a8f8-440e-8a6e-04bda5e5ce5f"),
    ("Waiting on Assignment", "bf590a3a-f190-458e-9d40-b0b41d0690ea"),
    ("Enrollment Accepted", "1d581ade-b0c3-4533-82f6-7e965e29c61b"),
    ("Audit Confirmed", "1ea2552d-c686-4600-862e-5a8d56a6d0e8"),
    ("Audit Cancelled", "654eaec0-778d-4ce5-a4ae-f2f06790f863"),
    ("Awaiting Results", "975d03c9-06f3-4e81-b01e-e065d983f1ec"),
    ("Results Received", "fd10490c-488d-408e-a721-234418e9583c"),
    ("Sales Appointment Scheduled", "0b050f31-af83-4cc9-939e-554591e62a63"),
    ("Sales Appointment No Show", "d80a2cd8-0140-4c42-95fd-5c9622cd9147"),
    ("Sales Appointment Demo", "5bf56e82-c742-48fe-a194-8b154848ca0e"),
    ("Workscope Submitted", "b45b7305-e86b-45dc-907b-7efe38145777"),
    ("With Program – Workscope Review", "2ad890e9-0600-4b7d-b027-198337a64832"),
    ("Install Scheduled", "ebd02c0d-f961-4622-9306-a9bb1eee9cd7"),
    ("Install Complete", "c0a23106-dea0-420e-b935-623848f09127"),
    ("Close Out Photos Complete", "a2ea7e6b-380c-428c-970c-4f7383e7efce"),
    ("With Program – Final Review", "8260f5af-fa43-4100-9c98-cfe769045e10"),
    ("Funding Allocated", "174ba8af-9d3d-4187-8a10-1f973fde65fb"),
    ("Paid", "fd01c786-a48d-4eac-9245-b4e1ad79d18c"),
)

GHL_STAGE_INDEX = {stage_id: index for index, (_name, stage_id) in enumerate(GHL_STAGES)}
GHL_STAGE_NAME = {stage_id: name for name, stage_id in GHL_STAGES}
GHL_STAGE_ID_BY_NAME = {name: stage_id for name, stage_id in GHL_STAGES}

# NYHEP step -> minimum GHL stage position. Used for lag, not for moving opps.
NYHEP_STAGE_POS = {
    "Create an Enrollment": 0,
    "Contractor Assignment": 3,
    "Enrollment Acceptance": 4,
    "Assessment Submission": 5,
    "Assessment Started": 5,
    "Assessment Review": 7,
    "Workscope Submission": 12,
    "Workscope Review": 13,
    "Provisional Approval": 13,
    "Install Started": 14,
    "Final Project Submission": 14,
    "Final Project Review": 17,
    "Final Technical Review": 17,
    "Funding Allocations": 18,
    "Installation Funding Allocations": 18,
    "Installation Review": 17,
    "Payment": 19,
}

FIELD_ENROLLMENT_ID = "Anddcx3E00WOhrNyD9mX"
FIELD_PROGRAM = "r0Ku4yXPNmUMjbj9DXpq"
FIELD_STEP = "T9eP2boFDKqp7sHecIes"
FIELD_STEP_STATUS = "km1ObkgiiCJLg8U6WUby"
FIELD_ENROLLMENT_STATUS = "2naIgZipnkHXbGHWy0oC"
FIELD_WITH = "5rYJczEHTOyyTLwc39oc"
FIELD_DUE = "HmHBTxWn28SbpDPc3yU6"
FIELD_STEP_SINCE = "uQUZj7KvaK7ChKkmYc36"
FIELD_TRADE_ALLY = "IWZrs3HAEyUtUJNnukXq"
FIELD_LAST_SYNCED = "dWzkIInUfGiwmprKKkyt"
FIELD_STALL = "rqdEqLGrFDjwZkgS8jxC"
FIELD_AUDIT_DATE = "BkgvC6HX5ZK1XFmCc5iv"
FIELD_WORKSCOPE_SUBMITTED = "Timj99fcG9tCLsX0Sjgm"
FIELD_INSTALL_DATE = "cVctzBYJoMZPpT6eZdk9"
FIELD_FINAL_SUBMITTED = "59o053X6d3Tmc4rldRcC"
FIELD_FUNDED_DATE = "reAn5xXiIGrN4HJhlLrD"
FIELD_PAID_DATE = "0rQeH6QfLgYeYCS6d7Me"

PROGRAM_OPTIONS = ("EmPower+", "Comfort Home", "REA")
STATUS_OPTIONS = ("Open", "Closed", "Cancelled")
WITH_OPTIONS = ("Us", "Program", "Unclear")
TRADE_OPTIONS = ("A Happy Day LLC", "Essential Homes LLC")

# Early sales stages. Past "Awaiting Income Qualification" starts at position 3.
INCOME_QUAL_POS = 2
