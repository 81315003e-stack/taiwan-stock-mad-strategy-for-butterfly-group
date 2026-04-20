import os
import datetime
import time
import requests
import pandas as pd
import numpy as np
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
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"❌ Telegram 發送失敗: {response.text}")
    except Exception as e:
        print(f"❗ 發送時發生錯誤: {e}")

def run_mad_strategy():
    print(">>> [版本：7.0] Telegram 完整修補版啟動 <<<")
    
    dl = DataLoader() 
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    # 1. 獲取股票清單
    try:
        stock_info = dl.taiwan_stock_info()
        stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
    except Exception as e:
        print(f"❌ 獲取清單失敗: {e}")
        return

    # 2. 抓取資料
    all_data = []
    test_range = stock_list[:50] # 測試前 50 檔，穩了再自己改大
    print(f"📡 正在掃描 {len(test_range)} 檔標的...")

    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date, end_date=today_str)
            if not df.empty and len(df) > 200:
                all_data.append(df)
            time.sleep(0.1) 
        except:
            continue

    # 3. 處理選股邏輯
    if not all_data:
        send_telegram_msg("⚠️ 今日 API 額度可能已滿，無法獲取數據。")
        return

    full_df = pd.concat(all_data)
    
    # 計算 MAD 指標
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # --- 關鍵修復：確保 final_picks 一定會被定義 ---
    final_picks = pd.DataFrame() 
    
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        
        today_df['pass_mrat'] = (today_df['mrat'] > q90) & (today_df['mrat'] > (1 + std_val))
        today_df['f1_pass'] = (today_df['close'] / today_df['h20']) > 0.88
        today_df['f2_pass'] = today_df['l10'] > today_df['l11_20']
        today_df['f3_pass'] = today_df['amp5_max'] < today_df['amp6_15_max']

        final_picks = today_df[
            (today_df['pass_mrat']) & (today_df['f1_pass']) & 
            (today_df['f2_pass']) & (today_df['f3_pass'])
        ]

    # 4. 發送 Telegram 通知
    msg = f"*📊 MAD 每週選股報告 ({latest_date})*\n\n"
    if not final_picks.empty:
        msg += "```\n"
        # 格式化輸出
        msg += final_picks[['stock_id', 'close', 'mrat']].to_string(index=False)
        msg += "\n```"
    else:
        msg += "_本週無符合條件標的。_"

    send_telegram_msg(msg)
    print("✅ 處理完成並已嘗試發送通知")

if __name__ == "__main__":
    run_mad_strategy()
