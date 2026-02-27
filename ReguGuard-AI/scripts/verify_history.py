import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.history_manager import HistoryManager

def test_history_manager():
    print("Starting HistoryManager verification...")
    
    # Use a temporary directory for testing
    test_dir = "data/history_test"
    mgr = HistoryManager(data_dir=test_dir)
    
    # 1. Test Saving
    session_data = {
        "filename": "test_doc.pdf",
        "industry": "Finance",
        "score": 85,
        "risk_level": "Low",
        "findings": [{"area": "Data Privacy", "status": "compliant"}],
        "approved_changes": {"Data Privacy_0": {"suggestion": "Keep it up"}},
        "rejected_changes": {},
        "executive_summary": "Test summary",
        "compliance_debt_estimate": 1000,
        "citations": [{"source": "GDPR", "url": "https://gdpr.eu"}]
    }
    
    session_id = mgr.save_session(session_data)
    print(f"Session saved with ID: {session_id}")
    
    # 2. Test Listing
    sessions = mgr.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["filename"] == "test_doc.pdf"
    assert sessions[0]["score"] == 85
    print("List sessions verified.")
    
    # 3. Test Retrieval
    detail = mgr.get_session_detail(session_id)
    assert detail is not None
    assert detail["executive_summary"] == "Test summary"
    assert detail["findings"][0]["area"] == "Data Privacy"
    print("Get session detail verified.")
    
    # 4. Test Deletion
    mgr.delete_session(session_id)
    sessions = mgr.list_sessions()
    assert len(sessions) == 0
    assert not os.path.exists(os.path.join(test_dir, "sessions", f"{session_id}.json"))
    print("Delete session verified.")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    print("Cleanup completed.")
    print("HistoryManager verification SUCCESSFUL!")

if __name__ == "__main__":
    try:
        test_history_manager()
    except Exception as e:
        print(f"Verification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
