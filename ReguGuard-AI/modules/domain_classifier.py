"""
Domain classifier for SOP / policy documents.

Dynamic behavior:
- If `XAI_API_KEY` is set, we use Grok (x.ai) to classify the domain based on
  the document content (dynamic, not keyword-static).
- If AI is unavailable, we fall back to a *data-driven* keyword model loaded from
  `data/domain_definitions.json` (so domains/keywords can be updated without code changes).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple


DOMAIN_DEFINITIONS_FILE = os.path.join("data", "domain_definitions.json")


# Default domains (used if no JSON config exists)
# Simplified to 4 main categories: Pharma/Health, Industrial/Mining, Finance, General
DEFAULT_DOMAINS: Dict[str, List[str]] = {
    "Pharma / Health": [
        # Pharma/Drug-specific
        "patient",
        "clinical trial",
        "clinical research",
        "gmp",
        "good manufacturing practice",
        "gcp",
        "good clinical practice",
        "gdp",
        "good distribution practice",
        "pharma",
        "pharmaceutical",
        "drug substance",
        "medication",
        "medical device",
        "medicinal product",
        "adverse event",
        "pharmacovigilance",
        "fda",
        "ema",
        "mhra",
        "hipaa",
        "protected health information",
        "hospital",
        "clinic",
        "sponsor",
        "investigator site",
        "cfr 21",
        "title 21",
        "batch record",
        "protocol amendment",
        "informed consent",
        "subject enrollment",
        # Healthcare/Medical
        "healthcare facility",
        "medical professional",
        "patient care",
        "medical protocol",
        "treatment procedure",
        "clinical endpoint",
        "biomedical",
        "health record",
        "patient safety",
        "medical ethics",
    ],
    "Industrial / Mining": [
        # Core Mining Keywords (highest priority)
        "mining",
        "mine",
        "ore",
        "extraction",
        "extractive",
        "mining site",
        "mining facility",
        "mining operations",
        "mining operation",
        "open pit",
        "open pit mining",
        "open-pit",
        "open-pit mining",
        "underground mine",
        "underground mining",
        "surface mining",
        "subsurface",
        "mineable",
        "mineralization",
        "ore deposit",
        "ore production",
        "ore body",
        "ore grade",
        "mineral",
        "minerals",
        "mineral processing",
        # Mining Equipment & Operations
        "drill rig",
        "drilling",
        "drilling operation",
        "blast",
        "blasting",
        "blasting operation",
        "explosive",
        "explosives",
        "explosives handling",
        "detonation",
        "haul truck",
        "haul road",
        "shovel",
        "loader",
        "excavator",
        "dredge",
        "pump",
        "mill",
        "milling",
        "beneficiation",
        "concentration",
        "smelter",
        "smelting",
        # Mine Structure & Geology
        "pit wall",
        "slope stability",
        "mine ventilation",
        "ventilation system",
        "shaft",
        "decline",
        "stope",
        "stoping",
        "face",
        "working face",
        "rockburst",
        "water management",
        "groundwater",
        "dewatering",
        # Tailings & Waste
        "tailings",
        "tailings dam",
        "tailings storage facility",
        "tsf",
        "waste rock",
        "waste management",
        "mine waste",
        "disposal",
        # Mining Regulations & Safety
        "msha",
        "mine safety",
        "mining accident",
        "mining incident",
        "safety protocol",
        "ventilation standard",
        "occupational safety",
        # Manufacturing/Industrial
        "manufacturing line",
        "production line",
        "assembly line",
        "oee",
        "overall equipment effectiveness",
        "quality control",
        "qc laboratory",
        "equipment qualification",
        "maintenance schedule",
        "preventive maintenance",
        "safety stock",
        "warehouse",
        "inventory control",
        "iso 9001",
        "iso 14001",
        "production schedule",
        "batch number",
        "material specification",
        "workstation",
        "production capacity",
        "factory",
        "plant",
        "manufacturing process",
        # Food/Agriculture (part of industrial)
        "farm",
        "farming",
        "grower",
        "harvest",
        "crop",
        "pesticide",
        "fertilizer",
        "usda",
        "good agricultural practice",
        "gap certification",
        "gap program",
        "food safety",
        "haccp",
        "hazard analysis",
        "packhouse",
        "packing facility",
        "processing plant",
        "cold chain",
        "traceability",
        "food handler",
        "produce",
        "organic certification",
    ],
    "Finance": [
        # Banking/Financial
        "bank",
        "banking institution",
        "lending",
        "credit risk",
        "loan portfolio",
        "securities",
        "investment bank",
        "broker dealer",
        "finra",
        "sec",
        "basel accords",
        "aml",
        "anti-money laundering",
        "kyc",
        "know your customer",
        "sox",
        "sarbanes-oxley",
        "capital adequacy",
        "liquidity coverage",
        "deposit",
        "settlement",
        "trading",
        "portfolio management",
        "derivatives",
        "compliance officer",
        "risk management committee",
        "financial institution",
        "credit union",
        "savings bank",
        "insurance",
        "underwriting",
        "premium",
        "policy holder",
        "claims",
        "actuarial",
        "reserve",
        "asset management",
        "wealth management",
        "investment management",
        "hedge fund",
        "private equity",
        "venture capital",
    ],
}


def _load_domain_definitions() -> Dict[str, List[str]]:
    """
    Load domain definitions from `data/domain_definitions.json` if present.

    Expected JSON format:
    {
      "Mining / Extractive Industries": ["mining", "ore", ...],
      "Healthcare / Pharma": ["patient", "fda", ...]
    }
    """
    try:
        if os.path.exists(DOMAIN_DEFINITIONS_FILE):
            with open(DOMAIN_DEFINITIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
                # normalize to strings
                cleaned: Dict[str, List[str]] = {}
                for k, v in data.items():
                    label = str(k).strip()
                    kws = [str(x).strip().lower() for x in (v or []) if str(x).strip()]
                    if label and kws:
                        cleaned[label] = kws
                if cleaned:
                    return cleaned
    except Exception:
        pass
    return DEFAULT_DOMAINS


def _score_domain(text_lower: str, keywords: List[str]) -> float:
    """
    Score domain match with proper word boundaries and contextual weighting.
    Uses word boundaries to avoid false positives like "mine" matching "undermine".
    Gives extra weight to critical domain-specific keywords.
    """
    # Core keywords that strongly indicate a domain (highest priority)
    mining_core = {"mining", "ore", "mine", "extraction", "extractive", "mineral", "milling", "smelting"}
    pharma_core = {"pharmaceutical", "pharma", "clinical trial", "fda", "gmp", "drug"}
    finance_core = {"bank", "trading", "securities", "investment", "aml", "kyc"}
    
    score = 0.0
    
    for kw in keywords:
        # Create a regex pattern with word boundaries
        pattern = r'\b' + re.escape(kw) + r'\b'
        matches = len(re.findall(pattern, text_lower))
        
        if matches > 0:
            # Check if keyword is a core domain indicator
            kw_lower = kw.lower()
            is_core_mining = any(core in kw_lower for core in mining_core)
            is_core_pharma = any(core in kw_lower for core in pharma_core)
            is_core_finance = any(core in kw_lower for core in finance_core)
            
            # Weight calculation:
            # - Core keywords get 5.0x boost (critical domain signals)
            # - Multi-word keywords: 3.0x base weight
            # - Short keywords (≤4 chars): 2.5x base weight (acronyms - rare & important)
            # - Regular keywords: 2.0x base weight
            # - Multiple occurrences show domain relevance (cap at 3 for diminishing returns)
            
            if is_core_mining or is_core_pharma or is_core_finance:
                base_weight = 5.0
            elif " " in kw:
                base_weight = 3.0
            elif len(kw) <= 4:
                base_weight = 2.5
            else:
                base_weight = 2.0
            
            keyword_score = base_weight * min(matches, 3)  # Cap at 3 occurrences
            score += keyword_score
    
    return score


def _ai_detect_domain(full_text: str, allowed_domains: List[str]) -> Optional[Dict[str, Any]]:
    """
    Use Grok (x.ai) to dynamically classify the SOP domain.
    Returns a dict or None if AI is unavailable.
    """
    # Lazy import to avoid any import cycles at module load time
    try:
        from modules.compliance_analyzer import get_grok_client
    except Exception:
        return None

    client = get_grok_client()
    if client is None:
        return None

    sample = (full_text or "").strip()
    sample = sample[:9000] + ("\n\n[... truncated ...]\n\n" + sample[-1500:] if len(sample) > 12000 else "")

    prompt = f"""You are a domain classifier for company SOP/policy documents.
