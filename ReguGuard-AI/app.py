import streamlit as st
import os
import json
import time
from datetime import datetime

from modules.sop_parser import extract_text_from_file, parse_sop_into_clauses
from modules.regulation_scraper import scrape_regulations, get_regulation_sources
from modules.rag_engine import RAGEngine
from modules.compliance_analyzer import (
    analyze_clause_compliance,
    calculate_overall_compliance,
    get_grok_client,
)

st.set_page_config(
    page_title="ReguGuard AI - Compliance Manager",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
        text-align: center;
    }
    .main-header h1 {
        color: white;
        font-size: 2.2rem;
        margin-bottom: 0.3rem;
    }
    .main-header p {
        color: #a8d8ea;
        font-size: 1rem;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1.2rem;
        text-align: center;
        border: 1px solid #e0e0e0;
    }
    .metric-card h3 {
        margin: 0;
        font-size: 2rem;
    }
    .metric-card p {
        margin: 0;
        color: #666;
        font-size: 0.85rem;
    }
    .status-compliant {
        background-color: #d4edda;
        color: #155724;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        display: inline-block;
    }
    .status-partial {
        background-color: #fff3cd;
        color: #856404;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        display: inline-block;
    }
    .status-non-compliant {
        background-color: #f8d7da;
        color: #721c24;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        display: inline-block;
    }
    .status-outdated {
        background-color: #e2e3e5;
        color: #383d41;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        display: inline-block;
    }
    .risk-high {
        color: #dc3545;
        font-weight: bold;
    }
    .risk-medium {
        color: #ffc107;
        font-weight: bold;
    }
    .risk-low {
        color: #28a745;
        font-weight: bold;
    }
    .citation-box {
        background: #f0f4f8;
        border-left: 4px solid #0f3460;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.85rem;
    }
    .suggestion-box {
        background: #e8f5e9;
        border-left: 4px solid #4caf50;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 6px 6px 0;
    }
    .section-divider {
        border-top: 2px solid #e0e0e0;
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    defaults = {
        "sop_text": None,
        "clauses": [],
        "regulations": [],
        "rag_engine": None,
        "matches": {},
        "analysis_results": [],
        "overall_compliance": None,
        "approved_changes": {},
        "analysis_complete": False,
        "scraping_complete": False,
        "current_step": "upload",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()


def render_header():
    st.markdown("""
    <div class="main-header">
        <h1>ReguGuard AI</h1>
        <p>Autonomous Compliance Manager for SMEs | Agentic Regulatory Synchronization</p>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar():
    with st.sidebar:
        st.markdown("### Navigation")
        st.info("ReguGuard is running in local analysis mode using web-scraped regulations.")

        st.markdown("---")
        st.markdown("### How It Works")
        st.markdown("""
        1. **Upload** your SOP document
        2. **Extract** policy clauses automatically
        3. **Scrape** latest government regulations
        4. **Analyze** compliance using AI + RAG
        5. **Review** results and approve changes
        """)

        st.markdown("---")
        st.markdown("### Regulation Sources")
        sources = get_regulation_sources()
        for src in sources:
            st.markdown(f"- [{src['name']}]({src['url']})")

        st.markdown("---")
        st.markdown("### Daily Monitoring")
        st.info("The system can periodically re-scrape regulations and re-analyze your SOP to detect new compliance gaps.")
        if st.button("Run Monitoring Check Now", use_container_width=True):
            st.session_state["current_step"] = "scrape"
            st.session_state["scraping_complete"] = False
            st.session_state["analysis_complete"] = False
            st.rerun()


def status_badge(status):
    badges = {
        "compliant": '<span class="status-compliant">Compliant</span>',
        "partially_compliant": '<span class="status-partial">Partially Compliant</span>',
        "non_compliant": '<span class="status-non-compliant">Non-Compliant</span>',
        "outdated": '<span class="status-outdated">Outdated</span>',
    }
    return badges.get(status, status)


def risk_badge(risk):
    badges = {
        "High": '<span class="risk-high">HIGH</span>',
        "Medium": '<span class="risk-medium">MEDIUM</span>',
        "Low": '<span class="risk-low">LOW</span>',
    }
    return badges.get(risk, risk)


def render_upload_section():
    st.markdown("## Step 1: Upload SOP Document")
    st.markdown("Upload your company's Standard Operating Procedure document for compliance analysis.")

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_file = st.file_uploader(
            "Choose a file (PDF, DOCX, or TXT)",
            type=["pdf", "docx", "txt"],
            key="sop_uploader",
        )

        if uploaded_file is not None:
            st.success(f"File uploaded: **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")

            if st.button("Extract & Parse SOP", type="primary", key="parse_btn"):
                with st.spinner("Extracting text from document..."):
                    try:
                        raw_text = extract_text_from_file(uploaded_file)
                        if not raw_text or not raw_text.strip():
                            st.error("Could not extract text from the uploaded file. Please try a different file.")
                            return

                        st.session_state["sop_text"] = raw_text
                        clauses = parse_sop_into_clauses(raw_text)
                        st.session_state["clauses"] = clauses
                        st.session_state["current_step"] = "review_clauses"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error processing file: {str(e)}")

    with col2:
        st.markdown("#### Supported Formats")
        st.markdown("- **PDF** - Portable Document Format")
        st.markdown("- **DOCX** - Microsoft Word")
        st.markdown("- **TXT** - Plain Text")
        st.markdown("---")
        st.markdown("#### Sample SOP")
        if st.button("Use Sample SOP", key="sample_btn"):
            sample_text = _get_sample_sop()
            st.session_state["sop_text"] = sample_text
            clauses = parse_sop_into_clauses(sample_text)
            st.session_state["clauses"] = clauses
            st.session_state["current_step"] = "review_clauses"
            st.rerun()


def render_clause_review():
    st.markdown("## Step 2: Extracted Clauses")
    clauses = st.session_state["clauses"]
    st.info(f"Found **{len(clauses)}** policy clauses in your SOP document.")

    for clause in clauses:
        with st.expander(f"{clause['id']} | {clause['title'][:80]} | Category: {clause['category']}", expanded=False):
            st.markdown(f"**Category:** {clause['category']}")
            st.text_area("Clause Text", clause["text"], height=120, key=f"clause_{clause['id']}", disabled=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back to Upload", key="back_upload"):
            st.session_state["current_step"] = "upload"
            st.rerun()
    with col2:
        if st.button("Proceed to Regulation Scraping", type="primary", key="proceed_scrape"):
            st.session_state["current_step"] = "scrape"
            st.rerun()


def render_scraping():
    st.markdown("## Step 3: Scraping Latest Regulations")
    st.markdown("Fetching current regulations from government and regulatory websites...")

    if not st.session_state["scraping_complete"]:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_cb(current, total, name):
            progress_bar.progress((current + 1) / total)
            status_text.markdown(f"Scraping: **{name}** ({current + 1}/{total})")

        with st.spinner("Scraping regulations..."):
            regulations = scrape_regulations(progress_callback=progress_cb)
            st.session_state["regulations"] = regulations
            st.session_state["scraping_complete"] = True

            rag = RAGEngine()
            rag.index_regulations(regulations)
            st.session_state["rag_engine"] = rag

        progress_bar.progress(1.0)
        status_text.markdown("**Scraping complete!**")
        st.rerun()
    else:
        regulations = st.session_state["regulations"]
        st.success(f"Loaded **{len(regulations)}** regulation entries from **{len(set(r['source_name'] for r in regulations))}** sources.")

        cats = {}
        for r in regulations:
            cat = r.get("category", "Unknown")
            cats[cat] = cats.get(cat, 0) + 1

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Regulations", len(regulations))
        with col2:
            st.metric("Categories", len(cats))
        with col3:
            st.metric("Sources", len(set(r["source_name"] for r in regulations)))

        st.markdown("#### Regulations by Category")
        for cat, count in sorted(cats.items()):
            st.markdown(f"- **{cat}**: {count} entries")

        if st.button("Proceed to Compliance Analysis", type="primary", key="proceed_analysis"):
            st.session_state["current_step"] = "analyze"
            st.rerun()


def render_analysis():
    st.markdown("## Step 4: Compliance Analysis")

    clauses = st.session_state["clauses"]
    rag = st.session_state["rag_engine"]

    if not st.session_state["analysis_complete"]:
        if not clauses:
            st.error("No clauses found. Please go back and upload an SOP document.")
            return
        if rag is None:
            st.error("Regulations not loaded. Please go back and scrape regulations first.")
            return

        st.markdown("Running RAG matching and compliance analysis...")
        progress_bar = st.progress(0)
        status_text = st.empty()

        matches = rag.match_all_clauses(clauses)
        st.session_state["matches"] = matches

        results = []
        for i, clause in enumerate(clauses):
            progress_bar.progress((i + 1) / len(clauses))
            status_text.markdown(f"Analyzing: **{clause['id']}** - {clause['title'][:60]}...")

            matched_regs = matches.get(clause["id"], [])
            result = analyze_clause_compliance(clause, matched_regs, use_ai=False)
            results.append(result)

        st.session_state["analysis_results"] = results
        st.session_state["overall_compliance"] = calculate_overall_compliance(results)
        st.session_state["analysis_complete"] = True
        st.session_state["current_step"] = "results"
        progress_bar.progress(1.0)
        status_text.markdown("**Analysis complete!**")
        st.rerun()
    else:
        st.session_state["current_step"] = "results"
        st.rerun()


def render_results():
    st.markdown("## Compliance Analysis Results")

    overall = st.session_state["overall_compliance"]
    results = st.session_state["analysis_results"]
    clauses = st.session_state["clauses"]

    if not overall or not results:
        st.warning("No analysis results available. Please run the analysis first.")
        if st.button("Go to Upload", key="go_upload"):
            st.session_state["current_step"] = "upload"
            st.rerun()
        return

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        score = overall["score"]
        color = "#28a745" if score >= 70 else "#ffc107" if score >= 40 else "#dc3545"
        st.markdown(f"""<div class="metric-card">
            <h3 style="color:{color}">{score}%</h3>
            <p>Compliance Score</p>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="metric-card">
            <h3 style="color:#155724">{overall['compliant']}</h3>
            <p>Compliant</p>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="metric-card">
            <h3 style="color:#856404">{overall['partial']}</h3>
            <p>Partially Compliant</p>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""<div class="metric-card">
            <h3 style="color:#721c24">{overall['non_compliant']}</h3>
            <p>Non-Compliant</p>
        </div>""", unsafe_allow_html=True)
    with col5:
        st.markdown(f"""<div class="metric-card">
            <h3 style="color:#383d41">{overall['outdated']}</h3>
            <p>Outdated</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    debt_col1, debt_col2, debt_col3 = st.columns(3)
    with debt_col1:
        debt = overall.get("compliance_debt", 0)
        st.metric("Estimated Compliance Debt", f"${debt:,.0f}")
    with debt_col2:
        st.metric("High Risk Clauses", overall.get("high_risk", 0))
    with debt_col3:
        method = results[0].get("analysis_method", "Rule-based") if results else "N/A"
        st.metric("Analysis Method", method.split("(")[0].strip())

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    st.markdown("### Detailed Clause Analysis")

    filter_status = st.selectbox(
        "Filter by status",
        ["All", "Compliant", "Partially Compliant", "Non-Compliant", "Outdated"],
        key="filter_status",
    )

    status_map = {
        "Compliant": "compliant",
        "Partially Compliant": "partially_compliant",
        "Non-Compliant": "non_compliant",
        "Outdated": "outdated",
    }

    clause_map = {c["id"]: c for c in clauses}

    for result in results:
        if filter_status != "All" and result.get("compliance_status") != status_map.get(filter_status):
            continue

        clause_id = result.get("clause_id", "Unknown")
        clause = clause_map.get(clause_id, {})
        title = clause.get("title", "Unknown")[:80]
        status = result.get("compliance_status", "unknown")
        risk = result.get("risk_level", "Unknown")
        score = result.get("compliance_score", 0)

        with st.expander(f"{clause_id} | {title} | Score: {score}%", expanded=(status != "compliant")):
            info_col1, info_col2, info_col3 = st.columns(3)
            with info_col1:
                st.markdown(f"**Status:** {status_badge(status)}", unsafe_allow_html=True)
            with info_col2:
                st.markdown(f"**Risk Level:** {risk_badge(risk)}", unsafe_allow_html=True)
            with info_col3:
                st.markdown(f"**Score:** {score}%")

            st.markdown(f"**Summary:** {result.get('summary', 'N/A')}")
            st.markdown(f"**Reasoning:** {result.get('reasoning', 'N/A')}")

            missing = result.get("missing_elements", [])
            if missing:
                st.markdown("**Missing Regulatory Elements:**")
                for m in missing:
                    st.markdown(f"- {m}")

            applicable = result.get("applicable_regulations", [])
            if applicable:
                st.markdown("**Applicable Regulations:**")
                for reg in applicable:
                    st.markdown(f"- {reg}")

            citations = result.get("citations", [])
            if citations:
                st.markdown("**Citations & Sources:**")
                for cit in citations:
                    st.markdown(f"""<div class="citation-box">
                        <strong>{cit.get('source', 'Unknown')}</strong> - {cit.get('title', 'N/A')}<br>
                        <a href="{cit.get('url', '#')}" target="_blank">{cit.get('url', 'N/A')}</a>
                        <br><em>Relevance: {cit.get('relevance_score', 0):.2%}</em>
                    </div>""", unsafe_allow_html=True)

            suggestion = result.get("suggested_correction", "")
            if suggestion and "no correction needed" not in suggestion.lower():
                st.markdown("**Suggested Correction:**")
                st.markdown(f"""<div class="suggestion-box">{suggestion}</div>""", unsafe_allow_html=True)

                approve_key = f"approve_{clause_id}"
                if st.button(f"Approve Change for {clause_id}", key=approve_key):
                    st.session_state["approved_changes"][clause_id] = {
                        "suggestion": suggestion,
                        "approved_at": datetime.now().isoformat(),
                        "status": status,
                    }
                    st.success(f"Change approved for {clause_id}! This will be tracked for implementation.")

                if clause_id in st.session_state.get("approved_changes", {}):
                    st.info(f"Change approved on {st.session_state['approved_changes'][clause_id]['approved_at']}")

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    approved = st.session_state.get("approved_changes", {})
    if approved:
        st.markdown("### Approved Changes Summary")
        st.info(f"**{len(approved)}** changes have been approved for implementation.")
        for cid, change in approved.items():
            st.markdown(f"- **{cid}**: Approved at {change['approved_at']}")

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        report = _generate_report(overall, results, clauses)
        st.download_button(
            "Download Full Report (JSON)",
            data=json.dumps(report, indent=2),
            file_name=f"reguguard_compliance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )
    with col2:
        if st.button("Re-run Analysis", key="rerun_analysis"):
            st.session_state["analysis_complete"] = False
            st.session_state["current_step"] = "analyze"
            st.rerun()
    with col3:
        if st.button("Start New Analysis", key="new_analysis"):
            for key in ["sop_text", "clauses", "regulations", "rag_engine", "matches",
                        "analysis_results", "overall_compliance", "approved_changes",
                        "analysis_complete", "scraping_complete"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state["current_step"] = "upload"
            st.rerun()


def _generate_report(overall, results, clauses):
    return {
        "report_title": "ReguGuard AI Compliance Report",
        "generated_at": datetime.now().isoformat(),
        "overall_compliance": overall,
        "clause_analyses": results,
        "total_clauses_analyzed": len(results),
        "approved_changes": st.session_state.get("approved_changes", {}),
    }


def _get_sample_sop():
    return """STANDARD OPERATING PROCEDURE
Company: Acme Corp
Version: 2.1
Last Updated: January 2025

Section 1: Purpose and Scope
1.1 Purpose
This Standard Operating Procedure establishes the policies and procedures for Acme Corp operations, ensuring compliance with applicable federal, state, and local regulations. This document covers all departments and operational areas.

1.2 Scope
This SOP applies to all employees, contractors, and third-party vendors who perform work on behalf of Acme Corp. It covers data handling, workplace safety, employment practices, financial operations, and environmental compliance.

Section 2: Data Privacy and Protection
2.1 Data Collection Policy
All personal data collected from customers and employees shall be processed in accordance with applicable privacy laws. Data collection must be limited to what is necessary for legitimate business purposes. Consent should be obtained where required.

2.2 Data Storage and Retention
Personal data shall be stored in encrypted databases with access controls. Data retention periods follow industry standards. Records may be kept for business purposes as determined by department heads.

2.3 Data Breach Response
In the event of a suspected data breach, the IT department should be notified. An investigation will be conducted when possible. Affected individuals may be notified if deemed appropriate by management.

Section 3: Workplace Health and Safety
3.1 General Safety Requirements
The company shall provide a safe working environment for all employees. Safety equipment is available upon request. Employees should report hazards to their supervisors.

3.2 Emergency Procedures
Emergency exits are marked throughout the facility. Fire drills are conducted periodically. First aid kits are maintained in common areas.

3.3 Incident Reporting
All workplace incidents should be reported to HR within a reasonable timeframe. Investigation of incidents will be conducted as resources permit.

Section 4: Employment Practices
4.1 Hiring and Onboarding
New employees undergo standard onboarding procedures. Background checks are performed for applicable positions. Equal opportunity principles guide our hiring decisions.

4.2 Compensation and Benefits
Employee compensation follows market standards. Overtime is paid as required by law. Benefits packages are reviewed annually.

4.3 Termination Procedures
Termination of employment follows standard HR procedures. Exit interviews are conducted when possible. Final paychecks are processed according to company policy.

Section 5: Financial Operations
5.1 Accounting Standards
Financial records are maintained using standard accounting practices. Quarterly reviews are performed by the finance team. Tax filings are prepared by the accounting department.

5.2 Expense Management
All business expenses require manager approval. Receipts must be submitted for reimbursement. Corporate credit card usage follows company guidelines.

Section 6: Environmental Compliance
6.1 Waste Management
The company follows applicable waste disposal regulations. Recycling programs are encouraged. Hazardous materials are handled by trained personnel.

6.2 Energy Conservation
Energy efficiency measures are implemented where practical. Equipment is maintained to optimize performance. Conservation initiatives are supported by management.

Section 7: IT Security
7.1 Access Control
System access is granted based on job requirements. Passwords must meet minimum complexity standards. Multi-factor authentication is recommended for sensitive systems.

7.2 Network Security
Firewalls and antivirus software are maintained on all company systems. Regular updates are applied to software and hardware. Security assessments are conducted periodically.

Section 8: Quality Assurance
8.1 Product Quality Standards
Products undergo quality inspection before delivery. Customer feedback is collected and reviewed. Continuous improvement processes are in place.

8.2 Document Control
This SOP is reviewed and updated periodically. Changes require management approval. Previous versions are maintained for reference.
"""


def main():
    try:
        render_header()
        render_sidebar()
        
        step = st.session_state.get("current_step", "upload")
        
        steps_display = {
            "upload": "1. Upload SOP",
            "review_clauses": "2. Review Clauses",
            "scrape": "3. Scrape Regulations",
            "analyze": "4. Analyze Compliance",
            "results": "5. View Results",
        }
        
        step_order = ["upload", "review_clauses", "scrape", "analyze", "results"]
        current_idx = step_order.index(step) if step in step_order else 0
        
        cols = st.columns(len(steps_display))
        for i, (s, label) in enumerate(steps_display.items()):
            with cols[i]:
                if i < current_idx:
                    st.markdown(f"~~{label}~~")
                elif i == current_idx:
                    st.markdown(f"**{label}**")
                else:
                    st.markdown(f"{label}")

        st.markdown("---")
        
        # Add actual content rendering here
        if step == "upload":
            render_upload_section()
        elif step == "review_clauses":
            render_clause_review()
        elif step == "scrape":
            render_scraping()
        elif step == "analyze":
            render_analysis()
        elif step == "results":
            render_results()
        else:
            st.error(f"Unknown step: {step}")
    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")
        st.exception(e)


if __name__ == "__main__":
    main()
