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
    department: str | None    # 部署名
    job_title: str | None     # 役職
    qualification: str | None # その他肩書（資格など）
    company_address: str | None # 会社住所
    company_url: str | None   # 会社URL
    company_phone: str | None # 会社電話
    company_fax: str | None   # 会社FAX

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

# 既存のDBファイルを削除（リセット）
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

with sqlite3.connect(DB_PATH) as con:
    con.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT,
            company         TEXT,
            email           TEXT UNIQUE,
            phone           TEXT,
            department      TEXT,
            job_title       TEXT,
            qualification   TEXT,
            company_address TEXT,
            company_url     TEXT,
            company_phone   TEXT,
            company_fax     TEXT
        );
    """)

def exists(email: str) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        return con.execute("SELECT 1 FROM contacts WHERE email=?", (email,)).fetchone() is not None

def save_cards(cards: List[Card]):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        for c in cards:
            # 安全にフィールド取得
            name = c.get("name", "")
            company = c.get("company", "")
            email = c.get("email", None)
            phone = c.get("phone", "")
            department = c.get("department", "")
            job_title = c.get("job_title", "")
            qualification = c.get("qualification", "")
            company_address = c.get("company_address", "")
            company_url = c.get("company_url", "")
            company_phone = c.get("company_phone", "")
            company_fax = c.get("company_fax", "")
            
            # メールアドレスがない場合は保存しない
            if not email:
                continue
                
            # 重複チェック
            if exists(email):
                cur.execute("""UPDATE contacts
                               SET name=?, company=?, phone=?, department=?, 
                                   job_title=?, qualification=?, company_address=?,
                                   company_url=?, company_phone=?, company_fax=?
                               WHERE email=?""",
                            (name, company, phone, department, job_title, qualification,
                             company_address, company_url, company_phone, company_fax, email))
            else:
                cur.execute("""INSERT INTO contacts
                               (name, company, email, phone, department, job_title, qualification,
                                company_address, company_url, company_phone, company_fax)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (name, company, email, phone, department, job_title, qualification,
                             company_address, company_url, company_phone, company_fax))
        con.commit()

# ====== 3. Vision OCR (複数ファイル対応) =====================================
def ocr_many(files) -> List[Card]:
    out: List[Card] = []
    for f in files:
        # ファイル名から適切なMIMEタイプを自動判定
        filename = f.name.lower() if hasattr(f, "name") else "unknown"
        mime_type = "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else "image/png"
        
        # 正しいMIMEタイプでdata URIを生成
        data_uri = f"data:{mime_type};base64," + base64.b64encode(f.getvalue()).decode()
        
        # より詳細なプロンプトを使用
        system_prompt = """
        あなたは名刺画像のテキストを正確に抽出するOCRエンジンです。
        以下のフィールドを含むJSON形式でのみ回答してください：

        {{
          "name": "人物名", // 名刺の所有者の名前。存在しない場合はnull
          "company": "会社名", // 会社名。存在しない場合はnull
          "email": "email@example.com", // メールアドレス。存在しない場合はnull
          "phone": "電話番号" // 電話番号。存在しない場合はnull
          "department": "部署名", // 部署名。存在しない場合はnull
          "job_title": "役職", // 役職。存在しない場合はnull
          "qualification": "肩書", // その他肩書（資格など）。存在しない場合はnull
          "company_address": "会社住所", // 会社住所。存在しない場合はnull
          "company_url": "会社URL", // 会社URL。存在しない場合はnull
          "company_phone": "会社電話", // 会社電話。存在しない場合はnull
          "company_fax": "会社FAX" // 会社FAX。存在しない場合はnull
        }}
        
        注意: 必ず有効なJSON形式で全フィールドを含めてください。存在しないフィールドはnullとしてください。
        画像に文字が見つからない場合でも、空のJSONを返さず必ず全フィールドに値を設定してください。
        """
        
        # より性能の高いモデルを使用
        resp = client.chat.completions.create(
            model="gpt-4o",  # より性能の高いモデルに変更
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]},
            ],
        )
        
        # デバッグ用に生のAPIレスポンスを表示
        raw_content = resp.choices[0].message.content
        print(f"OCR結果: {raw_content}")
        
        # Markdownコードブロック文法を削除
        content_to_parse = raw_content
        # ```jsonと```を削除
        if content_to_parse.startswith('```'):
            # 最初の```行を削除
            first_newline = content_to_parse.find('\n')
            if first_newline != -1:
                content_to_parse = content_to_parse[first_newline+1:]
            # 最後の```を削除
            last_backticks = content_to_parse.rfind('```')
            if last_backticks != -1:
                content_to_parse = content_to_parse[:last_backticks]
        
        print(f"パース対象: {content_to_parse}")
        
        try:
            card = json.loads(content_to_parse)
            # 各フィールドの存在を確認
            required_fields = ["name", "company", "email", "phone", "department", "job_title", "qualification", "company_address", "company_url", "company_phone", "company_fax"]
            for field in required_fields:
                if field not in card:
                    card[field] = None
            out.append(card)
        except json.JSONDecodeError:
            print("JSONパースエラー: ", content_to_parse)
            out.append({"error": "parse_failed", "name": None, "company": None, "email": None, "phone": None, "department": None, "job_title": None, "qualification": None, "company_address": None, "company_url": None, "company_phone": None, "company_fax": None})
    return out

