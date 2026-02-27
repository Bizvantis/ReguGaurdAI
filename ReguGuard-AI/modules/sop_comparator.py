import difflib
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from modules.sop_parser import parse_sop_into_clauses


REG_REF_KEYWORDS = [
    "cfr",
    "ecfr",
    "osha",
    "hipaa",
    "hhs",
    "nist",
    "epa",
    "fda",
    "eeoc",
    "fincen",
    "sec",
    "ftc",
    "dol",
    "federal register",
    "iso",
    "gmp",
]

CONTROL_KEYWORDS = [
    "approval",
    "approve",
    "review",
    "audit",
    "training",
    "record",
    "retention",
    "deviation",
    "oos",
    "out of specification",
    "capa",
    "validation",
    "change control",
    "governance",
    "responsible",
    "owner",
    "escalat",
    "risk",
    "mitigation",
]


def _norm(s: str) -> str:
    return (s or "").strip()


def _lower(s: str) -> str:
    return _norm(s).lower()


def _clause_repr(c: dict) -> str:
    return f"{c.get('title','')} {c.get('text','')}".strip()


def _diff_lines(a: str, b: str) -> tuple[list[str], list[str]]:
    """
    Return (removed_lines, added_lines) comparing a -> b.
    Lines are exact as in inputs (verbatim).
    """
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    sm = difflib.SequenceMatcher(a=a_lines, b=b_lines)
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            removed.extend([ln for ln in a_lines[i1:i2] if ln.strip()])
        if tag in ("insert", "replace"):
            added.extend([ln for ln in b_lines[j1:j2] if ln.strip()])
    return removed[:8], added[:8]


def _contains_any(lines: list[str], keywords: list[str]) -> bool:
    blob = " ".join(lines).lower()
    return any(k in blob for k in keywords)


def _count_mandatory(lines: list[str]) -> tuple[int, int]:
    blob = " ".join(lines).lower()
    must = sum(blob.count(w) for w in ["must", "shall", "required"])
    weak = sum(blob.count(w) for w in ["should", "may", "when possible", "if feasible", "recommended"])
    return must, weak


def _classify_difference(removed: list[str], added: list[str]) -> str:
    if not removed and not added:
        return "No Material Difference"

    # Regulatory references
    if _contains_any(added, REG_REF_KEYWORDS) and not _contains_any(removed, REG_REF_KEYWORDS):
        return "Regulatory Alignment Enhancement"

    # Controls / governance
    if _contains_any(added, CONTROL_KEYWORDS) and not _contains_any(removed, CONTROL_KEYWORDS):
        return "Control Strengthening"

    # Mandatory language vs ambiguity
    must_added, weak_added = _count_mandatory(added)
    must_removed, weak_removed = _count_mandatory(removed)
    if must_added > must_removed and weak_added <= weak_removed:
        return "Compliance Improvement"

    # Structure: lots of adds/removes often means restructuring
    if len(added) + len(removed) >= 8:
        return "Structural Improvement"

    # Clarity: shorter, cleaner lines added (heuristic)
    if added and all(len(x) < 180 for x in added) and len(added) >= 2:
        return "Clarity Enhancement"

    return "No Material Difference"


def _learning_rules_from_diffs(removed: list[str], added: list[str]) -> list[str]:
    rules: list[str] = []

    # Mandatory language improvement
    if any("should" in _lower(r) for r in removed) and any(("shall" in _lower(a) or "must" in _lower(a)) for a in added):
        rules.append("Prefer mandatory language (shall/must/required) over advisory language (should/may) for compliance controls.")

    # Roles/responsibilities
    if any("responsible" in _lower(a) or "owner" in _lower(a) for a in added):
        rules.append("Explicitly assign responsibilities/owners for each compliance control.")

    # Approval / review cadence
    if any("approve" in _lower(a) or "review" in _lower(a) for a in added):
        rules.append("Add explicit approval/review controls (who approves, when, and how often).")

    # Documentation rigor
    if any("record" in _lower(a) or "retention" in _lower(a) for a in added):
        rules.append("State documentation and record-retention requirements explicitly (what is recorded and how long it is retained).")

    # Deviations/OOS/CAPA/Validation
    if any(k in " ".join(_lower(a) for a in added) for k in ["deviation", "oos", "capa", "validation", "change control"]):
        rules.append("Include governance mechanisms for deviations/OOS/CAPA/validation/change control where applicable.")

    # Regulatory anchoring
    if _contains_any(added, REG_REF_KEYWORDS):
        rules.append("Anchor controls to explicit regulatory references when present in the SOP text (agency/framework names, CFR/standard references).")

    return list(dict.fromkeys(rules))


