import os
import json
import re
import math
from openai import OpenAI

from modules.sop_parser import parse_sop_into_clauses


def get_grok_client():
    api_key = os.environ.get("XAI_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1",
    )


def calculate_compliance_score(
    regulatory_alignment_score,
    language_strength_score,
    completeness_score,
    risk_penalty,
    industry=None,
    has_citations=True,
    has_enforceable_language=True,
    missing_critical_elements=0,
    total_elements_checked=0
):
    """
    Calculate a dynamic, accurate compliance score using weighted factors and proper formulas.
    
    Formula: Score = Base_Score * Weight_Factors - Penalties
    
    Where:
    - Base_Score = Weighted average of regulatory alignment, language strength, and completeness
    - Weight_Factors = Industry-specific adjustments and citation bonuses
    - Penalties = Risk-based deductions
    
    Args:
        regulatory_alignment_score: 0-1, similarity to regulations (RAG similarity)
        language_strength_score: 0-1, strength of compliance language (must/shall/required)
        completeness_score: 0-1, completeness of required elements
        risk_penalty: 0-1, penalty factor based on risk indicators
        industry: Industry type for industry-specific weights
        has_citations: Whether regulatory citations are present
        has_enforceable_language: Whether document uses enforceable language
        missing_critical_elements: Number of critical missing elements
        total_elements_checked: Total number of elements checked
    
    Returns:
        compliance_score: 0-100 integer score
    """
    # Industry-specific weights (higher weight = more important for that industry)
    industry_weights = {
        "Finance": {
            "regulatory": 0.45,  # High regulatory alignment critical
            "language": 0.30,     # Strong language important
            "completeness": 0.25  # Completeness important
        },
        "Pharma/Healthcare": {
            "regulatory": 0.50,  # Very high regulatory alignment critical
            "language": 0.25,     # Language important
            "completeness": 0.25  # Completeness critical
        },
        "Education": {
            "regulatory": 0.40,
            "language": 0.30,
            "completeness": 0.30
        },
        "Agriculture": {
            "regulatory": 0.40,
            "language": 0.30,
            "completeness": 0.30
        },
        "Manufacturing": {
            "regulatory": 0.35,
            "language": 0.35,
            "completeness": 0.30
        },
        "Technology": {
            "regulatory": 0.40,
            "language": 0.30,
            "completeness": 0.30
        },
        "Retail": {
            "regulatory": 0.35,
            "language": 0.35,
            "completeness": 0.30
        },
        "Energy": {
            "regulatory": 0.45,
            "language": 0.30,
            "completeness": 0.25
        },
        "Construction": {
            "regulatory": 0.40,
            "language": 0.30,
            "completeness": 0.30
        },
        "Legal": {
            "regulatory": 0.45,
            "language": 0.35,
            "completeness": 0.20
        },
        "General": {
            "regulatory": 0.40,
            "language": 0.30,
            "completeness": 0.30
        }
    }
    
    # Get weights for industry (default to General)
    weights = industry_weights.get(industry, industry_weights["General"])
    
    # Normalize scores to 0-1 range (they should already be, but ensure)
    regulatory_alignment_score = max(0.0, min(1.0, regulatory_alignment_score))
    language_strength_score = max(0.0, min(1.0, language_strength_score))
    completeness_score = max(0.0, min(1.0, completeness_score))
    risk_penalty = max(0.0, min(1.0, risk_penalty))
    
    # Calculate weighted base score using geometric mean for better distribution
    # Geometric mean is better than arithmetic mean for multiplicative factors
    base_score = (
        math.pow(regulatory_alignment_score, weights["regulatory"]) *
        math.pow(language_strength_score, weights["language"]) *
        math.pow(completeness_score, weights["completeness"])
    )
    
    # Apply logarithmic scaling to base score for better distribution
    # This ensures scores are more evenly distributed across the 0-100 range
    if base_score > 0:
        base_score_scaled = 100 * (1 - math.exp(-2 * base_score))
    else:
        base_score_scaled = 0
    
    # Apply bonuses
    citation_bonus = 0
    if has_citations:
        citation_bonus = 3.0  # Small bonus for having citations
    
    enforceable_bonus = 0
    if has_enforceable_language:
        enforceable_bonus = 2.0  # Small bonus for enforceable language
    
    # Calculate completeness penalty (exponential penalty for missing critical elements)
    completeness_penalty = 0
    if total_elements_checked > 0:
        missing_ratio = missing_critical_elements / total_elements_checked
        # Exponential penalty: missing 10% = -5 points, missing 30% = -15 points, missing 50% = -30 points
        completeness_penalty = 30 * (missing_ratio ** 1.5)
    
    # Apply risk penalty (multiplicative, not additive)
    # Risk penalty reduces score proportionally
    risk_adjusted_score = base_score_scaled * (1 - risk_penalty * 0.4)  # Max 40% reduction from risk
    
    # Apply bonuses and penalties
    final_score = risk_adjusted_score + citation_bonus + enforceable_bonus - completeness_penalty
    
    # Ensure score is within bounds
    final_score = max(0, min(100, final_score))
    
    return round(final_score)


