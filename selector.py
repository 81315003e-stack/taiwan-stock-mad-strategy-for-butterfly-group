import os
import datetime
import time
import requests
import pandas as pd
from FinMind.data import DataLoader
import sys

# 強制讓 print 立即顯示在 Log 中
def print_log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print_log("❌ 錯誤：找不到 Telegram Token 或 Chat ID 變數！")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    res = requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
    if res.status_code == 200:
        print_log("✅ Telegram 訊息已成功送出！")
    else:
        print_log(f"❌ Telegram 發送失敗：{res.text}")

def run_mad_strategy():
    print_log("🚀 診斷啟動：程式開始執行...")
    
    dl = DataLoader()
    token = os.getenv('FINMIND_TOKEN')
    if token:
        dl.login(api_token=token)
        print_log("🔑 FinMind Token 登入設定完成")
    
    # 1. 測試 API 存取
    print_log("📡 正在嘗試抓取全市場快照 (這一步最容易卡住)...")
    try:
        market_all = dl.taiwan_stock_daily_last()
        if market_all.empty:
            print_log("⚠️ 警告：全市場快照回傳空值，可能是 API 維護中")
            send_telegram_msg("⚠️ 今日市場快照回傳空值，請檢查 FinMind 狀態")
            return
        print_log(f"✅ 成功抓取快照，共 {len(market_all)} 筆資料")
    except Exception as e:
        print_log(f"❌ API 報錯：{str(e)}")
        send_telegram_msg(f"❌ API 執行錯誤：{str(e)}")
        return

    # 2. 篩選活跃股
    active_df = market_all[
        (market_all['volume'] >= 500000) & 
        (market_all['stock_id'].str.match(r'^\d{4}$'))
    ]
    active_list = active_df['stock_id'].unique().tolist()
    print_log(f"🔍 篩選出 {len(active_list)} 檔活躍股 (成交量 > 500張)")

    if not active_list:
        print_log("⚠️ 沒有符合成交量門檻的股票，停止執行")
        return

    # 3. 測試發送
    test_msg = f"📊 MAD 診斷報告\n---\n目前偵測到市場活躍股數：{len(active_list)} 檔\n資料日期：{market_all['date'].max()}\n系統運作正常，準備開始深度掃描..."
    send_telegram_msg(test_msg)

    # (這裡為了診斷先跑前 50 檔，確保能快速跑完看到結果)
    print_log("🏗️ 準備進入深度掃描邏輯...")
    # ... (此處可保留你之前的 MAD 計算邏輯) ...

# --- 這是最重要的部分，沒這兩行程式就不會跑 ---
if __name__ == "__main__":
    try:
        run_mad_strategy()
    except Exception as fatal_e:
        print_log(f"💥 程式發生致命錯誤：{str(fatal_e)}")
