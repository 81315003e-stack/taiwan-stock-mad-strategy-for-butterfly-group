import os
import datetime
import requests
import pandas as pd
from FinMind.data import DataLoader

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("未設定 Telegram Token 或 Chat ID，跳過通知。")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown" # 讓文字可以有粗體或等寬字體，看起來更專業
    }
    
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("✅ Telegram 通知發送成功")
        else:
            print(f"❌ Telegram 發送失敗: {response.text}")
    except Exception as e:
        print(f"❗ 發送時發生錯誤: {e}")

def run_mad_strategy():
    # ... (前面的選股邏輯保持不變，版本 6.0 的邏輯) ...
    
    # 組合訊息
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    msg = f"*📊 MAD 每週強勢股報告 ({date_str})*\n\n"
    
    if not final_picks.empty:
        # 使用 Markdown 的程式碼區塊格式，讓清單整齊對齊
        msg += "```\n"
        msg += final_picks[['stock_id', 'close', 'mrat']].to_string(index=False)
        msg += "\n```"
    else:
        msg += "_本週無符合條件標的。_"

    send_telegram_msg(msg)

if __name__ == "__main__":
    run_mad_strategy()
