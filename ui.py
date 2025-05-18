# ui.py
import streamlit as st
import pandas as pd
from models import Card, State
from db import get_all_contacts
from ocr import ocr_many
from graph import check_dup, apply_decision, save_node

def init_session_state():
    if "dup_cards" not in st.session_state: st.session_state.dup_cards = None
    if "current_state" not in st.session_state: st.session_state.current_state = None
    if "clear_files_flag" not in st.session_state: st.session_state.clear_files_flag = False
    if "ocr_results" not in st.session_state: st.session_state.ocr_results = None
    if "edit_mode" not in st.session_state: st.session_state.edit_mode = False
    if "edited_cards" not in st.session_state: st.session_state.edited_cards = []
    if "files_from_camera" not in st.session_state: st.session_state.files_from_camera = []

def should_clear_files():
    # ファイルクリアフラグをセット
    st.session_state["clear_files_flag"] = True
    # カメラで撮影した写真もクリア
    if "files_from_camera" in st.session_state:
        st.session_state.files_from_camera = []
    # 再実行
    st.rerun()

def render_upload_tabs():
    tab1, tab2 = st.tabs(["📁 ファイルアップロード", "📷 カメラで撮影"])
    
    with tab1:
        # ファイルアップローダーにキーを追加し、セッションで管理できるようにする
        files = st.file_uploader(
            "名刺画像を選択（複数枚可）",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="card_files"
        )
    
    with tab2:
        # カメラ入力
        camera_img = st.camera_input("カメラで名刺を撮影", key="camera_image")
        
        # カメラで撮影した画像がある場合、それをfilesとして扱う
        if camera_img is not None:
            if camera_img not in st.session_state.files_from_camera:
                st.session_state.files_from_camera.append(camera_img)
            
            # 撮影した画像の一覧を表示
            if len(st.session_state.files_from_camera) > 0:
                st.write(f"撮影済み: {len(st.session_state.files_from_camera)}枚")
                
                # 画像をクリアするボタン
                if st.button("撮影画像をクリア"):
                    st.session_state.files_from_camera = []
                    st.rerun()
    
    return files

def render_edit_form():
    if not st.session_state.edit_mode or not st.session_state.ocr_results:
        return
    
    st.subheader("📝 OCR結果の編集")
    st.write("データを確認し、必要に応じて編集してください。")
    
    edited_cards = []
    
    # 各カードの編集フォームを表示
    for i, card in enumerate(st.session_state.edited_cards):
        with st.expander(f"カード {i+1}: {card.get('name', '名前なし')} - {card.get('company', '会社名なし')}", expanded=(i==0)):
            cols = st.columns([1, 1])
            
            # 左側のカラム
            with cols[0]:
                name = st.text_input("名前", card.get("name", ""), key=f"name_{i}")
                company = st.text_input("会社名", card.get("company", ""), key=f"company_{i}")
                email = st.text_input("メールアドレス", card.get("email", ""), key=f"email_{i}")
                phone = st.text_input("電話番号", card.get("phone", ""), key=f"phone_{i}")
                department = st.text_input("部署名", card.get("department", ""), key=f"department_{i}")
                job_title = st.text_input("役職", card.get("job_title", ""), key=f"job_title_{i}")
            
            # 右側のカラム
            with cols[1]:
                qualification = st.text_input("資格・肩書き", card.get("qualification", ""), key=f"qualification_{i}")
                company_address = st.text_input("会社住所", card.get("company_address", ""), key=f"company_address_{i}")
                company_url = st.text_input("会社URL", card.get("company_url", ""), key=f"company_url_{i}")
                company_phone = st.text_input("会社電話", card.get("company_phone", ""), key=f"company_phone_{i}")
                company_fax = st.text_input("会社FAX", card.get("company_fax", ""), key=f"company_fax_{i}")
            
            # 編集後のカードを保存
            edited_card = {
                "name": name or None,
                "company": company or None,
                "email": email or None,
                "phone": phone or None,
                "department": department or None,
                "job_title": job_title or None,
                "qualification": qualification or None,
                "company_address": company_address or None,
                "company_url": company_url or None,
                "company_phone": company_phone or None,
                "company_fax": company_fax or None
            }
            edited_cards.append(edited_card)
    
    # 編集完了ボタン
    if st.button("編集完了、保存へ進む"):
        # 編集後のデータをセッションに保存
        st.session_state.edited_cards = edited_cards
        
        # 初期状態を定義
        initial_state = {"cards": edited_cards}
        
        # チェックノードを実行して重複カードを検出
        state = check_dup(initial_state.copy())
        
        # 編集モードを無効化
        st.session_state.edit_mode = False
        
        if state["need_human"]:
            # 重複がある場合はセッションに保存
            st.session_state.current_state = state
            st.session_state.dup_cards = state["dup_cards"]
            st.rerun()  # 重複解決モードに切り替え
        else:
            # 重複がない場合は直接セーブ処理を行う
            # decisionsが不要なのでapply_decisionをスキップ
            state["final_cards"] = state["new_cards"]
            state = save_node(state)
            st.success("保存完了！")
            
            # 保存後にファイルをクリア
            should_clear_files()
            st.rerun()  # 編集モードを完全に無効化

