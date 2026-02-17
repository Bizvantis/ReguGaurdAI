import requests
from bs4 import BeautifulSoup
import re
import time
import hashlib
import json
import os

DATA_DIR = "data"
CACHE_FILE = os.path.join(DATA_DIR, "regulation_cache.json")

DEFAULT_SOURCES = [
    {
        "name": "OSHA - Workplace Safety Standards",
        "url": "https://www.osha.gov/laws-regs/regulations/standardnumber",
        "category": "Health & Safety",
        "selector": "main, article, .content, body",
        "industries": ["General", "Manufacturing", "Construction", "Energy", "Retail"],
    },
    {
        "name": "EPA - Environmental Regulations",
        "url": "https://www.epa.gov/regulatory-information/laws-and-executive-orders",
        "category": "Environmental",
        "selector": "main, article, .content, body",
        "industries": ["General", "Manufacturing", "Energy", "Agriculture"],
    },
    {
        "name": "FTC - Consumer Protection Rules",
        "url": "https://www.ftc.gov/legal-library/browse/rules",
        "category": "Legal",
        "selector": "main, article, .content, body",
        "industries": ["General", "Retail", "Technology", "Finance"],
    },
    {
        "name": "HHS - HIPAA Privacy Rule",
        "url": "https://www.hhs.gov/hipaa/for-professionals/privacy/index.html",
        "category": "Data Privacy",
        "selector": "main, article, .content, body",
        "industries": ["Pharma/Healthcare", "General"],
    },
    {
        "name": "DOL - Employment Laws",
        "url": "https://www.dol.gov/general/aboutdol/majorlaws",
        "category": "Employment",
        "selector": "main, article, .content, body",
        "industries": ["General", "Manufacturing", "Retail", "Technology", "Education", "Construction"],
    },
    {
        "name": "IRS - Small Business & Self-Employed",
        "url": "https://www.irs.gov/businesses/small-businesses-self-employed",
        "category": "Financial",
        "selector": "main, article, .content, body",
        "industries": ["Finance", "General"],
    },
    {
        "name": "NIST - Cybersecurity Framework",
        "url": "https://www.nist.gov/cyberframework",
        "category": "IT Security",
        "selector": "main, article, .content, body",
        "industries": ["Technology", "Finance", "Pharma/Healthcare", "General"],
    },
    {
        "name": "eCFR - Code of Federal Regulations (Title 21)",
        "url": "https://www.ecfr.gov/current/title-21",
        "category": "Legal",
        "selector": "main, #content-body, .content, body",
        "industries": ["Pharma/Healthcare"],
    },
    {
        "name": "FDA - Regulatory Procedures (SOPs)",
        "url": "https://www.fda.gov/about-fda/regulatory-procedures-manual",
        "category": "Quality Control",
        "selector": "main, article, .content, #main-content, body",
        "industries": ["Pharma/Healthcare"],
    },
    {
        "name": "CFPB - Consumer Financial Protection",
        "url": "https://www.consumerfinance.gov/rules-policy/regulations/",
        "category": "Legal",
        "selector": "main, article, .content, body",
        "industries": ["Finance"],
    },
    {
        "name": "SEC - Small Business Compliance",
        "url": "https://www.sec.gov/smallbusiness",
        "category": "Financial",
        "selector": "main, #content, body",
        "industries": ["Finance"],
    },
    {
        "name": "NIST - Privacy Framework",
        "url": "https://www.nist.gov/privacy-framework",
        "category": "Data Privacy",
        "selector": "main, article, .content, body",
        "industries": ["Technology", "Finance", "Pharma/Healthcare", "General"],
    },
    {
        "name": "DOL - Workplace Posters & Compliance",
        "url": "https://www.dol.gov/general/topic/compliance",
        "category": "Employment",
        "selector": "main, article, .content, body",
        "industries": ["General", "Manufacturing", "Retail", "Construction"],
    },
    {
        "name": "CISA - Cybersecurity Best Practices",
        "url": "https://www.cisa.gov/topics/cyber-threats-and-advisories",
        "category": "IT Security",
        "selector": "main, article, .content, body",
        "industries": ["Technology", "Finance", "General"],
    },
    {
        "name": "EU GDPR - Official Journal (EUR-Lex)",
        "url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "category": "Data Privacy",
        "selector": "main, article, .content, body",
        "industries": ["Technology", "Finance", "Pharma/Healthcare", "General"],
    },
    {
        "name": "EDPB - GDPR Guidelines & Best Practices",
        "url": "https://edpb.europa.eu/our-work-tools/general-guidance/gdpr-guidelines-recommendations-best-practices_en",
        "category": "Data Privacy",
        "selector": "main, article, .content, body",
        "industries": ["Technology", "Finance", "Pharma/Healthcare", "General"],
    },
    {
        "name": "EU-OSHA - EU Health & Safety Legislation",
        "url": "https://osha.europa.eu/en/legislation",
        "category": "Health & Safety",
        "selector": "main, article, .content, body",
        "industries": ["General", "Manufacturing", "Construction"],
    },
    {
        "name": "ILO - International Labour Standards",
        "url": "https://www.ilo.org/global/standards/lang--en/index.htm",
        "category": "Employment",
        "selector": "main, article, .content, body",
        "industries": ["General", "Manufacturing", "Retail", "Construction"],
    },
    # Finance-specific sources
    {
        "name": "FDIC - Banking Regulations",
        "url": "https://www.fdic.gov/regulations/laws/rules",
        "category": "Financial",
        "selector": "main, article, .content, body",
        "industries": ["Finance"],
    },
    {
        "name": "FINRA - Financial Industry Regulatory Authority",
        "url": "https://www.finra.org/rules-guidance",
        "category": "Financial",
        "selector": "main, article, .content, body",
        "industries": ["Finance"],
    },
    {
        "name": "OCC - Office of the Comptroller of the Currency",
        "url": "https://www.occ.gov/topics/supervision-and-examination/index-supervision-and-examination.html",
        "category": "Financial",
        "selector": "main, article, .content, body",
        "industries": ["Finance"],
    },
    # Pharma/Healthcare-specific sources
    {
        "name": "FDA - Food and Drug Administration Regulations",
        "url": "https://www.fda.gov/regulatory-information",
        "category": "Quality Control",
        "selector": "main, article, .content, body",
        "industries": ["Pharma/Healthcare"],
    },
    {
        "name": "CMS - Centers for Medicare & Medicaid Services",
        "url": "https://www.cms.gov/regulations-and-guidance",
        "category": "Legal",
        "selector": "main, article, .content, body",
        "industries": ["Pharma/Healthcare"],
    },
    {
        "name": "eCFR - Title 21 Food and Drugs",
        "url": "https://www.ecfr.gov/current/title-21/chapter-I",
        "category": "Legal",
        "selector": "main, #content-body, .content, body",
        "industries": ["Pharma/Healthcare"],
    },
    # Education-specific sources
    {
        "name": "FERPA - Family Educational Rights and Privacy Act",
        "url": "https://www2.ed.gov/policy/gen/guid/fpco/ferpa/index.html",
        "category": "Data Privacy",
        "selector": "main, article, .content, body",
        "industries": ["Education"],
    },
    {
        "name": "US Department of Education - Regulations",
        "url": "https://www2.ed.gov/policy/landing.jhtml",
        "category": "Legal",
        "selector": "main, article, .content, body",
        "industries": ["Education"],
    },
    # Agriculture-specific sources
    {
        "name": "USDA - United States Department of Agriculture",
        "url": "https://www.usda.gov/regulations",
        "category": "Legal",
        "selector": "main, article, .content, body",
        "industries": ["Agriculture"],
    },
    {
        "name": "FDA - Food Safety Regulations",
        "url": "https://www.fda.gov/food/food-safety-modernization-act-fsma",
        "category": "Quality Control",
        "selector": "main, article, .content, body",
        "industries": ["Agriculture"],
    },
    # Manufacturing-specific sources
    {
        "name": "ISO - International Organization for Standardization",
        "url": "https://www.iso.org/standards.html",
        "category": "Quality Control",
        "selector": "main, article, .content, body",
        "industries": ["Manufacturing"],
    },
    # Energy-specific sources
    {
        "name": "DOE - Department of Energy Regulations",
        "url": "https://www.energy.gov/regulations",
        "category": "Legal",
        "selector": "main, article, .content, body",
        "industries": ["Energy"],
    },
    {
        "name": "FERC - Federal Energy Regulatory Commission",
        "url": "https://www.ferc.gov/regulations",
        "category": "Legal",
        "selector": "main, article, .content, body",
        "industries": ["Energy"],
    },
    # Technology-specific sources
    {
        "name": "NIST - Information Technology Standards",
        "url": "https://www.nist.gov/itl",
        "category": "IT Security",
        "selector": "main, article, .content, body",
        "industries": ["Technology"],
    },
    # Construction-specific sources
    {
        "name": "OSHA - Construction Industry Standards",
        "url": "https://www.osha.gov/construction",
        "category": "Health & Safety",
        "selector": "main, article, .content, body",
        "industries": ["Construction"],
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_regulation_sources():
    return DEFAULT_SOURCES.copy()


def get_sources_by_industry(industry):
    """
    Get regulation sources filtered by industry.
    Returns sources that match the industry, plus always include "General" sources.
    """
    if not industry or industry == "General":
        # Return all sources if General
        return DEFAULT_SOURCES.copy()
    
    # Normalize industry name
    industry_normalized = industry.strip()
    
    # Get sources that match the industry
    matching_sources = []
    for source in DEFAULT_SOURCES:
        source_industries = source.get("industries", ["General"])
        if industry_normalized in source_industries or "General" in source_industries:
            matching_sources.append(source)
    
    # If no specific matches found, return General sources
    if not matching_sources:
        matching_sources = [s for s in DEFAULT_SOURCES if "General" in s.get("industries", ["General"])]
    
    return matching_sources


def scrape_regulations(sources=None, progress_callback=None, industry=None):
    """
    Scrape regulations from sources.
    If industry is provided, filter sources by industry.
    """
    if sources is None:
        if industry:
            sources = get_sources_by_industry(industry)
        else:
            sources = DEFAULT_SOURCES

    all_regulations = []
    for i, source in enumerate(sources):
        if progress_callback:
            progress_callback(i, len(sources), source["name"])
        try:
            regs = _scrape_single_source(source)
            all_regulations.extend(regs)
        except Exception as e:
            all_regulations.append({
                "source_name": source["name"],
                "source_url": source["url"],
                "category": source["category"],
                "title": f"[Scraping Error] {source['name']}",
                "text": f"Could not retrieve regulations from this source. Using cached/fallback data. Error: {str(e)}",
                "status": "error",
            })
        time.sleep(0.5)

    if not all_regulations:
        all_regulations = _get_fallback_regulations()

    _cache_regulations(all_regulations)
    return all_regulations


def _scrape_single_source(source):
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception:
        cached = _load_cached_regulations()
        source_cached = [r for r in cached if r.get("source_url") == source["url"]]
        if source_cached:
            return source_cached
        return _get_fallback_for_category(source)

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    content = None
    for sel in source["selector"].split(","):
        sel = sel.strip()
        content = soup.select_one(sel)
        if content:
            break
    if not content:
        content = soup.body or soup

    text = content.get_text(separator="\n", strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)

    regulations = _split_into_regulations(text, source)
    return regulations


def _split_into_regulations(text, source):
    if len(text) < 100:
        return _get_fallback_for_category(source)

    chunks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""
    current_title = source["name"]

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) < 200 and (para.isupper() or re.match(r'^[\d.]+\s+[A-Z]', para) or re.match(r'^(?:Section|Title|Part|Chapter)\s', para, re.I)):
            if current_chunk and len(current_chunk) > 50:
                chunks.append({
                    "source_name": source["name"],
                    "source_url": source["url"],
                    "category": source["category"],
                    "title": current_title[:150],
                    "text": current_chunk.strip()[:2000],
                    "status": "active",
                })
            current_title = para[:150]
            current_chunk = ""
        else:
            current_chunk += para + "\n"

    if current_chunk and len(current_chunk) > 50:
        chunks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "category": source["category"],
            "title": current_title[:150],
            "text": current_chunk.strip()[:2000],
            "status": "active",
        })

    if not chunks:
        chunks.append({
            "source_name": source["name"],
            "source_url": source["url"],
            "category": source["category"],
            "title": source["name"],
            "text": text[:2000],
            "status": "active",
        })

    return chunks[:30]


