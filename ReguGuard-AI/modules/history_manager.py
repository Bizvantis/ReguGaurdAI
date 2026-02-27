"""
Conversation history manager for ReguGuard AI.
Stores and retrieves past compliance analyses, similar to ChatGPT's conversation history.
"""
import os
import json
from datetime import datetime
from typing import List, Dict, Optional


HISTORY_DIR = "data"
HISTORY_FILE = os.path.join(HISTORY_DIR, "analysis_history.jsonl")


def save_analysis_history(
    document_name: str,
    domain: Optional[str],
    compliance_score: int,
    risk_level: str,
    analysis_method: str,
    num_findings: int,
    sop_text_preview: str = "",
    full_analysis: Optional[Dict] = None,
    sop_text: Optional[str] = None,
    regulations: Optional[List] = None,
) -> str:
    """
    Save a completed analysis to history with full analysis data.
    
    Returns:
        analysis_id: Unique identifier for this analysis
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    
    analysis_id = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(document_name) % 10000}"
    
    record = {
        "analysis_id": analysis_id,
        "timestamp": datetime.now().isoformat(),
        "document_name": document_name,
        "domain": domain or "General",
        "compliance_score": compliance_score,
        "risk_level": risk_level,
        "analysis_method": analysis_method,
        "num_findings": num_findings,
        "sop_text_preview": sop_text_preview[:200] if sop_text_preview else "",
        # Store full analysis data for viewing later (always save if provided)
        "full_analysis": full_analysis if full_analysis else None,
        "sop_text": sop_text[:5000] if sop_text else None,  # Store first 5000 chars
        "regulations_count": len(regulations) if regulations else 0,
    }
    
    # Ensure full_analysis is saved (critical for detailed view)
    if not full_analysis:
        import warnings
        warnings.warn(f"Warning: Saving history without full_analysis for {document_name}")
    
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Warning: Could not save history: {e}")
    
    return analysis_id


def load_analysis_history(limit: int = 50) -> List[Dict]:
    """
    Load recent analysis history.
    
    Returns:
        List of analysis records, most recent first
    """
    if not os.path.exists(HISTORY_FILE):
        return []
    
    records = []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception as e:
        print(f"Warning: Could not load history: {e}")
        return []
    
    # Sort by timestamp descending (most recent first)
    records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return records[:limit]


def get_analysis_by_id(analysis_id: str) -> Optional[Dict]:
    """Retrieve a specific analysis by ID."""
    records = load_analysis_history(limit=1000)
    for record in records:
        if record.get("analysis_id") == analysis_id:
            return record
    return None


def clear_history():
    """Clear all analysis history."""
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
    except Exception as e:
        print(f"Warning: Could not clear history: {e}")


def delete_analysis(analysis_id: str) -> bool:
    """
    Delete a specific analysis by ID from history.
    Returns True if successful, False otherwise.
    """
    try:
        records = load_analysis_history(limit=1000)
        remaining = [r for r in records if r.get("analysis_id") != analysis_id]
        
        # Rewrite history file without the deleted record
        os.makedirs(HISTORY_DIR, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for record in remaining:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"Warning: Could not delete analysis: {e}")
        return False