# ====== 4. LangGraph ノード定義 =============================================
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

# checkpointerが問題を起こしているので完全に無効化
graph = sg.compile()

# ====== 6. Streamlit UI ======================================================
st.set_page_config(page_title="名刺 OCR Demo", page_icon="📇")
st.title("📇 Business-Card OCR Demo")

# ファイルアップローダーにキーを追加し、セッションで管理できるようにする
files = st.file_uploader(
    "名刺画像を選択（複数枚可）",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    key="card_files"
)

# session_state 保持
if "dup_cards" not in st.session_state: st.session_state.dup_cards = None
if "current_state" not in st.session_state: st.session_state.current_state = None
if "clear_files_flag" not in st.session_state: st.session_state.clear_files_flag = False

# ファイルクリアフラグがセットされていたら実行
if st.session_state.clear_files_flag:
    if "card_files" in st.session_state:
        del st.session_state["card_files"]
    st.session_state.clear_files_flag = False

# ファイルクリア用関数
def should_clear_files():
    # ファイルクリアフラグをセット
    st.session_state["clear_files_flag"] = True
    # 再実行
    st.experimental_rerun()

# --- 解析開始ボタン ----------------------------------------------------------
if st.button("🖨️ 解析開始") and files:
    cards = ocr_many(files)
    
    # 初期状態を定義
    initial_state = {"cards": cards}
    
    # LangGraphのワークフローを一度に実行できるよう修正
    # 重複チェックを手動で実行
    state = initial_state.copy()
    
    # チェックノードを実行して重複カードを検出
    state = check_dup(state)
    
    if state["need_human"]:
        # 重複がある場合はセッションに保存
        st.session_state.current_state = state
        st.session_state.dup_cards = state["dup_cards"]
        st.warning("⚠️ 登録済みデータと重複があります。上書き or スキップを選択してください。")
    else:
        # 重複がない場合は直接セーブ処理を行う
        # decisionsが不要なのでapply_decisionをスキップ
        state["final_cards"] = state["new_cards"]
        state = save_node(state)
        st.success("保存完了！")
        st.json(state["final_cards"])
        
        # 保存後にファイルをクリア
        should_clear_files()

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
        # 保存していた状態にユーザーの決定を追加
        if st.session_state.current_state:
            # 最新のステートにdecisionsを追加
            updated_state = st.session_state.current_state.copy()
            updated_state["decisions"] = decisions
            
            # グラフの実行を継続
            # applyノードから手動で実行
            result = apply_decision(updated_state)
            result = save_node(result)
            
            st.success(f"保存完了！スキップ: {', '.join(result.get('skipped', [])) or 'なし'}")
            st.session_state.dup_cards = None
            st.session_state.current_state = None
            st.json(result["final_cards"])
            
            # ファイルをクリア
            should_clear_files()

# --- データベース一覧 --------------------------------------------------------
with sqlite3.connect(DB_PATH) as con:
    rows = con.execute("SELECT name, company, email, phone, department, job_title, qualification, company_address, company_url, company_phone, company_fax FROM contacts").fetchall()

if rows:
    st.divider()
    st.subheader("📚 名刺データベース")
    
    # データをPandasデータフレームに変換して列名を指定
    import pandas as pd
    df = pd.DataFrame(rows, columns=[
        "氏名", "会社名", "メールアドレス", "個人電話", 
        "部署名", "役職", "肩書き", "会社住所", 
        "会社URL", "会社電話", "会社FAX"
    ])
    
    # データフレームを表として表示
    st.table(df)
