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

def run_hybrid_strategy():
    print_log("🚀 MAD 全能決策版 16.0 啟動 (基本面 + 技術面觸發)...")
    dl = DataLoader()
    
    # 1. 獲取市場清單
    try:
        stock_info = dl.taiwan_stock_info()
        stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        print_log(f"✅ 成功獲取清單，共 {len(stock_list)} 檔")
    except Exception as e:
        print_log(f"❌ 獲取清產失敗: {e}")
        return

    target_stocks = stock_list[:500] # 為了 API 額度安全，先鎖定前 500 檔
    passed_stocks_data = []
    
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date_price = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    start_date_revenue = (datetime.datetime.now() - datetime.timedelta(days=400)).strftime('%Y-%m-%d')

    print_log(f"📡 正在掃描前 {len(target_stocks)} 檔標的...")
    
    for sid in target_stocks:
        try:
            # A. 技術面抓取與初步過濾
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date_price, end_date=today)
            if df.empty or len(df) < 200: continue
            
            # 成交量欄位偵測與過濾 (成交量 > 500張)
            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            if not vol_col or df.iloc[-1][vol_col] < 500000: continue
            
            # B. 基本面濾網：月營收年增率 (YoY)
            # 為了節省 API，我們對初步符合條件的才抓營收
            revenue_df = dl.taiwan_stock_month_revenue(stock_id=sid, start_date=start_date_revenue)
            if revenue_df.empty or len(revenue_df) < 13: continue
            
            # 計算最新一期營收 YoY
            latest_rev = revenue_df.iloc[-1]['revenue']
            last_year_rev = revenue_df.iloc[-13]['revenue']
            rev_yoy = (latest_rev - last_year_rev) / last_year_rev
            
            # 核心基本面條件：營收 YoY > 15% (代表風口上的實質成長)
            if rev_yoy < 0.15: continue
            
            # 將基本面數據暫存進 df 方便後續計算
            df['rev_yoy'] = rev_yoy
            passed_stocks_data.append(df)
            
        except:
            continue
        time.sleep(0.02)

    if not passed_stocks_data:
        send_telegram_msg("⚠️ 今日掃描結束，無符合「營收成長」且「動能強勢」標的。")
        return

    # 3. 核心指標與價格觸發邏輯
    full_df = pd.concat(passed_stocks_data)
    full_df.columns = [c.lower() for c in full_df.columns]
    
    # MAD 與 F1-F3 計算
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # --- 新增：進場訊號所需欄位 ---
    vol_col = 'trading_volume' if 'trading_volume' in full_df.columns else 'volume'
    full_df['vol_ma5'] = full_df.groupby('stock_id')[vol_col].transform(lambda x: x.rolling(5).mean())
    full_df['vol_ratio'] = full_df[vol_col] / full_df['vol_ma5']
    full_df['ma21_dist'] = (full_df['close'] - full_df['ma21']) / full_df['ma21']

    def get_signal(row):
        if row['close'] >= row['h20_max'] and row['vol_ratio'] > 1.3:
            return "🔥 帶量突破"
        if 0 <= row['ma21_dist'] <= 0.03 and row['vol_ratio'] < 1.2:
            return "🛡️ 回測支撐"
        if row['amp5_max'] < row['amp6_15_max'] and row['vol_ratio'] < 1.0:
            return "⌛ 蓄勢待發"
        return "👀 趨勢向上"

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 橫截面篩選
    mrat_vals = today_df['mrat'].dropna()
    mrat_p90 = mrat_vals.quantile(0.9)
    mrat_std = mrat_vals.std()

    final_picks = today_df[
        (today_df['mrat'] > mrat_p90) & (today_df['mrat'] > (1 + mrat_std)) &
        (today_df['close'] / today_df['h20_max'] > 0.88) &
        (today_df['l10_min'] > today_df['l11_20_min'])
    ].copy()

    final_picks['signal'] = final_picks.apply(get_signal, axis=1)

    # 4. Telegram 格式化報告
    msg = f"*📊 MAD 決策報告 ({latest_date})*\n"
    msg += f"篩選：營收 YoY > 15% + 成交量 > 500張\n"
    msg += "---"
    
    if not final_picks.empty:
        msg += "\n代號  價格  YoY%  時機\n"
        for _, row in final_picks.sort_values('mrat', ascending=False).iterrows():
            msg += f"`{row['stock_id']}`  {row['close']:>5.1f}  {row['rev_yoy']*100:>4.1f}%  {row['signal']}\n"
    else:
        msg += "\n_今日無符合營收與動能雙標的。_"

    send_telegram_msg(msg)
    print_log(f"✅ 報告發送完成。")

if __name__ == "__main__":
    run_hybrid_strategy()