def _get_fallback_for_category(source):
    fallbacks = _get_fallback_regulations()
    return [r for r in fallbacks if r["category"] == source["category"]] or [fallbacks[0]]


def _get_fallback_regulations():
    return [
        {
            "source_name": "OSHA - Workplace Safety Standards",
            "source_url": "https://www.osha.gov/laws-regs",
            "category": "Health & Safety",
            "title": "General Duty Clause - Section 5(a)(1)",
            "text": "Each employer shall furnish to each of his employees employment and a place of employment which are free from recognized hazards that are causing or are likely to cause death or serious physical harm to his employees. Employers must comply with occupational safety and health standards promulgated under the OSH Act. Employers must provide personal protective equipment (PPE) at no cost to employees. Training must be provided in a language and vocabulary workers can understand.",
            "status": "active",
        },
        {
            "source_name": "EPA - Environmental Regulations",
            "source_url": "https://www.epa.gov/regulatory-information",
            "category": "Environmental",
            "title": "Clean Air Act & RCRA Requirements",
            "text": "Businesses must comply with the Clean Air Act standards for emissions. Resource Conservation and Recovery Act (RCRA) requires proper handling, storage, and disposal of hazardous waste. Facilities must maintain records of waste disposal and report to EPA. Environmental impact assessments are required for new operations. Spill prevention and countermeasure plans must be maintained.",
            "status": "active",
        },
        {
            "source_name": "HHS - HIPAA Privacy Rule",
            "source_url": "https://www.hhs.gov/hipaa",
            "category": "Data Privacy",
            "title": "HIPAA Privacy & Security Rules",
            "text": "Protected Health Information (PHI) must be safeguarded with administrative, physical, and technical safeguards. Covered entities must provide Notice of Privacy Practices. Minimum necessary standard applies to all uses and disclosures. Business Associate Agreements required for third parties handling PHI. Breach notification required within 60 days of discovery. Individuals have right to access and amend their records.",
            "status": "active",
        },
        {
            "source_name": "DOL - Employment Laws",
            "source_url": "https://www.dol.gov/general/aboutdol/majorlaws",
            "category": "Employment",
            "title": "Fair Labor Standards Act (FLSA) & FMLA",
            "text": "The Fair Labor Standards Act establishes minimum wage ($7.25/hour federal), overtime pay (1.5x for hours over 40/week), recordkeeping, and child labor standards. The Family and Medical Leave Act provides eligible employees up to 12 weeks of unpaid, job-protected leave per year. Anti-discrimination laws prohibit employment decisions based on race, color, religion, sex, national origin, age, disability, or genetic information.",
            "status": "active",
        },
        {
            "source_name": "IRS - Tax Compliance",
            "source_url": "https://www.irs.gov/businesses",
            "category": "Financial",
            "title": "Business Tax Obligations",
            "text": "All businesses must obtain an Employer Identification Number (EIN). Quarterly estimated tax payments required. Employment taxes must be deposited on time. Form 1099 reporting for payments over $600 to independent contractors. Record retention requirement of 3-7 years depending on document type. Proper classification of workers as employees vs independent contractors.",
            "status": "active",
        },
        {
            "source_name": "FTC - Consumer Protection",
            "source_url": "https://www.ftc.gov/legal-library/browse/rules",
            "category": "Legal",
            "title": "FTC Act & Consumer Protection Rules",
            "text": "Section 5 of the FTC Act prohibits unfair or deceptive acts or practices in commerce. Truth in advertising standards require substantiation of claims. CAN-SPAM Act requires commercial emails include opt-out mechanisms. Children's Online Privacy Protection Act (COPPA) protects children under 13. Clear and conspicuous disclosure of material terms required in all consumer transactions.",
            "status": "active",
        },
        {
            "source_name": "NIST - Cybersecurity Framework",
            "source_url": "https://www.nist.gov/cyberframework",
            "category": "IT Security",
            "title": "NIST Cybersecurity Framework Core Functions",
            "text": "The framework organizes cybersecurity activities into five core functions: Identify (asset management, risk assessment), Protect (access control, data security, training), Detect (anomalies, continuous monitoring), Respond (response planning, communications, mitigation), Recover (recovery planning, improvements). Organizations should implement multi-factor authentication, encryption at rest and in transit, regular security assessments, and incident response plans.",
            "status": "active",
        },
        {
            "source_name": "eCFR - Code of Federal Regulations",
            "source_url": "https://www.ecfr.gov",
            "category": "Legal",
            "title": "CFR General Requirements",
            "text": "The Code of Federal Regulations (CFR) is the codification of the general and permanent rules published in the Federal Register by the executive departments and agencies of the Federal Government. Title 21 covers Food and Drugs; Title 29 Labor; Title 40 Protection of Environment. Organizations must comply with applicable titles and maintain current awareness of amendments.",
            "status": "active",
        },
        {
            "source_name": "FDA - Regulatory Procedures",
            "source_url": "https://www.fda.gov/about-fda/regulatory-procedures-manual",
            "category": "Quality Control",
            "title": "FDA SOP and Documentation Standards",
            "text": "Standard Operating Procedures (SOPs) must be written, approved, and maintained. Changes require documented review and approval. Training on SOPs must be documented. Records must be retained per regulatory requirements. Quality systems should include management review, corrective action, and document control.",
            "status": "active",
        },
        {
            "source_name": "CFPB - Consumer Financial Protection",
            "source_url": "https://www.consumerfinance.gov/rules-policy/regulations/",
            "category": "Legal",
            "title": "Consumer Financial Protection Regulations",
            "text": "Consumer financial products and services must comply with disclosure requirements, fair lending, debt collection rules, and consumer complaint procedures. Recordkeeping and compliance management systems are required. Unfair, deceptive, or abusive acts or practices (UDAAP) are prohibited.",
            "status": "active",
        },
        {
            "source_name": "SEC - Small Business",
            "source_url": "https://www.sec.gov/smallbusiness",
            "category": "Financial",
            "title": "SEC Disclosure and Reporting",
            "text": "Small businesses raising capital or subject to SEC rules must maintain accurate books and records, file required reports, and provide disclosures to investors. Internal controls and compliance programs should be documented.",
            "status": "active",
        },
        {
            "source_name": "CISA - Cybersecurity",
            "source_url": "https://www.cisa.gov",
            "category": "IT Security",
            "title": "Cybersecurity Best Practices",
            "text": "Implement defense in depth, patch management, access controls, and incident response plans. Monitor advisories for threats. Report significant cyber incidents as required. Protect critical systems and data with encryption and segmentation.",
            "status": "active",
        },
    ]


def _cache_regulations(regulations):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(regulations, f, indent=2)
    except Exception:
        pass


def _load_cached_regulations():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []
