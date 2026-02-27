import os
import json
import re
import random
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
    for i, match in enumerate(matched_regs[:10], start=1):
        reg = match["regulation"]
        reg_context += f"\n--- Regulation [{i}] ---\nSource: {reg.get('source_name')}\nURL: {reg.get('source_url')}\nTitle: {reg.get('title')}\nContent: {reg.get('text', '')[:600]}\n"
        citations.append({
            "id": i,
            "source": reg.get("source_name", "Unknown"),
            "url": reg.get("source_url", "#"),
            "title": reg.get("title", "Unknown"),
            "relevance_score": match.get("similarity_score", 0),
        })

    prompt = f"""You are a senior regulatory compliance consultant. Review the ENTIRE document below and assess its compliance with the provided regulations.

FULL DOCUMENT (excerpt):
{doc_sample}

RELEVANT REGULATIONS:
{reg_context}

Respond with valid JSON only (no markdown), in this exact structure:
{{
    "overall_score": <number 0-100>,
    "overall_risk_level": "Low" | "Medium" | "High",
    "executive_summary": "Detailed summary referencing specific document themes.",
    "findings": [
        {{
            "area": "Specific section name or theme (e.g. 'Section 4.1 Data Encryption' or 'Employee Training Policy')",
            "status": "compliant" | "partially_compliant" | "non_compliant" | "outdated",
            "risk_level": "Low" | "Medium" | "High",
            "issue": "Specific technical mismatch or gap found in this exact section.",
            "suggestion": "CONSULTANT-STYLE INSTRUCTION. Must be specific to this document. E.g. 'Update Section 2.1 to explicitly include 256-bit AES encryption requirements as per Regulation [1]'. DO NOT use generic advice like 'Update policy'.",
            "text": "Exact short snippet from the document related to this finding",
            "applicable_regulations": ["Regulation [ID] (Source Name)"]
        }}
    ],
    "missing_elements": ["List of specific clauses or controls currently missing from the document."],
    "compliance_debt_estimate": <number>,
    "analysis_method": "AI (Grok)"
}}

CRITICAL: Every suggestion must be actionable and document-specific. Use specific "Regulation [ID]" (e.g., "Regulation [1]") from the list in "applicable_regulations". If the document is vague, providing the exact text to be added is highly encouraged."""

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

    for clause in clauses:
        title = clause.get("title", "Section")
        ctext = clause.get("text", "") or ""
        cat = clause.get("category")

        clause_query = f"{title}\n{ctext[:1800]}"
        matches = rag_engine.retrieve_relevant_regulations(clause_query, clause_category=cat, top_k=4) if rag_engine else (matched_regs[:4] if matched_regs else [])

        avg_sim = sum(m.get("similarity_score", 0) for m in matches) / len(matches) if matches else 0.0
        enforceable = _has_enforceable_language(ctext)

        top_reg = matches[0]["regulation"] if matches else None
        top_title = (top_reg or {}).get("title", "relevant regulation")
        top_text = (top_reg or {}).get("text", "") or ""
        req_sentence = _extract_requirement_sentence(top_text)

        # Decide status/risk and craft issue/suggestion dynamically from the specific clause text
        # Extract specific section details for targeted issues
        section_keywords = []
        for kw in ["procedure", "process", "policy", "requirement", "responsibility", "approval", "review", "audit", "record"]:
            if kw in ctext.lower():
                section_keywords.append(kw)
        keywords_display = ", ".join(section_keywords[:3]) if section_keywords else "content"
        
        # Generate varied issue descriptions to avoid repetition
        issue_variations = {
            "no_match_1": f"'{title}' lacks regulatory foundation. Addresses {keywords_display} but has no connection to compliance requirements.",
            "no_match_2": f"No regulatory alignment found for '{title}'. The {keywords_display} described here requires external compliance reference.",
            "no_match_3": f"'{title}' appears disconnected from regulatory framework. Consider mapping this {keywords_display} to applicable standards.",
            "partial_1": f"'{title}' relates to {top_title} but lacks mandatory language. Text is permissive rather than prescriptive.",
            "partial_2": f"'{title}' touches on {top_title}, but enforceable requirements are missing or unclear.",
            "partial_3": f"'{title}' has some regulatory connection to {top_title}, though critical controls lack specificity.",
            "weak_1": f"'{title}' has minimal alignment with {top_title}. Current structure does not meet regulatory expectations.",
            "weak_2": f"'{title}'s approach to {top_title} needs strengthening. Requirements are not sufficiently detailed.",
            "weak_3": f"'{title}' falls short of {top_title} standards. The outlined {keywords_display} require more rigorous framework.",
        }
        
        if not matches:
            status = "non_compliant"
            risk_level = "High"
            # Use varied wording
            issue = random.choice([issue_variations["no_match_1"], issue_variations["no_match_2"], issue_variations["no_match_3"]])
            # Dynamic suggestion referencing the specific area content
            area_content = f"the {keywords_display}" if keywords_display != "content" else "this section"
            suggestion = f"Establish a formal regulatory baseline for '{title}'. Substantially revise {area_content} to include mandatory 'shall/must' requirements, specific roles, and a measurable verification frequency."
            clause_score = 25
        else:
            if avg_sim >= 0.18 and enforceable:
                status = "compliant"
                risk_level = "Low"
                issue = "None"
                suggestion = f"The current {keywords_display} in '{title}' aligns with {top_title}. No immediate regulatory changes required."
                clause_score = 85 + int(min(0.15, avg_sim - 0.18) * 100)
            elif avg_sim >= 0.10:
                status = "partially_compliant"
                risk_level = "Medium"
                reg_fragment = req_sentence[:100] + "..." if len(req_sentence) > 100 else req_sentence
                if not enforceable:
                    issue = issue_variations["partial_1"] if random.random() < 0.5 else issue_variations["partial_2"]
                    suggestion = f"Strengthen '{title}' by converting passive language to direct requirements. Requirement to append: '{reg_fragment}'."
                else:
                    issue = issue_variations["partial_3"]
                    suggestion = f"Enhance '{title}' by explicitly incorporating technical controls from {top_title}. Proposed addition: '{reg_fragment}'."
                clause_score = 45 + int(avg_sim * 150)
            else:
                status = "non_compliant"
                risk_level = "High"
                issue = random.choice([issue_variations["weak_1"], issue_variations["weak_2"], issue_variations["weak_3"]])
                reg_fragment = req_sentence[:100] + "..." if len(req_sentence) > 100 else req_sentence
                suggestion = f"Major restructuring required for '{title}'. Align with {top_title} framework. Key missing control: '{reg_fragment}'."
                clause_score = 30 + int(avg_sim * 120)

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
            "text": ctext[:300], # Include the actual section text or a snippet of it
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

    overall_score = int(sum(section_scores) / len(section_scores)) if section_scores else 0
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
    # Deduplicate and merge findings with identical or near-identical issues
    def _merge_findings(findings_list):
        """Merge identical/similar issue findings to avoid repetition"""
        if not findings_list or len(findings_list) <= 1:
            return findings_list
        
        def _similarity(s1, s2):
            """Simple word-overlap similarity metric"""
            w1 = set(s1.lower().split())
            w2 = set(s2.lower().split())
            if not w1 or not w2:
                return 0
            return len(w1 & w2) / len(w1 | w2)
        
        merged = []
        used = set()
        
        for i, f in enumerate(findings_list):
            if i in used:
                continue
            
            issue_text = f.get("issue", "").strip()
            if not issue_text or issue_text == "None":
                merged.append(f)
                used.add(i)
                continue
            
            # Find similar findings
            group = [i]
            for j in range(i + 1, len(findings_list)):
                if j in used:
                    continue
                other_issue = findings_list[j].get("issue", "").strip()
                if other_issue and other_issue != "None":
                    if _similarity(issue_text, other_issue) > 0.60:  # 60% word overlap = similar
                        group.append(j)
            
            # Merge the group
            if len(group) == 1:
                merged.append(f)
            else:
                # Combine areas
                areas = [findings_list[idx].get("area", f"Section {idx}") for idx in group]
                merged_area = "; ".join(areas[:3])  # Limit to 3 areas
                if len(group) > 3:
                    merged_area += f" (+{len(group)-3} more)"
                
                # Use the most specific issue from the group (longest one with most detail)
                best_issue = max([findings_list[idx].get("issue", "") for idx in group], key=len)
                best_sugg = max([findings_list[idx].get("suggestion", "") for idx in group], key=len)
                
                # Collect all applicable regulations
                all_regs = []
                for idx in group:
                    all_regs.extend(findings_list[idx].get("applicable_regulations", []))
                unique_regs = list(dict.fromkeys(all_regs))  # preserve order, remove duups
                
                merged_finding = {
                    "area": merged_area[:100],
                    "status": findings_list[group[0]].get("status", "partially_compliant"),
                    "risk_level": findings_list[group[0]].get("risk_level", "Medium"),
                    "issue": best_issue,
                    "suggestion": best_sugg,
                    "text": findings_list[group[0]].get("text", ""), # Keep original text snippet
                    "applicable_regulations": unique_regs[:5],
                }
                merged.append(merged_finding)
            
            for idx in group:
                used.add(idx)
        
        return merged
    
    findings = _merge_findings(findings)
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

