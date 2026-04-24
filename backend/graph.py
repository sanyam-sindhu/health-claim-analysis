from typing import TypedDict, Optional, List, Dict, Any
from langgraph.graph import StateGraph, END

from nodes import (
    validate_documents_node,
    extract_documents_node,
    cross_validate_node,
    check_policy_node,
    check_fraud_node,
    make_decision_node,
)


class ClaimState(TypedDict):
    claim_id: str
    member_id: str
    policy_id: str
    claim_category: str
    treatment_date: str
    claimed_amount: float
    hospital_name: Optional[str]
    ytd_claims_amount: float
    claims_history: List[Dict[str, Any]]
    documents: List[Dict[str, Any]]
    simulate_component_failure: bool
    member: Optional[Dict[str, Any]]
    doc_validation: Optional[Dict[str, Any]]
    extracted_docs: Optional[List[Dict[str, Any]]]
    cross_validation: Optional[Dict[str, Any]]
    policy_check: Optional[Dict[str, Any]]
    fraud_check: Optional[Dict[str, Any]]
    decision: Optional[str]
    approved_amount: Optional[float]
    confidence_score: Optional[float]
    rejection_reasons: Optional[List[str]]
    decision_notes: Optional[str]
    line_item_decisions: Optional[List[Dict[str, Any]]]
    should_stop: bool
    stop_message: Optional[str]
    component_failures: List[str]
    trace: List[Dict[str, Any]]


def _route_after_doc_validation(state: ClaimState) -> str:
    return "end" if state.get("should_stop") else "extract_documents"


def _route_after_cross_validate(state: ClaimState) -> str:
    return "end" if state.get("should_stop") else "check_policy"


def create_graph():
    g = StateGraph(ClaimState)

    g.add_node("validate_documents", validate_documents_node)
    g.add_node("extract_documents", extract_documents_node)
    g.add_node("cross_validate", cross_validate_node)
    g.add_node("check_policy", check_policy_node)
    g.add_node("check_fraud", check_fraud_node)
    g.add_node("make_decision", make_decision_node)

    g.set_entry_point("validate_documents")
    g.add_conditional_edges("validate_documents", _route_after_doc_validation,
                            {"end": END, "extract_documents": "extract_documents"})
    g.add_edge("extract_documents", "cross_validate")
    g.add_conditional_edges("cross_validate", _route_after_cross_validate,
                            {"end": END, "check_policy": "check_policy"})
    g.add_edge("check_policy", "check_fraud")
    g.add_edge("check_fraud", "make_decision")
    g.add_edge("make_decision", END)

    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = create_graph()
    return _graph


async def run_claim_pipeline(initial_state: dict) -> ClaimState:
    graph = get_graph()
    result = await graph.ainvoke(initial_state)
    return result