def calculate_regulatory_alignment_score(matched_regulations, avg_similarity, top_similarity):
    """
    Calculate regulatory alignment score based on RAG similarity metrics.
    Uses multiple similarity metrics for accuracy.
    """
    if not matched_regulations or len(matched_regulations) == 0:
        return 0.0
    
    # Base score from average similarity (normalized to 0-1)
    avg_score = min(1.0, avg_similarity * 2.0)  # Scale: 0.5 similarity = 1.0 score
    
    # Top match boost (strongest regulation match gets extra weight)
    top_score = min(1.0, top_similarity * 2.5)  # Scale: 0.4 similarity = 1.0 score
    
    # Number of matches boost (more matches = better coverage)
    match_count = len(matched_regulations)
    match_count_score = min(1.0, match_count / 5.0)  # 5+ matches = full score
    
    # Weighted combination: 50% avg, 30% top, 20% count
    alignment_score = (0.5 * avg_score) + (0.3 * top_score) + (0.2 * match_count_score)
    
    return min(1.0, alignment_score)


def calculate_language_strength_score(text):
    """
    Calculate language strength score based on compliance language indicators.
    """
    if not text:
        return 0.0
    
    text_lower = text.lower()
    
    # Strong compliance language (high weight)
    strong_indicators = [
        "must", "shall", "required", "mandatory", "obligated",
        "comply with", "in accordance with", "pursuant to",
        "as mandated", "as required by", "per regulatory"
    ]
    
    # Moderate compliance language (medium weight)
    moderate_indicators = [
        "should", "recommended", "expected", "advisable",
        "best practice", "guideline", "standard"
    ]
    
    # Weak/risky language (negative weight)
    weak_indicators = [
        "may", "optional", "when possible", "if applicable",
        "best effort", "consider", "where practicable"
    ]
    
    # Count occurrences
    strong_count = sum(1 for ind in strong_indicators if ind in text_lower)
    moderate_count = sum(1 for ind in moderate_indicators if ind in text_lower)
    weak_count = sum(1 for ind in weak_indicators if ind in text_lower)
    
    # Normalize by text length (words)
    word_count = len(text.split())
    if word_count == 0:
        return 0.0
    
    # Calculate density scores
    strong_density = min(1.0, (strong_count * 10) / word_count * 100)  # 1% density = full score
    moderate_density = min(0.5, (moderate_count * 5) / word_count * 100)  # 1% density = 0.5 score
    weak_density = min(0.3, (weak_count * 3) / word_count * 100)  # 1% density = 0.3 penalty
    
    # Weighted score: strong is positive, moderate is neutral-positive, weak is negative
    language_score = (strong_density * 1.0) + (moderate_density * 0.3) - (weak_density * 0.5)
    
    # Apply sigmoid function for smooth distribution
    language_score = 1 / (1 + math.exp(-5 * (language_score - 0.3)))
    
    return max(0.0, min(1.0, language_score))


def calculate_completeness_score(text, category, matched_regulations):
    """
    Calculate completeness score based on required elements presence.
    """
    if not text:
        return 0.0
    
    text_lower = text.lower()
    
    # Universal required elements (all documents should have)
    universal_elements = [
        "responsible", "owner", "review", "audit", "approval",
        "procedure", "process", "documentation", "record"
    ]
    
    # Category-specific required elements
    category_elements = {
        "Data Privacy": [
            "consent", "breach", "notification", "retention", "deletion",
            "access", "privacy", "data protection", "gdpr", "hipaa"
        ],
        "Health & Safety": [
            "emergency", "ppe", "incident", "reporting", "training",
            "safety", "hazard", "risk assessment", "osha"
        ],
        "Financial": [
            "audit", "reporting", "internal control", "compliance",
            "record", "documentation", "review", "approval", "sec", "irs"
        ],
        "Employment": [
            "discrimination", "overtime", "leave", "termination",
            "policy", "procedure", "training", "dol", "flsa"
        ],
        "Environmental": [
            "waste", "disposal", "emission", "monitoring", "impact",
            "assessment", "spill", "response", "epa", "rcra"
        ],
        "IT Security": [
            "access control", "encryption", "incident response",
            "security audit", "cybersecurity", "nist", "cisa"
        ],
        "Quality Control": [
            "inspection", "non-conformance", "document control",
            "management review", "corrective action", "fda", "iso"
        ],
        "Legal": [
            "compliance review", "legal hold", "contract review",
            "record retention", "regulatory", "legal"
        ],
    }
    
    # Count found elements
    universal_found = sum(1 for elem in universal_elements if elem in text_lower)
    universal_total = len(universal_elements)
    
    category_specific = category_elements.get(category, [])
    category_found = sum(1 for elem in category_specific if elem in text_lower)
    category_total = len(category_specific) if category_specific else 1
    
    # Calculate scores
    universal_score = universal_found / universal_total if universal_total > 0 else 0.5
    category_score = category_found / category_total if category_total > 0 else 0.5
    
    # Weighted combination: 60% universal, 40% category-specific
    completeness_score = (0.6 * universal_score) + (0.4 * category_score)
    
    # Boost if regulations are matched (indicates alignment)
    if matched_regulations and len(matched_regulations) > 0:
        completeness_score = min(1.0, completeness_score * 1.1)
    
    return max(0.0, min(1.0, completeness_score))


