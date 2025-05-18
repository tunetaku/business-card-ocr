# app.py
# ------------------------------------------------------------
# Business-card OCR & 重複確認フロー (Streamlit + LangGraph)
# ------------------------------------------------------------
import streamlit as st
from db import init_db
from ocr import ocr_many
from ui import (
    init_session_state, 
    render_upload_tabs, 
    render_edit_form, 
    render_duplicate_resolution, 
    render_contact_database
)

# データベース初期化
init_db()

# Streamlit UI 設定
st.set_page_config(page_title="名刺 OCR Demo", page_icon="📇")
st.title("📇 Business-Card OCR Demo")

# セッション状態初期化
init_session_state()

# ファイルクリアフラグチェック
if st.session_state.clear_files_flag:
    if "card_files" in st.session_state:
        del st.session_state["card_files"]
    st.session_state.clear_files_flag = False

# アップロードタブ表示
files = render_upload_tabs()

# 入力ファイルの取得
has_files = files is not None and len(files) > 0
has_camera_images = len(st.session_state.files_from_camera) > 0

all_files = []
if has_files:
    all_files.extend(files)
if has_camera_images:
    all_files.extend(st.session_state.files_from_camera)

# 解析開始ボタン
if st.button("🔊 解析開始", disabled=(not has_files and not has_camera_images)) and all_files:
    st.info(f"📝 合計 {len(all_files)} 枚の画像を処理中...")
    
    # ファイルをOCR処理
    cards = ocr_many(all_files)
    
    # OCR結果をセッションに保存し、編集モードを有効化
    st.session_state.ocr_results = cards
    st.session_state.edit_mode = True
    st.session_state.edited_cards = cards.copy()
    
    # ページを再読み込みして編集フォームを表示
    st.rerun()

# 編集フォーム表示
render_edit_form()

# 重複解決UI表示
render_duplicate_resolution()

# データベース一覧表示
render_contact_database()