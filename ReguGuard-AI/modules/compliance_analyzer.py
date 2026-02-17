import os
import json
from openai import OpenAI


def get_grok_client():
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )


def analyze_clause_compliance(clause, matched_regulations, use_ai=False):
    return _rule_based_analyze(clause, matched_regulations)


def _ai_analyze(client, clause, matched_regulations):
    reg_context = ""
    citations = []
    for i, match in enumerate(matched_regulations[:5]):
        reg = match["regulation"]
        reg_context += f"\n--- Regulation {i+1} ---\n"
        reg_context += f"Source: {reg.get('source_name', 'Unknown')}\n"
        reg_context += f"URL: {reg.get('source_url', 'N/A')}\n"
        reg_context += f"Title: {reg.get('title', 'Unknown')}\n"
        reg_context += f"Content: {reg.get('text', '')[:800]}\n"
        citations.append({
            "source": reg.get("source_name", "Unknown"),
            "url": reg.get("source_url", "N/A"),
            "title": reg.get("title", "Unknown"),
            "relevance_score": match.get("similarity_score", 0),
        })

    prompt = f"""You are a compliance expert analyzing whether a company's Standard Operating Procedure (SOP) clause complies with current government regulations.

SOP CLAUSE:
ID: {clause['id']}
Title: {clause['title']}
Category: {clause['category']}
Text: {clause['text'][:1500]}

RELEVANT REGULATIONS:
{reg_context}

Analyze this SOP clause against the provided regulations and respond in this exact JSON format:
{{
    "compliance_status": "compliant" | "partially_compliant" | "non_compliant" | "outdated",
    "risk_level": "Low" | "Medium" | "High",
    "compliance_score": <number 0-100>,
    "summary": "<brief compliance summary in 2-3 sentences>",
    "missing_elements": ["<list of missing regulatory elements>"],
    "suggested_correction": "<suggested corrected clause text or 'No correction needed'>",
    "reasoning": "<detailed legal reasoning in 3-5 sentences>",
    "applicable_regulations": ["<list of specific regulation names/sections that apply>"]
}}

Be thorough and specific. Reference actual regulation names and sections where possible."""

    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {"role": "system", "content": "You are a regulatory compliance expert. Always respond with valid JSON only, no markdown formatting."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1500,
    )

    response_text = response.choices[0].message.content.strip()
    response_text = response_text.strip("`")
    if response_text.startswith("json"):
        response_text = response_text[4:]
    response_text = response_text.strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response_text[start:end])
        else:
            return _rule_based_analyze(clause, matched_regulations, ai_error="Invalid JSON response")

    result["citations"] = citations
    result["analysis_method"] = "AI (Grok)"
    result["clause_id"] = clause["id"]
    return result


