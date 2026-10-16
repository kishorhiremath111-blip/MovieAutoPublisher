#!/usr/bin/env python3
"""Fail-closed copyright/rights review and upload approval checks."""
from urllib.parse import urlparse

ALLOWED_RIGHTS_BASES = {"public_domain", "written_permission", "license", "original_content"}


def rights_gate(item):
    """Return (approved, reason). Edits or short duration never imply permission."""
    if not isinstance(item, dict):
        return False, "metadata item is not an object"
    if item.get("rights_review_status") != "approved":
        return False, "rights_review_status must be approved after a human copyright/rights review"
    if item.get("upload_approved") is not True:
        return False, "upload_approved must be true after explicit human approval"
    basis = str(item.get("rights_basis") or "").strip().lower()
    if basis not in ALLOWED_RIGHTS_BASES:
        return False, "rights_basis must be public_domain, written_permission, license, or original_content"
    proof = str(item.get("rights_verification_url") or "").strip()
    parsed = urlparse(proof)
    if parsed.scheme != "https" or not parsed.hostname:
        return False, "rights_verification_url must be an HTTPS evidence/permission URL"
    note = str(item.get("rights_verification_note") or "").strip()
    if len(note) < 30:
        return False, "rights_verification_note must explain rights for this exact source and intended use"
    if item.get("audio_language_verified") is not True:
        return False, "audio language must be checked manually"
    return True, "copyright/rights review and upload approval present"
