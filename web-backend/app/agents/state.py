from typing import TypedDict, List, Optional, Any

class CaseAgentState(TypedDict):
    case_id: str
    user_id: str
    messages: List[dict]
    intake_data: Optional[dict]
    triage_tier: int  # 1: Informational, 2: Suspected Fraud, 3: Distress
    verification_results: Optional[dict]
    evidence_gathered: List[dict]
    next_action: Optional[str]
