import os
import datetime
import time
import requests
import pandas as pd
from FinMind.data import DataLoader

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not (token and chat_id): return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

def run_mad_strategy():
    print(">>> [版本：8.0] 診斷強化版啟動 <<<")
    dl = DataLoader() 
    
    # --- 關鍵修正：將結束日期設為「昨天」 ---
    # 這樣可以確保避開尚未產生的「盤中調整後資料」
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1))
    end_date_str = yesterday.strftime('%Y-%m-%d')
    start_date_str = (yesterday - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    print(f"📡 嘗試檢索區間：{start_date_str} 至 {end_date_str}")

    # 1. 獲取股票清單 (取前 20 檔權值股做精確測試)
    # 我們先手動指定幾檔熱門股，確保排除「冷門股無資料」的因素
    test_range = ['2330', '2317', '2454', '2308', '2382', '3231', '2301', '2881', '2882', '1301']

    all_data = []
    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date_str, end_date=end_date_str)
            if not df.empty and len(df) > 200:
                all_data.append(df)
                print(f"✅ {sid}: 成功獲取 {len(df)} 筆資料")
            else:
                reason = "空表格" if df.empty else f"資料長度不足({len(df)}筆)"
                print(f"⚠️ {sid}: {reason}")
            time.sleep(0.5) 
        except Exception as e:
            print(f"❗ {sid} 請求異常: {e}")

    if not all_data:
        # 改為更精確的報錯回報
        error_msg = f"❌ 檢索失敗\n測試標的：{test_range}\n日期區間：{start_date_str} ~ {end_date_str}\n原因：API 回傳皆為空值。建議下午 4 點後再執行。"
        send_telegram_msg(error_msg)
        return

    # ... (後續計算與發送邏輯與版本 7.0 相同) ...
    # (此處為節省空間略過，請保留你 selector.py 後半段的計算與 Telegram 發送部分)