def render_duplicate_resolution():
    if not st.session_state.dup_cards:
        return
    
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

def render_contact_database():
    rows = get_all_contacts()
    
    if not rows:
        return
    
    st.divider()
    st.subheader("📚 名刺データベース")
    
    # データをPandasデータフレームに変換して列名を指定
    df = pd.DataFrame(rows, columns=[
        "氏名", "会社名", "メールアドレス", "個人電話", 
        "部署名", "役職", "肩書き", "会社住所", 
        "会社URL", "会社電話", "会社FAX"
    ])
    
    # 検索機能のためのフィルターボックス
    st.text_input("🔍 検索", key="search_term", placeholder="検索語句を入力...")
    search_term = st.session_state.get("search_term", "").lower()
    
    # 検索条件に一致する行をフィルタリング
    if search_term:
        mask = False
        for col in df.columns:
            # 各列で検索語句を含む行を探す (NaN値は文字列に変換)
            mask = mask | df[col].astype(str).str.lower().str.contains(search_term, na=False)
        filtered_df = df[mask]
    else:
        filtered_df = df
    
    # カスタム CSS で横スクロールを有効化し、最小幅を設定
    st.markdown("""
    <style>
    .data-table-container {
        min-width: 1200px;  /* 最小幅の設定 */
        overflow-x: auto;   /* 横スクロールを有効化 */
    }
    </style>
    """, unsafe_allow_html=True)
    
    # データフレームを表示 (検索可能、横スクロール対応)
    with st.container():
        st.markdown('<div class="data-table-container">', unsafe_allow_html=True)
        st.dataframe(
            filtered_df,
            use_container_width=True,
            column_config={
                "氏名": st.column_config.TextColumn("氏名", width="medium"),
                "会社名": st.column_config.TextColumn("会社名", width="medium"),
                "メールアドレス": st.column_config.TextColumn("メールアドレス", width="medium"),
                "個人電話": st.column_config.TextColumn("個人電話", width="medium"),
                "部署名": st.column_config.TextColumn("部署名", width="medium"),
                "役職": st.column_config.TextColumn("役職", width="medium"),
                "肩書き": st.column_config.TextColumn("肩書き", width="medium"),
                "会社住所": st.column_config.TextColumn("会社住所", width="large"),
                "会社URL": st.column_config.LinkColumn("会社URL", width="medium"),
                "会社電話": st.column_config.TextColumn("会社電話", width="medium"),
                "会社FAX": st.column_config.TextColumn("会社FAX", width="medium")
            },
            height=400
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 統計情報
    st.caption(f"全 {len(df)} 件中 {len(filtered_df)} 件表示中")
