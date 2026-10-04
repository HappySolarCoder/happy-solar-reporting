# -*- coding: utf-8 -*-
"""Idempotent Firestore seed for draft terminology and knowledge.

Dry-run is the default. Nothing here approves a definition.

    python scripts/copilot_seed.py
    python scripts/copilot_seed.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
sys.path.insert(0, str(API))

from copilot.dictionary import load_seed as load_terms
from copilot.knowledge import load_seed as load_knowledge


def _hash(payload) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write drafts to Firestore")
    args = parser.parse_args()
    terms = load_terms()
    knowledge = load_knowledge()
    print(f"terms={len(terms)} documents={len(knowledge['documents'])} mode={'apply' if args.apply else 'dry-run'}")
    for term in terms:
        print(f"term {term['term_id']} status={term['governance']['status']} hash={_hash(term)[:12]}")
    for document in knowledge["documents"]:
        print(f"doc {document['document_id']} status={document['approval_status']} hash={_hash(document)[:12]}")
    if not args.apply:
        print("Dry run only. Pass --apply to upsert draft records. Approved rows are not overwritten.")
        return 0
    from copilot.firestore_store import firestore_client

    client = firestore_client()
    if client is None:
        print("Firestore credentials are missing. Set FIREBASE_SERVICE_ACCOUNT_JSON, GCP_PROJECT_ID, FIRESTORE_DATABASE_ID.")
        return 1
    for term in terms:
        ref = client.collection("copilot_terminology").document(term["term_id"])
        current = ref.get().to_dict() or {}
        if current.get("governance", {}).get("status") == "APPROVED":
            print(f"skip approved {term['term_id']}")
            continue
        body = dict(term)
        body["source_hash"] = _hash(term)
        ref.set(body)
    for document in knowledge["documents"]:
        ref = client.collection("copilot_knowledge").document(document["document_id"])
        current = ref.get().to_dict() or {}
        digest = _hash(document)
        if current.get("source_hash") == digest:
            print(f"unchanged {document['document_id']}")
            continue
        if current.get("approval_status") == "APPROVED":
            print(f"skip approved {document['document_id']}")
            continue
        body = dict(document)
        body["source_hash"] = digest
        ref.set(body)
    print("Seed write finished. Statuses remain DRAFT unless an admin revision already approved them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