Analyze this SOP clause against the provided regulations and respond in this exact JSON format. 

CRITICAL: Suggestions must be specific, technical instructions (e.g., "Amend Section X to state...")—NOT generic advice.

{{
    "compliance_status": "compliant" | "partially_compliant" | "non_compliant" | "outdated",
    "risk_level": "Low" | "Medium" | "High",
    "compliance_score": <number 0-100>,
    "summary": "Compliance summary specific to this clause.",
    "missing_elements": ["List of missing regulatory elements specific to this clause."],
    "suggested_correction": "Document-specific text or technical amendment instruction. Must be actionable and derived from the provided regulations.",
    "reasoning": "Legal/compliance reasoning linking this specific document text to the regulation.",
    "applicable_regulations": ["List of specific regulation names/sections"]
}}"""

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
    elif compliant_score >= 2 and avg_similarity > 0.12:
        status = "compliant"
        risk_level = "Low"
        score = min(98, 80 + compliant_score * 4 + int(avg_similarity * 30))
    elif compliant_score >= 1 and (avg_similarity > 0.08 or has_matches):
        status = "partially_compliant"
        risk_level = "Medium"
        score = min(75, 45 + compliant_score * 12 + int(avg_similarity * 50))
    elif avg_similarity > 0.15 and risk_score <= 1:
        status = "partially_compliant"
        risk_level = "Medium"
        score = 55
    elif risk_score >= 2:
        status = "partially_compliant"
        risk_level = "Medium"
        score = 45
    else:
        status = "non_compliant"
        risk_level = "High" if not has_matches else "Medium"
        score = max(15, min(35, 20 + int(avg_similarity * 80)))

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
