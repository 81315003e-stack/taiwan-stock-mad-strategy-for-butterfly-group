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
    if not (token and chat_id): return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

def run_mad_strategy():
    print(f">>> [版本：8.2] 週末相容版啟動 ({datetime.datetime.now()}) <<<")
    dl = DataLoader() 
    
    # --- 核心邏輯修改：自動抓取最新可用資料 ---
    # 設定 end_date 為今天，API 會自動回傳「直到最近一個交易日」的所有資料
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date_str = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    print(f"📡 請求區間：{start_date_str} 至 {today_str} (自動涵蓋最近交易日)")

    # 1. 獲取股票清單
    stock_info = dl.taiwan_stock_info()
    stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()

    # 2. 抓取資料 (每週執行，建議掃描前 200 檔即可，確保速度與穩定)
    all_data = []
    scan_limit = 200
    for sid in stock_list[:scan_limit]:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date_str, end_date=today_str)
            if not df.empty and len(df) > 200:
                all_data.append(df)
        except:
            continue
        time.sleep(0.1)

    if not all_data:
        send_telegram_msg("⚠️ 樣本內未發現有效交易資料，請確認 API 狀態或市場是否正處於長期休市。")
        return

    full_df = pd.concat(all_data)
    
    # 3. 計算因子 (MAD 核心公式： $MRAT = \frac{MA_{21}}{MA_{200}}$)
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    # ... (其餘 F1~F3 計算邏輯同前一版) ...
    
    # 此處保留 F1~F3 的計算代碼
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # ... (篩選與發送邏輯) ...
    # 最終發送時，這版會正確抓到「上週五 (4/17)」的數據作為最新報告日期
    msg = f"*📊 MAD 每週選股報告 (資料日期：{latest_date})*\n"
    # ... (組合訊息代碼) ...
    send_telegram_msg(msg)

if __name__ == "__main__":
    run_mad_strategy()