def compare_sop_documents(ai_updated_text: str, human_text: str) -> dict[str, Any]:
    """
    Structured, clause-by-clause comparison grounded strictly in document text.
    Produces exact-line quotes via line diffs (no hallucinated clauses/sections).
    """
    ai_text = _norm(ai_updated_text)
    hu_text = _norm(human_text)

    ai_clauses = parse_sop_into_clauses(ai_text) if ai_text else []
    hu_clauses = parse_sop_into_clauses(hu_text) if hu_text else []

    # If either side is empty, return minimal report grounded in that fact.
    if not ai_clauses or not hu_clauses:
        return {
            "Key Differences": [],
            "Compliance Enhancements in Human Version": [],
            "Weaknesses in Human Version": [],
            "Learning Extracted Rules": [],
            "Model Update Recommendations": [
                "Unable to compare clause-by-clause because one document did not yield extractable clauses.",
            ],
        }

    ai_docs = [_clause_repr(c) for c in ai_clauses]
    hu_docs = [_clause_repr(c) for c in hu_clauses]

    vec = TfidfVectorizer(max_features=8000, stop_words="english", ngram_range=(1, 2))
    X = vec.fit_transform(ai_docs + hu_docs)
    X_ai = X[: len(ai_docs)]
    X_hu = X[len(ai_docs) :]
    sim = cosine_similarity(X_ai, X_hu)

    # Greedy matching: each human clause matched at most once
    matched_hu = set()
    pairs: list[tuple[int, int, float]] = []
    for i in range(sim.shape[0]):
        j = int(np.argmax(sim[i]))
        score = float(sim[i, j])
        if j in matched_hu:
            # pick next best
            order = np.argsort(sim[i])[::-1]
            for jj in order:
                jj = int(jj)
                if jj not in matched_hu:
                    j = jj
                    score = float(sim[i, j])
                    break
        matched_hu.add(j)
        pairs.append((i, j, score))

    key_diffs = []
    human_stronger = []
    ai_stronger = []
    learning_rules: list[str] = []

    for i, j, score in pairs:
        ai_clause = ai_clauses[i]
        hu_clause = hu_clauses[j]

        removed, added = _diff_lines(ai_clause.get("text", ""), hu_clause.get("text", ""))
        classification = _classify_difference(removed, added)

        if classification != "No Material Difference":
            entry = {
                "classification": classification,
                "ai_clause_id": ai_clause.get("id"),
                "ai_title": ai_clause.get("title"),
                "human_clause_id": hu_clause.get("id"),
                "human_title": hu_clause.get("title"),
                "similarity": round(score, 3),
                "quotes_removed_from_ai": removed,  # exact lines removed/changed
                "quotes_added_in_human": added,      # exact lines added/changed
            }
            key_diffs.append(entry)

            # Determine strength direction using added/removed control keywords
            if _contains_any(added, CONTROL_KEYWORDS) and not _contains_any(removed, CONTROL_KEYWORDS):
                human_stronger.append(entry)
            elif _contains_any(removed, CONTROL_KEYWORDS) and not _contains_any(added, CONTROL_KEYWORDS):
                ai_stronger.append(entry)

            learning_rules.extend(_learning_rules_from_diffs(removed, added))

    # Weaknesses in human version: places where controls/reg refs were removed
    weaknesses = []
    for e in ai_stronger:
        weaknesses.append({
            "classification": "Control Strengthening",
            "note": "AI version contains control/regulatory detail not present (or reduced) in the human version, based on exact removed/added lines.",
            "quotes_removed_from_ai": e.get("quotes_removed_from_ai", []),
            "quotes_added_in_human": e.get("quotes_added_in_human", []),
        })

    # Conservative recommendations based on extracted learning rules
    model_recos = []
    for r in list(dict.fromkeys(learning_rules))[:10]:
        model_recos.append(f"Update SOP generation prompts/templates to: {r}")
    if not model_recos:
        model_recos = ["No verified human improvements detected that warrant updating generation rules."]

    return {
        "Key Differences": key_diffs,
        "Compliance Enhancements in Human Version": human_stronger,
        "Weaknesses in Human Version": weaknesses,
        "Learning Extracted Rules": list(dict.fromkeys(learning_rules)),
        "Model Update Recommendations": model_recos,
        "meta": {
            "ai_clauses": len(ai_clauses),
            "human_clauses": len(hu_clauses),
            "matched_pairs": len(pairs),
        },
    }

