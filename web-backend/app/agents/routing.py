# Agent routing decisions
def route_next_step(state):
    tier = state.get("triage_tier", 1)
    if tier == 3:
        return "human_review"
    return "reply_and_act"
