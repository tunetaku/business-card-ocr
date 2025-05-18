# app.py
# ------------------------------------------------------------
# Business-card OCR & 重複確認フロー (Streamlit + LangGraph)
# ------------------------------------------------------------
import os, sqlite3, json, base64
from typing import List, Dict, TypedDict, Literal

import streamlit as st
from openai import OpenAI

from langgraph.graph import StateGraph          # ← 0.3 以降
from langgraph.types import interrupt

# ====== 0. 環境変数 ==========================================================
# OPENAI_API_KEY は事前に export / set しておく
client = OpenAI()

# ====== 1. 型定義 ============================================================
class Card(TypedDict, total=False):
    name: str | None
    company: str | None
    email: str | None
    phone: str | None

class State(TypedDict, total=False):
    cards: List[Card]                                    # OCR 済みすべて
    new_cards: List[Card]                                # 既存無し
    dup_cards: List[Card]                                # 衝突分
    need_human: bool                                     # True → UI 介入
    decisions: Dict[str, Literal["overwrite", "skip"]]   # email → 行動
    final_cards: List[Card]                              # 保存対象
    skipped: List[str]                                   # スキップ email

# ====== 2. DB 初期化 ========================================================
DB_PATH = "contacts.db"
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

with sqlite3.connect(DB_PATH) as con:
    con.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT,
            company TEXT,
            email   TEXT UNIQUE,
            phone   TEXT
        );
    """)

def exists(email: str) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        return con.execute("SELECT 1 FROM contacts WHERE email=?", (email,)).fetchone() is not None

def save_cards(cards: List[Card]):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        for c in cards:
            if exists(c["email"]):
                cur.execute("""UPDATE contacts
                               SET name=?, company=?, phone=?
                               WHERE email=?""",
                            (c["name"], c["company"], c["phone"], c["email"]))
            else:
                cur.execute("""INSERT INTO contacts
                               (name, company, email, phone)
                               VALUES (?,?,?,?)""",
                            (c["name"], c["company"], c["email"], c["phone"]))
        con.commit()

# ====== 3. Vision OCR (複数ファイル対応) =====================================
def ocr_many(files) -> List[Card]:
    out: List[Card] = []
    for f in files:
        data_uri = "data:image/png;base64," + base64.b64encode(f.getvalue()).decode()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system",
                 "content": "You are an OCR engine for business cards. "
                            "Return ONLY valid JSON with keys: "
                            "name, company, email, phone (null if absent)."},
                {"role": "user",
                 "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}}
                 ]},
            ],
        )
        try:
            card = json.loads(resp.choices[0].message.content)
            out.append(card)
        except json.JSONDecodeError:
            out.append({"error": "parse_failed"})
    return out

# ====== 4. LangGraph ノード定義 =============================================
def check_dup(state: State) -> State:
    new_, dup_ = [], []
    for c in state["cards"]:
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
    overwrite = {c["email"]: c for c in state["dup_cards"]
                 if state["decisions"].get(c["email"]) == "overwrite"}
    skip = {email for email in state["decisions"]
            if state["decisions"][email] == "skip"}
    state["final_cards"] = state["new_cards"] + list(overwrite.values())
    state["skipped"] = list(skip)
    return state

def save_node(state: State) -> State:
    save_cards(state["final_cards"])
    return state

# ====== 5. Graph 組み立て ====================================================
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

# Configure checkpointer with all required options
graph = sg.compile(checkpointer={"configurable": {"thread_id": "__thread__"}, "type": "file", "config": {"directory": "./checkpoints"}})

# ====== 6. Streamlit UI ======================================================
st.set_page_config(page_title="名刺 OCR Demo", page_icon="📇")
st.title("📇 Business-Card OCR Demo")

files = st.file_uploader(
    "名刺画像を選択（複数枚可）",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

# session_state 保持
if "thread_id" not in st.session_state: st.session_state.thread_id = None
if "dup_cards" not in st.session_state: st.session_state.dup_cards = None

# --- 解析開始ボタン ----------------------------------------------------------
if st.button("🖨️ 解析開始") and files:
    cards = ocr_many(files)
    result = graph.invoke({"cards": cards})

    if result.get("need_human"):
        # UI 介入
        st.session_state.thread_id = result["__thread__"]
        st.session_state.dup_cards = result["dup_cards"]
        st.warning("⚠️ 登録済みデータと重複があります。上書き or スキップを選択してください。")
    else:
        st.success("保存完了！")
        st.json(result["final_cards"])

# --- 重複解決 UI -------------------------------------------------------------
if st.session_state.dup_cards:
    st.subheader("重複カードの処理")
    decisions = {}
    for c in st.session_state.dup_cards:
        email = c["email"]
        choice = st.radio(
            f"{email} ({c.get('name')} / {c.get('company')})",
            ("overwrite", "skip"),
            key=email,
        )
        decisions[email] = choice

    if st.button("決定して保存"):
        thread = st.session_state.thread_id
        resumed = graph.resume(thread, {"decisions": decisions})
        st.success(f"保存完了！スキップ: {', '.join(resumed['skipped']) or 'なし'}")
        st.session_state.thread_id = None
        st.session_state.dup_cards = None
        st.json(resumed["final_cards"])

# --- データベース一覧 --------------------------------------------------------
with sqlite3.connect(DB_PATH) as con:
    rows = con.execute("SELECT name, company, email, phone FROM contacts").fetchall()

if rows:
    st.divider()
    st.subheader("📚 名刺データベース")
    st.table(rows)
