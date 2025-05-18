# models.py
from typing import List, Dict, TypedDict, Literal

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