def _rule_based_analyze(clause, matched_regulations, ai_error=None):
    text_lower = clause.get("text", "").lower()
    category = clause.get("category", "General")

    compliance_indicators = {
        "compliant": ["shall comply", "in accordance with", "as required by", "pursuant to",
                       "in compliance", "adhering to", "follows", "meets requirements"],
        "risk": ["may", "optional", "when possible", "if applicable", "best effort",
                 "should", "recommended", "consider"],
        "outdated": ["superseded", "replaced by", "no longer", "deprecated",
                     "previous version", "old standard", "former"],
    }

    compliant_score = sum(1 for kw in compliance_indicators["compliant"] if kw in text_lower)
    risk_score = sum(1 for kw in compliance_indicators["risk"] if kw in text_lower)
    outdated_score = sum(1 for kw in compliance_indicators["outdated"] if kw in text_lower)

    has_matches = len(matched_regulations) > 0
    avg_similarity = 0
    if has_matches:
        avg_similarity = sum(m["similarity_score"] for m in matched_regulations) / len(matched_regulations)

    if outdated_score >= 2:
        status = "outdated"
        risk_level = "High"
        score = 20
    elif compliant_score >= 2 and avg_similarity > 0.15:
        status = "compliant"
        risk_level = "Low"
        score = 85 + min(compliant_score * 3, 15)
    elif compliant_score >= 1 or avg_similarity > 0.1:
        status = "partially_compliant"
        risk_level = "Medium"
        score = 50 + min(compliant_score * 10, 30)
    elif risk_score >= 2:
        status = "partially_compliant"
        risk_level = "Medium"
        score = 45
    else:
        status = "non_compliant"
        risk_level = "High"
        score = 25

    citations = []
    applicable_regs = []
    for match in matched_regulations[:5]:
        reg = match["regulation"]
        citations.append({
            "source": reg.get("source_name", "Unknown"),
            "url": reg.get("source_url", "N/A"),
            "title": reg.get("title", "Unknown"),
            "relevance_score": match.get("similarity_score", 0),
        })
        applicable_regs.append(reg.get("title", "Unknown"))

    missing = []
    category_requirements = {
        "Data Privacy": ["explicit consent mechanisms", "data breach notification procedures", "data retention policy", "right to deletion process"],
        "Health & Safety": ["emergency procedures", "PPE requirements", "incident reporting", "safety training schedule"],
        "Financial": ["audit trail requirements", "tax filing schedule", "financial reporting standards", "internal controls"],
        "Employment": ["anti-discrimination policy", "overtime calculation method", "leave policy details", "termination procedures"],
        "Environmental": ["waste disposal procedures", "emission monitoring", "environmental impact assessment", "spill response plan"],
        "IT Security": ["access control policy", "encryption standards", "incident response plan", "regular security audits"],
        "Quality Control": ["inspection procedures", "non-conformance handling", "document control", "management review"],
        "Legal": ["regulatory compliance review schedule", "legal hold procedures", "contract review process", "record retention policy"],
    }

    for req in category_requirements.get(category, ["regulatory reference", "review schedule", "responsible party designation"]):
        if req.lower().replace(" ", "") not in text_lower.replace(" ", ""):
            missing.append(req)

    method = "Rule-based Analysis"
    if ai_error:
        method += f" (AI unavailable: {ai_error[:80]})"

    return {
        "clause_id": clause["id"],
        "compliance_status": status,
        "risk_level": risk_level,
        "compliance_score": score,
        "summary": f"Clause analyzed using {method}. Status: {status}. The clause {'aligns with' if score > 60 else 'needs improvement to meet'} current regulatory requirements for {category}.",
        "missing_elements": missing[:5],
        "suggested_correction": _generate_suggestion(clause, status, missing, category),
        "reasoning": f"Based on keyword analysis and regulatory matching (avg similarity: {avg_similarity:.2f}), this clause shows {status.replace('_', ' ')} characteristics. Found {compliant_score} compliance indicators and {risk_score} risk indicators.",
        "applicable_regulations": applicable_regs[:5],
        "citations": citations,
        "analysis_method": method,
    }


def _generate_suggestion(clause, status, missing, category):
    if status == "compliant":
        return "No correction needed. Clause appears compliant with current regulations."

    suggestion = f"Revise this {category} clause to include: "
    if missing:
        suggestion += ", ".join(missing[:3]) + ". "
    suggestion += "Ensure explicit references to applicable regulatory frameworks and include specific compliance measures with designated responsible parties and review schedules."
    return suggestion


def calculate_overall_compliance(results):
    if not results:
        return {"score": 0, "total_clauses": 0, "compliant": 0, "partial": 0, "non_compliant": 0, "outdated": 0, "compliance_debt": 0}

    total = len(results)
    scores = [r.get("compliance_score", 0) for r in results]
    avg_score = sum(scores) / total if total else 0

    compliant = sum(1 for r in results if r.get("compliance_status") == "compliant")
    partial = sum(1 for r in results if r.get("compliance_status") == "partially_compliant")
    non_compliant = sum(1 for r in results if r.get("compliance_status") == "non_compliant")
    outdated = sum(1 for r in results if r.get("compliance_status") == "outdated")

    high_risk = sum(1 for r in results if r.get("risk_level") == "High")
    medium_risk = sum(1 for r in results if r.get("risk_level") == "Medium")

    compliance_debt = (high_risk * 10000) + (medium_risk * 5000) + (non_compliant * 3000) + (outdated * 7000) + (partial * 1500)

    return {
        "score": round(avg_score, 1),
        "total_clauses": total,
        "compliant": compliant,
        "partial": partial,
        "non_compliant": non_compliant,
        "outdated": outdated,
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": total - high_risk - medium_risk,
        "compliance_debt": compliance_debt,
    }
