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
    if not (token and chat_id):
        print("未設定 Telegram Token 或 Chat ID")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def run_mad_strategy():
    print(f">>> [版本：8.1] 每週選股通知版啟動 ({datetime.datetime.now()}) <<<")
    dl = DataLoader() 
    
    # 修正日期：設定結束日期為「昨天」，確保能抓到已完成計算的調整後股價
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1))
    end_date_str = yesterday.strftime('%Y-%m-%d')
    start_date_str = (yesterday - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    # 1. 獲取股票清單
    try:
        stock_info = dl.taiwan_stock_info()
        # 篩選 4 位數的個股
        stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        print(f"✅ 成功獲取清單，共 {len(stock_list)} 檔標的")
    except Exception as e:
        send_telegram_msg(f"❌ 獲取股票清單失敗: {e}")
        return

    # 2. 抓取資料 (每週執行一次，我們可以把範圍開大到 300 檔)
    all_data = []
    scan_count = 300 
    test_range = stock_list[:scan_count]
    print(f"📡 正在掃描前 {scan_count} 檔標的...")

    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date_str, end_date=end_date_str)
            if not df.empty and len(df) > 200:
                all_data.append(df)
            time.sleep(0.1) 
        except:
            continue

    if not all_data:
        send_telegram_msg(f"⚠️ 於 {end_date_str} 區間未抓取到有效數據，請檢查 API 狀態。")
        return

    # 3. 選股計算邏輯
    full_df = pd.concat(all_data)
    # 計算 MAD 因子： $MRAT = \frac{MA_{21}}{MA_{200}}$
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    
    # Price Action 條件
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 篩選名單
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_values = today_df['mrat'].dropna()
    final_picks = pd.DataFrame()

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

    # 5. Telegram 發送結果
    msg = f"*📊 MAD 每週選股報告 ({latest_date})*\n"
    msg += f"掃描樣本：前 {scan_count} 檔個股\n"
    msg += "---"
    if not final_picks.empty:
        msg += "\n```\n"
        msg += final_picks[['stock_id', 'close', 'mrat']].round(3).to_string(index=False)
        msg += "\n```"
    else:
        msg += "\n_本週樣本內無符合標的。_"

    send_telegram_msg(msg)
    print(f"✅ 任務完成，資料日期：{latest_date}")

if __name__ == "__main__":
    run_mad_strategy()