Classify the document into ONE best-fit domain from the allowed list.

Allowed domains:
{json.dumps(allowed_domains, indent=2)}

DOCUMENT (excerpt):
{sample}

Respond with valid JSON only (no markdown):
{{
  "domain": "<one of allowed domains OR 'General'>",
  "confidence": <number 0.0 to 1.0>,
  "reason": "One short sentence citing the main signals."
}}

Rules:
- Choose the closest matching domain from the allowed list.
- If nothing clearly matches, use "General".
"""

    try:
        resp = client.chat.completions.create(
            model="grok-3-mini",
            messages=[
                {"role": "system", "content": "You are a domain classifier. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        text = (resp.choices[0].message.content or "").strip().strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
    except Exception:
        return None
    return None


def detect_document_domain(full_text: str, use_ai: bool = True) -> Dict[str, object]:
    """
    Infer the primary domain of the SOP / policy document with improved accuracy.

    Returns:
        {
            "domain": "<best label or 'General'>",
            "confidence": <0.0 - 1.0>,
            "reason": "<short explanation>",
        }
    """
    if not full_text or not full_text.strip():
        return {
            "domain": "General",
            "confidence": 0.0,
            "reason": "No text to analyze.",
        }

    domain_defs = _load_domain_definitions()
    allowed_domains = sorted(set(list(domain_defs.keys()) + ["General"]))

    # 1) Dynamic AI classification (if enabled + API key available)
    if use_ai:
        ai = _ai_detect_domain(full_text, allowed_domains=allowed_domains)
        if isinstance(ai, dict):
            domain = str(ai.get("domain", "") or "").strip()
            if domain not in allowed_domains:
                domain = "General"
            conf = ai.get("confidence", 0.0)
            try:
                conf_f = float(conf)
            except Exception:
                conf_f = 0.0
            return {
                "domain": domain,
                "confidence": max(0.0, min(1.0, conf_f)),
                "reason": str(ai.get("reason", "Classified using AI (Grok)."))[:300],
            }

    # 2) Data-driven keyword fallback (still configurable via JSON)
    sample = full_text[:50000]  # Increased sample size for better analysis
    text_lower = re.sub(r"\s+", " ", sample.lower())

    scores: List[Tuple[str, float]] = []
    for label, kws in domain_defs.items():
        s = _score_domain(text_lower, kws)
        scores.append((label, s))

    scores.sort(key=lambda x: x[1], reverse=True)
    best_label, best_score = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0

    # Improved confidence calculation
    if best_score <= 0:
        return {
            "domain": "General",
            "confidence": 0.0,
            "reason": "No strong domain-specific signals detected; using general SME regulations.",
        }

    # Calculate confidence based on:
    # 1. How strong the best match is
    # 2. How much it outperforms the second-best match (separation)
    # The stronger the signal and the more it stands out from others, the higher the confidence
    
    # Normalize score to 0-1 range based on reasonable maximum
    # A realistic maximum is around 50 points for a highly domain-specific document
    normalized_best = min(1.0, best_score / 50.0)
    
    # Consider the gap between best and second (higher gap = more confidence)
    if second_score > 0:
        gap_ratio = best_score / (best_score + second_score + 0.1)
    else:
        gap_ratio = 1.0
    
    # Combine: higher weight on the raw score, with gap as a tiebreaker
    confidence = (normalized_best * 0.7 + gap_ratio * 0.3)
    confidence = min(0.95, max(0.3, confidence))  # Clamp between 0.3 and 0.95

    reason = (
        f"Detected domain '{best_label}' using keyword signals "
        f"(score: {best_score:.1f}, separation: {best_score - second_score:.1f})."
    )

    return {
        "domain": best_label,
        "confidence": round(confidence, 2),
        "reason": reason,
    }

