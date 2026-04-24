import os
import datetime
import time
import requests
import pandas as pd
import numpy as np
from FinMind.data import DataLoader
import sys

def print_log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def run_batched_strategy():
    # --- 0. 讀取分段參數 (修正後的防呆版本) ---
    # 先抓出原始字串
    raw_start = os.getenv('SLICE_START')
    raw_end = os.getenv('SLICE_END')
    
    # 這裡的邏輯是：如果有抓到東西且不是空格，就轉成數字；否則給預設值 0 或 500
    start_idx = int(raw_start) if raw_start and raw_start.strip() else 0
    end_idx = int(raw_end) if raw_end and raw_end.strip() else 500
    
    print_log(f"🚀 MAD 分批掃描啟動：範圍 {start_idx} ~ {end_idx}")
    dl = DataLoader()
    
    # 1. 獲取全市場清單
    try:
        stock_info = dl.taiwan_stock_info()
        full_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        target_stocks = full_list[start_idx:end_idx]
        print_log(f"✅ 載入清單成功，本批次掃描 {len(target_stocks)} 檔")
    except Exception as e:
        print_log(f"❌ 獲取清單失敗: {e}")
        return

    all_price_data = []
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')

    # 2. 【第一層漏斗】抓取價格並篩選 MAD 動能
    print_log("📡 階段 1：正在掃描價格動能 (MAD)...")
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=today)
            if df.empty or len(df) < 200: continue
            
            # 成交量檢查 (500張)
            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            if not vol_col or df.iloc[-1][vol_col] < 500000: continue
            
            # 計算 MAD (MRAT)
            df['ma21'] = df['close'].rolling(21).mean()
            df['ma200'] = df['close'].rolling(200).mean()
            df['mrat'] = df['ma21'] / df['ma200']
            
            # 初步篩選：MRAT 必須大於 1.0 (多頭趨勢) 才會進下一關
            if df['mrat'].iloc[-1] > 1.0:
                all_price_data.append(df)
        except:
            continue
        time.sleep(0.02)

    if not all_price_data:
        print_log("⚠️ 本批次無符合動能標的。")
        return

    # 3. 【第二層漏斗】對動能標的進行基本面檢查
    print_log(f"📡 階段 2：針對 {len(all_price_data)} 檔潛力股檢查營收 (YoY > 15%)...")
    final_data_list = []
    rev_start = (datetime.datetime.now() - datetime.timedelta(days=400)).strftime('%Y-%m-%d')

    for df in all_price_data:
        sid = df['stock_id'].iloc[0]
        try:
            rev_df = dl.taiwan_stock_month_revenue(stock_id=sid, start_date=rev_start)
            if rev_df.empty or len(rev_df) < 13: continue
            
            rev_yoy = (rev_df.iloc[-1]['revenue'] - rev_df.iloc[-13]['revenue']) / rev_df.iloc[-13]['revenue']
            
            if rev_yoy >= 0.15:
                df['rev_yoy'] = rev_yoy
                final_data_list.append(df)
        except:
            continue
        time.sleep(0.05)

    if not final_data_list:
        print_log("⚠️ 本批次標的基本面 YoY 未達標。")
        return

    # 4. 指標計算與發送 (與之前邏輯相同)
    full_df = pd.concat(final_data_list)
    full_df.columns = [c.lower() for c in full_df.columns]
    
    # 詳細 F1-F3
    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 橫截面訊號標籤
    today_df['ma21_dist'] = (today_df['close'] - today_df['ma21']) / today_df['ma21']
    
    def get_signal(row):
        if row['close'] >= row['h20_max']: return "🔥 帶量突破"
        if 0 <= row['ma21_dist'] <= 0.03: return "🛡️ 回測支撐"
        if row['amp5_max'] < row['amp6_15_max']: return "⌛ 蓄勢待發"
        return "👀 趨勢向上"

    today_df['signal'] = today_df.apply(get_signal, axis=1)
    
    # 發送訊息
    msg = f"*📊 MAD 全市場報告 ({latest_date})*\n"
    msg += f"分段：{start_idx}~{end_idx} | 營收 YoY > 15%\n---\n"
    msg += "代號  價格  YoY%  時機\n"
    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += f"`{row['stock_id']}`  {row['close']:>5.1f}  {row['rev_yoy']*100:>4.1f}%  {row['signal']}\n"

    send_telegram_msg(msg)
    print_log(f"✅ 分段 {start_idx} 執行完畢")

if __name__ == "__main__":
    run_batched_strategy()
