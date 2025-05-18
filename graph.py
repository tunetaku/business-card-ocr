# graph.py
from langgraph.graph import StateGraph
from langgraph.types import interrupt
from models import State
from db import exists, save_cards

def check_dup(state: State) -> State:
    new_, dup_ = [], []
    for c in state["cards"]:
        # デバッグ表示も安全に処理
        print(f"Card: {c.get('name', '[nameがありません]')}")
        # emailキーが存在しない場合は必ず新規カードとして扱う
        if "email" not in c or c["email"] is None:
            # emailがない場合は重複チェック不可能なので、新規として扱う
            new_.append(c)
        else:
            # emailがあれば重複チェック
            (dup_ if exists(c["email"]) else new_).append(c)
    state["new_cards"], state["dup_cards"] = new_, dup_
    state["need_human"] = bool(dup_) and not state.get("decisions")
    return state

def gate(state: State) -> State:
    # 重複ありかつ decisions 未確定 → 一時停止
    if state["need_human"]:
        interrupt(state)
    return state

def apply_decision(state: State) -> State:
    # 重複カードには必ずemailがあるはずだが、安全のためチェック
    overwrite = {}
    for c in state.get("dup_cards", []):
        if "email" in c and c["email"] and state["decisions"].get(c["email"]) == "overwrite":
            overwrite[c["email"]] = c
    
    # skip処理も安全に行う
    skip = set()
    for email in state.get("decisions", {}):
        if email and state["decisions"].get(email) == "skip":
            skip.add(email)
    
    # 最終的な保存カードを用意
    state["final_cards"] = state.get("new_cards", []) + list(overwrite.values())
    state["skipped"] = list(skip)
    return state

def save_node(state: State) -> State:
    save_cards(state["final_cards"])
    return state

def create_graph():
    sg = StateGraph(State)
    sg.add_node("check", check_dup)
    sg.add_node("gate", gate)
    sg.add_node("apply", apply_decision)
    sg.add_node("save", save_node)

    sg.set_entry_point("check")
    sg.add_edge("check", "gate")
    sg.add_conditional_edges(
        "gate",
        lambda s: "apply" if not s["need_human"] else "END",
    )
    sg.add_edge("apply", "save")
    sg.set_finish_point("save")

    # checkpointerが問題を起こしているので完全に無効化
    return sg.compile()
