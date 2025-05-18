# ocr.py
import json
import base64
from typing import List
from openai import OpenAI
from models import Card

client = OpenAI()

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