def calculate_risk_penalty(text, matched_regulations, avg_similarity):
    """
    Calculate risk penalty factor (0-1) based on risk indicators.
    Higher penalty = more risk = lower final score.
    """
    if not text:
        return 1.0  # Maximum penalty if no text
    
    text_lower = text.lower()
    
    # High-risk indicators
    high_risk_indicators = [
        "outdated", "superseded", "deprecated", "no longer",
        "optional", "may", "when possible", "best effort"
    ]
    
    # Medium-risk indicators
    medium_risk_indicators = [
        "should", "recommended", "consider", "if applicable"
    ]
    
    # Count risk indicators
    high_risk_count = sum(1 for ind in high_risk_indicators if ind in text_lower)
    medium_risk_count = sum(1 for ind in medium_risk_indicators if ind in text_lower)
    
    # Calculate risk score (0-1)
    word_count = len(text.split())
    if word_count == 0:
        return 1.0
    
    high_risk_density = min(1.0, (high_risk_count * 20) / word_count * 100)
    medium_risk_density = min(0.5, (medium_risk_count * 10) / word_count * 100)
    
    risk_score = (high_risk_density * 0.7) + (medium_risk_density * 0.3)
    
    # Add penalty for low regulatory alignment
    alignment_penalty = 0.0
    if not matched_regulations or len(matched_regulations) == 0:
        alignment_penalty = 0.5  # High penalty if no matches
    elif avg_similarity < 0.1:
        alignment_penalty = 0.3  # Medium penalty if low similarity
    
    # Combine risk factors
    total_risk = min(1.0, risk_score + alignment_penalty)
    
    return total_risk


def detect_industry(full_text, use_ai=True):
    """
    Detect the industry/sector that the document belongs to.
    Returns: { "industry": str, "confidence": str, "reason": str }
    Industries: Finance, Pharma/Healthcare, Education, Agriculture, Manufacturing, Technology, Retail, Energy, Construction, Legal, General
    """
    if not full_text or not full_text.strip():
        return {"industry": "General", "confidence": "Low", "reason": "No text content available for industry detection."}

    if use_ai:
        client = get_grok_client()
        if client is not None:
            try:
                return _ai_detect_industry(client, full_text)
            except Exception as e:
                return _rule_based_detect_industry(full_text, ai_error=str(e)[:80])
    return _rule_based_detect_industry(full_text)


def _ai_detect_industry(client, full_text):
    # Send a representative sample to stay within token limits
    sample = full_text[:8000].strip()
    if len(full_text) > 10000:
        sample += "\n\n[... document continues ...]\n\n" + full_text[-2000:].strip()

    prompt = f"""You are an industry classifier. Analyze the following document and determine which industry or sector it belongs to.

DOCUMENT CONTENT (excerpt):
{sample}

Respond with valid JSON only, no markdown:
{{
    "industry": "One of: Finance, Pharma/Healthcare, Education, Agriculture, Manufacturing, Technology, Retail, Energy, Construction, Legal, General",
    "confidence": "High" | "Medium" | "Low",
    "reason": "One or two sentences explaining why this document belongs to this industry, citing specific keywords or themes from the document."
}}

Consider these industry indicators:
- Finance: banking, securities, financial reporting, SEC, FDIC, investment, accounting, tax compliance
- Pharma/Healthcare: FDA, pharmaceutical, clinical trials, drug manufacturing, HIPAA, medical devices, healthcare procedures
- Education: educational institutions, student data, FERPA, curriculum, academic policies, accreditation
- Agriculture: farming, USDA, food safety, agricultural standards, crop management, livestock
- Manufacturing: production processes, quality control, ISO standards, industrial safety, production lines
- Technology: software development, IT security, data centers, cybersecurity, software compliance
- Retail: consumer goods, retail operations, point of sale, inventory management, customer service
- Energy: power generation, oil and gas, renewable energy, EPA emissions, energy regulations
- Construction: building codes, OSHA construction, safety protocols, construction standards
- Legal: legal compliance, regulatory affairs, contract management, legal procedures
- General: if the document doesn't clearly fit into a specific industry or covers multiple sectors"""

    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {"role": "system", "content": "You are an industry classifier. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=300,
    )
    text = response.choices[0].message.content.strip().strip("`").strip()
    if text.startswith("json"):
        text = text[4:].strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
        else:
            return _rule_based_detect_industry(full_text, ai_error="Invalid JSON")
    
    industry = str(result.get("industry", "General")).strip()
    # Normalize industry names
    industry_map = {
        "pharma": "Pharma/Healthcare",
        "healthcare": "Pharma/Healthcare",
        "health": "Pharma/Healthcare",
        "pharmaceutical": "Pharma/Healthcare",
        "medical": "Pharma/Healthcare",
    }
    industry_lower = industry.lower()
    for key, value in industry_map.items():
        if key in industry_lower:
            industry = value
            break
    
    return {
        "industry": industry if industry in ["Finance", "Pharma/Healthcare", "Education", "Agriculture", "Manufacturing", "Technology", "Retail", "Energy", "Construction", "Legal", "General"] else "General",
        "confidence": str(result.get("confidence", "Medium"))[:20],
        "reason": str(result.get("reason", "Industry detected based on document content."))[:500],
    }


def _rule_based_detect_industry(full_text, ai_error=None):
    text_lower = full_text.lower()
    
    industry_keywords = {
        "Finance": [
            "bank", "securities", "sec", "fdic", "financial reporting", "accounting", "tax compliance",
            "investment", "trading", "audit", "financial statement", "cfpb", "finra", "irs", "treasury",
            "capital", "loan", "credit", "mortgage", "compliance officer", "financial controls"
        ],
        "Pharma/Healthcare": [
            "fda", "pharmaceutical", "drug", "clinical trial", "medical device", "hipaa", "healthcare",
            "patient", "prescription", "gmp", "good manufacturing practice", "fda approval", "regulatory affairs",
            "pharmacy", "hospital", "medical", "health", "biotechnology", "biotech"
        ],
        "Education": [
            "education", "school", "university", "student", "ferpa", "curriculum", "academic", "accreditation",
            "educational institution", "campus", "tuition", "enrollment", "student data", "educational policy"
        ],
        "Agriculture": [
            "agriculture", "farming", "usda", "crop", "livestock", "food safety", "agricultural", "farm",
            "harvest", "agricultural standards", "organic", "pesticide", "fertilizer", "agricultural compliance"
        ],
        "Manufacturing": [
            "manufacturing", "production", "iso", "quality control", "production line", "industrial",
            "assembly", "factory", "manufacturing process", "production facility", "industrial safety"
        ],
        "Technology": [
            "software", "it security", "cybersecurity", "data center", "technology", "software development",
            "information technology", "cyber", "network security", "it infrastructure", "cloud computing"
        ],
        "Retail": [
            "retail", "consumer", "point of sale", "inventory", "retail store", "customer service",
            "merchandise", "retail operations", "consumer goods", "sales floor"
        ],
        "Energy": [
            "energy", "power", "oil", "gas", "renewable", "emissions", "epa", "power generation",
            "energy sector", "electricity", "petroleum", "nuclear", "solar", "wind energy"
        ],
        "Construction": [
            "construction", "building code", "osha construction", "construction site", "building",
            "construction safety", "construction project", "contractor", "construction standards"
        ],
        "Legal": [
            "legal compliance", "regulatory affairs", "contract", "legal procedure", "attorney",
            "legal department", "compliance legal", "regulatory compliance", "legal review"
        ],
    }
    
    scores = {}
    for industry, keywords in industry_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[industry] = score
    
    if not scores:
        return {
            "industry": "General",
            "confidence": "Low",
            "reason": "No specific industry indicators found. Document appears to be general-purpose." + (f" (AI unavailable: {ai_error})" if ai_error else "")
        }
    
    # Get the industry with highest score
    detected_industry = max(scores.items(), key=lambda x: x[1])[0]
    max_score = scores[detected_industry]
    total_keywords = sum(len(keywords) for keywords in industry_keywords.values())
    
    confidence = "High" if max_score >= 5 else "Medium" if max_score >= 2 else "Low"
    
    reason = f"Document contains {max_score} keyword(s) related to {detected_industry} industry."
    if ai_error:
        reason += f" (AI unavailable: {ai_error})"
    
    return {
        "industry": detected_industry,
        "confidence": confidence,
        "reason": reason
    }


def is_document_sop(full_text, use_ai=True):
    """
    Detect if the uploaded document is a company SOP (or similar policy/compliance document).
    Returns: { "is_sop": bool, "reason": str, "document_type": str }
    """
    if not full_text or not full_text.strip():
        return {"is_sop": False, "reason": "No text content could be extracted from the document.", "document_type": "Unknown"}

    if use_ai:
        client = get_grok_client()
        if client is not None:
            try:
                return _ai_is_document_sop(client, full_text)
            except Exception as e:
                return _rule_based_is_sop(full_text, ai_error=str(e)[:80])
    return _rule_based_is_sop(full_text)


def _ai_is_document_sop(client, full_text):
    # Send a representative sample (first and last parts) to stay within token limits
    sample = full_text[:6000].strip()
    if len(full_text) > 8000:
        sample += "\n\n[... document continues ...]\n\n" + full_text[-2000:].strip()

    prompt = f"""You are a document classifier. Determine whether the following document is a company Standard Operating Procedure (SOP), policy document, compliance manual, or similar formal business procedure document that governs how an organization operates.

DOCUMENT CONTENT (excerpt):
{sample}

Respond with valid JSON only, no markdown:
{{
    "is_sop": true or false,
    "reason": "One or two sentences explaining why this is or is not an SOP/policy document.",
    "document_type": "Brief label for the document type if not an SOP (e.g. 'Marketing brochure', 'Recipe', 'Personal letter', 'Technical manual'). If it IS an SOP, use 'Company SOP or policy document'."
}}

Consider as SOP-like: Standard Operating Procedures, company policies, compliance manuals, quality manuals, HR handbooks, safety manuals, regulatory procedure documents. Reject: recipes, fiction, personal correspondence, generic articles, marketing copy (unless clearly a policy), non-organizational content."""

    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {"role": "system", "content": "You are a document classifier. Respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=400,
    )
    text = response.choices[0].message.content.strip().strip("`").strip()
    if text.startswith("json"):
        text = text[4:].strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
        else:
            return _rule_based_is_sop(full_text, ai_error="Invalid JSON")
    return {
        "is_sop": bool(result.get("is_sop", False)),
        "reason": str(result.get("reason", "Unable to determine."))[:500],
        "document_type": str(result.get("document_type", "Unknown"))[:200],
    }


def _rule_based_is_sop(full_text, ai_error=None):
    text_lower = full_text.lower()
    sop_indicators = [
        "standard operating procedure", "sop", "company policy", "policies and procedures",
        "compliance with", "applicable regulations", "scope", "purpose", "procedure",
        "section 1", "section 2", "policy statement", "responsibilities", "references",
        "document control", "revision history", "approved by", "effective date",
        "workplace safety", "data protection", "hr policy", "quality assurance",
    ]
    non_sop_indicators = [
        "recipe", "ingredients", "fiction", "chapter one", "dear sir", "yours sincerely",
        "once upon a time", "blog post", "newsletter", "advertisement",
    ]
    score = sum(1 for kw in sop_indicators if kw in text_lower)
    non_score = sum(1 for kw in non_sop_indicators if kw in text_lower)
    is_sop = score >= 2 and non_score == 0
    reason = "Document contains SOP-like structure and terminology (sections, policies, procedures)." if is_sop else "Document does not appear to be a company SOP or policy document based on structure and keywords."
    if ai_error:
        reason += f" (AI check unavailable: {ai_error})"
    doc_type = "Company SOP or policy document" if is_sop else "Likely not an SOP (generic or other document type)"
    return {"is_sop": is_sop, "reason": reason, "document_type": doc_type}


def analyze_full_document_compliance(full_text, regulations, rag_engine, use_ai=True):
    """
    Analyze the full uploaded document as a whole against regulations. Returns a single
    dynamic report: overall_score, risk_level, summary, findings[], citations, etc.
    """
    if not full_text or not full_text.strip():
        return _empty_full_document_result("No document text to analyze.")

    # RAG: retrieve relevant regulations for the entire document (use first N chars for query)
    query_text = full_text[:15000] if len(full_text) > 15000 else full_text
    matched_regs = rag_engine.retrieve_relevant_regulations(query_text, clause_category=None, top_k=12) if rag_engine else []

    if use_ai:
        client = get_grok_client()
        if client is not None:
            try:
                return _ai_full_document_analysis(client, full_text, matched_regs)
            except Exception as e:
                return _rule_based_full_document_analysis(full_text, matched_regs, rag_engine=rag_engine, ai_error=str(e)[:80])
    return _rule_based_full_document_analysis(full_text, matched_regs, rag_engine=rag_engine)


def _ai_full_document_analysis(client, full_text, matched_regs):
    doc_sample = full_text[:12000].strip()
    if len(full_text) > 14000:
        doc_sample += "\n\n[... document continues ...]\n\n" + full_text[-3000:].strip()

    reg_context = ""
    citations = []
    for i, match in enumerate(matched_regs[:10]):
        reg = match["regulation"]
        reg_context += f"\n--- Regulation {i+1} ---\nSource: {reg.get('source_name')}\nURL: {reg.get('source_url')}\nTitle: {reg.get('title')}\nContent: {reg.get('text', '')[:600]}\n"
        citations.append({
            "source": reg.get("source_name", "Unknown"),
            "url": reg.get("source_url", "#"),
            "title": reg.get("title", "Unknown"),
            "relevance_score": match.get("similarity_score", 0),
        })

    prompt = f"""You are a compliance expert. Review the ENTIRE document below as a whole and assess its compliance with the given regulations. Base your assessment only on the document and regulations provided. Be specific and reference actual sections/themes from the document.

FULL DOCUMENT (excerpt):
{doc_sample}

RELEVANT REGULATIONS:
{reg_context}

Respond with valid JSON only (no markdown), in this exact structure:
{{
    "overall_score": <number 0-100>,
    "overall_risk_level": "Low" | "Medium" | "High",
    "executive_summary": "2-4 sentences summarizing the document's compliance posture based on its actual content.",
    "findings": [
        {{
            "area": "Short label (e.g. section name or theme from the document)",
            "status": "compliant" | "partially_compliant" | "non_compliant" | "outdated",
            "risk_level": "Low" | "Medium" | "High",
            "issue": "Brief description of what is wrong or missing, or 'None' if compliant",
            "suggestion": "Specific recommended action or 'No change needed'",
            "applicable_regulations": ["regulation name or source"]
        }}
    ],
    "missing_elements": ["list of missing regulatory elements across the document"],
    "compliance_debt_estimate": <number, estimated cost/risk value in dollars if issues are not addressed>,
    "analysis_method": "AI (Grok)"
}}

Generate findings dynamically from the document content. Do not use generic placeholders. Reference actual sections, policies, or themes present in the document. If the document is very short or vague, say so in the executive_summary and adjust findings accordingly."""

    response = client.chat.completions.create(
        model="grok-3-mini",
        messages=[
            {"role": "system", "content": "You are a regulatory compliance expert. Respond with valid JSON only, no markdown."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=2500,
    )
    text = response.choices[0].message.content.strip().strip("`").strip()
    if text.startswith("json"):
        text = text[4:].strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
        else:
            return _rule_based_full_document_analysis(full_text, matched_regs, rag_engine=None, ai_error="Invalid JSON")
    result["citations"] = citations
    result.setdefault("findings", [])
    result.setdefault("missing_elements", [])
    result.setdefault("executive_summary", "Full-document compliance analysis completed.")
    result.setdefault("compliance_debt_estimate", 0)
    return result


def _rule_based_full_document_analysis(full_text, matched_regs, rag_engine=None, ai_error=None):
    """
    Dynamic rule-based analysis:
    - Split document into clauses/sections
    - For each section, retrieve the most relevant regulations (RAG) and generate a finding
    This avoids static/generic findings and ties issues to the specific uploaded document text.
    """
    text_lower = full_text.lower()

    clauses = parse_sop_into_clauses(full_text) or []
    # Keep a reasonable number of sections so UI/export stays usable
    clauses = clauses[:12]

    def _has_enforceable_language(txt: str) -> bool:
        t = (txt or "").lower()
        return any(k in t for k in [" must ", " shall ", " required ", " ensure ", " will "])

    def _extract_requirement_sentence(reg_text: str) -> str:
        if not reg_text:
            return ""
        # Split into "sentences" in a tolerant way for scraped text
        parts = re.split(r"(?<=[.!?])\s+|\n+", reg_text.strip())
        for p in parts:
            s = p.strip()
            if not s:
                continue
            sl = s.lower()
            if any(w in sl for w in ["must", "shall", "required", "ensure", "provide", "maintain"]):
                return s[:260]
        # fallback
        return reg_text.strip().replace("\n", " ")[:260]

    findings = []
    section_scores = []
    all_citations = []
    
    # Detect industry for industry-specific scoring (if available)
    detected_industry = None
    if hasattr(rag_engine, '_industry') and rag_engine._industry:
        detected_industry = rag_engine._industry
    # Try to infer from document if not set
    if not detected_industry:
        industry_result = detect_industry(full_text, use_ai=False)
        detected_industry = industry_result.get("industry", "General")

    for clause in clauses:
        title = clause.get("title", "Section")
        ctext = clause.get("text", "") or ""
        cat = clause.get("category")

        clause_query = f"{title}\n{ctext[:1800]}"
        matches = rag_engine.retrieve_relevant_regulations(clause_query, clause_category=cat, top_k=4) if rag_engine else (matched_regs[:4] if matched_regs else [])

        avg_sim = sum(m.get("similarity_score", 0) for m in matches) / len(matches) if matches else 0.0
        top_sim = matches[0].get("similarity_score", 0.0) if matches else 0.0
        enforceable = _has_enforceable_language(ctext)

        top_reg = matches[0]["regulation"] if matches else None
        top_title = (top_reg or {}).get("title", "relevant regulation")
        top_text = (top_reg or {}).get("text", "") or ""
        req_sentence = _extract_requirement_sentence(top_text)

        # Calculate dynamic compliance score using new formula
        regulatory_alignment = calculate_regulatory_alignment_score(matches, avg_sim, top_sim)
        language_strength = calculate_language_strength_score(ctext)
        completeness = calculate_completeness_score(ctext, cat or "General", matches)
        risk_penalty = calculate_risk_penalty(ctext, matches, avg_sim)
        
        # Count missing critical elements
        missing_critical = 0
        total_elements = 8  # Approximate number of elements checked
        if not enforceable:
            missing_critical += 1
        if not matches or len(matches) == 0:
            missing_critical += 1
        if completeness < 0.5:
            missing_critical += 2
        
        clause_score = calculate_compliance_score(
            regulatory_alignment_score=regulatory_alignment,
            language_strength_score=language_strength,
            completeness_score=completeness,
            risk_penalty=risk_penalty,
            industry=detected_industry,
            has_citations=len(matches) > 0,
            has_enforceable_language=enforceable,
            missing_critical_elements=missing_critical,
            total_elements_checked=total_elements
        )

        # Determine status and risk level based on score
        if clause_score >= 75:
            status = "compliant"
            risk_level = "Low"
            issue = "None" if clause_score >= 85 else "Minor improvements possible for enhanced compliance."
            suggestion = "No change needed" if clause_score >= 85 else "Consider adding more specific regulatory references for enhanced compliance."
        elif clause_score >= 50:
            status = "partially_compliant"
            risk_level = "Medium"
            if not enforceable:
                issue = f"Section is relevant to {top_title} but uses weak/vague language (missing must/shall/required)."
            else:
                issue = f"Section partially aligns with {top_title}; some required elements appear missing or unclear."
            suggestion = f"Add an explicit requirement aligned with {top_title}: “{req_sentence}”" if req_sentence else f"Align this section more closely with {top_title} and add enforceable requirements."
        else:
            status = "non_compliant"
            risk_level = "High"
            if not matches:
                issue = "No strong regulation match for this section; it may be missing specific compliance requirements."
                suggestion = "Add enforceable requirements (must/shall), reference the governing regulation, assign an owner, and define a review cadence."
            else:
                issue = f"Section has weak alignment with relevant regulations (top match: {top_title})."
                suggestion = f"Update the section to include required elements from {top_title}, for example: “{req_sentence}”" if req_sentence else f"Update this section to include required elements from {top_title}."

        applicable = []
        for m in matches[:3]:
            r = m.get("regulation", {})
            t = (r.get("title") or "").strip()
            if t:
                applicable.append(t)

        findings.append({
            "area": str(title)[:80],
            "status": status,
            "risk_level": risk_level,
            "issue": issue,
            "suggestion": suggestion,
            "applicable_regulations": applicable,
        })

        section_scores.append(max(0, min(100, int(clause_score))))

        for m in matches[:2]:
            r = m.get("regulation", {})
            all_citations.append({
                "source": r.get("source_name", "Unknown"),
                "url": r.get("source_url", "#"),
                "title": r.get("title", "Unknown"),
                "relevance_score": m.get("similarity_score", 0),
            })

    # Calculate overall score using weighted average (weight by section importance/length)
    if section_scores:
        # Use geometric mean for better representation of overall compliance
        # Geometric mean is more sensitive to low scores (non-compliance)
        if all(s > 0 for s in section_scores):
            # Calculate product manually for compatibility
            product = 1.0
            for s in section_scores:
                product *= s
            overall_score = math.pow(product, 1.0 / len(section_scores))
        else:
            # If any score is 0, use arithmetic mean
            overall_score = sum(section_scores) / len(section_scores)
        overall_score = round(overall_score)
    else:
        # Calculate document-level score if no sections
        doc_regulatory_alignment = calculate_regulatory_alignment_score(matched_regs, 
            sum(m.get("similarity_score", 0) for m in matched_regs) / len(matched_regs) if matched_regs else 0.0,
            matched_regs[0].get("similarity_score", 0.0) if matched_regs else 0.0)
        doc_language_strength = calculate_language_strength_score(full_text)
        doc_completeness = calculate_completeness_score(full_text, "General", matched_regs)
        doc_risk_penalty = calculate_risk_penalty(full_text, matched_regs, 
            sum(m.get("similarity_score", 0) for m in matched_regs) / len(matched_regs) if matched_regs else 0.0)
        
        overall_score = calculate_compliance_score(
            regulatory_alignment_score=doc_regulatory_alignment,
            language_strength_score=doc_language_strength,
            completeness_score=doc_completeness,
            risk_penalty=doc_risk_penalty,
            industry=detected_industry,
            has_citations=len(matched_regs) > 0,
            has_enforceable_language=_has_enforceable_language(full_text),
            missing_critical_elements=0,
            total_elements_checked=1
        )
    
    overall_risk = "Low" if overall_score >= 70 else "Medium" if overall_score >= 45 else "High"

    # de-duplicate citations (by url+title) and keep top ones
    seen = set()
    dedup = []
    for c in sorted(all_citations, key=lambda x: x.get("relevance_score", 0), reverse=True):
        k = (c.get("url"), c.get("title"))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(c)
        if len(dedup) >= 10:
            break

    missing_elements = []
    if "review" not in text_lower and "audit" not in text_lower:
        missing_elements.append("Review / audit cadence for policies")
    if "responsible" not in text_lower and "owner" not in text_lower:
        missing_elements.append("Responsible owner / role assignments")
    if "training" in text_lower and "frequency" not in text_lower:
        # heuristic only
        missing_elements.append("Training frequency / documentation details")

    method = "Rule-based (section-based, RAG-matched)"
    if ai_error:
        method += f" (AI unavailable: {ai_error})"

    exec_summary = (
        f"Document reviewed using {method}. Findings were generated per section by matching that section’s text to the most relevant scraped regulations. "
        f"Overall compliance is estimated at {overall_score}% with {overall_risk} risk."
    )

    return {
        "overall_score": overall_score,
        "overall_risk_level": overall_risk,
        "executive_summary": exec_summary,
        "findings": findings,
        "missing_elements": missing_elements,
        "compliance_debt_estimate": (100 - overall_score) * 120,
        "citations": dedup,
        "analysis_method": method,
    }


def _empty_full_document_result(message):
    return {
        "overall_score": 0,
        "overall_risk_level": "High",
        "executive_summary": message,
        "findings": [],
        "missing_elements": [],
        "compliance_debt_estimate": 0,
        "citations": [],
        "analysis_method": "None",
    }


def analyze_clause_compliance(clause, matched_regulations, use_ai=False):
    if use_ai:
        client = get_grok_client()
        if client is not None:
            try:
                return _ai_analyze(client, clause, matched_regulations)
            except Exception as e:
                return _rule_based_analyze(clause, matched_regulations, ai_error=str(e)[:80])
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
        "compliant": [
            "shall comply", "in accordance with", "as required by", "pursuant to",
            "in compliance", "adhering to", "follows", "meets requirements", "in line with",
            "per regulatory", "as mandated", "documented procedure", "written policy",
            "retention period", "breach notification", "access control", "encryption",
        ],
        "risk": [
            "may", "optional", "when possible", "if applicable", "best effort",
            "should", "recommended", "consider", "where practicable", "as appropriate",
        ],
        "outdated": [
            "superseded", "replaced by", "no longer", "deprecated",
            "previous version", "old standard", "former", "legacy",
        ],
    }

    # First, identify missing elements for completeness calculation
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
    
    # Calculate dynamic compliance score using new formula
    clause_text = clause.get("text", "")
    has_matches = len(matched_regulations) > 0
    avg_similarity = sum(m["similarity_score"] for m in matched_regulations) / len(matched_regulations) if matched_regulations else 0.0
    top_similarity = matched_regulations[0].get("similarity_score", 0.0) if matched_regulations else 0.0
    
    # Check for outdated language
    outdated_score = sum(1 for kw in compliance_indicators["outdated"] if kw in text_lower)
    if outdated_score >= 2:
        # Heavy penalty for outdated content
        regulatory_alignment = 0.1
        language_strength = 0.1
        completeness = 0.2
        risk_penalty = 0.9
    else:
        # Calculate normal scores
        regulatory_alignment = calculate_regulatory_alignment_score(matched_regulations, avg_similarity, top_similarity)
        language_strength = calculate_language_strength_score(clause_text)
        completeness = calculate_completeness_score(clause_text, category, matched_regulations)
        risk_penalty = calculate_risk_penalty(clause_text, matched_regulations, avg_similarity)
    
    # Count missing critical elements
    missing_critical = len(missing)
    total_elements = len(category_requirements.get(category, []))
    
    # Detect industry for industry-specific scoring
    industry = "General"  # Default, can be enhanced with context
    
    score = calculate_compliance_score(
        regulatory_alignment_score=regulatory_alignment,
        language_strength_score=language_strength,
        completeness_score=completeness,
        risk_penalty=risk_penalty,
        industry=industry,
        has_citations=has_matches,
        has_enforceable_language=any(kw in text_lower for kw in ["must", "shall", "required", "mandatory"]),
        missing_critical_elements=missing_critical,
        total_elements_checked=max(total_elements, 1)
    )
    
    # Determine status and risk level based on score
    if outdated_score >= 2:
        status = "outdated"
        risk_level = "High"
    elif score >= 75:
        status = "compliant"
        risk_level = "Low"
    elif score >= 50:
        status = "partially_compliant"
        risk_level = "Medium"
    else:
        status = "non_compliant"
        risk_level = "High" if not has_matches else "Medium"

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
        "reasoning": f"Based on dynamic compliance scoring (regulatory alignment: {regulatory_alignment:.2f}, language strength: {language_strength:.2f}, completeness: {completeness:.2f}), this clause shows {status.replace('_', ' ')} characteristics with a score of {score}.",
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
