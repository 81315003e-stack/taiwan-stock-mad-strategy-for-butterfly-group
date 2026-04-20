import os
import datetime
import time
import requests
import pandas as pd
import numpy as np
from FinMind.data import DataLoader
import sys

# 強制 print 立即輸出到 Log
def print_log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print_log("❌ 錯誤：找不到 Telegram Token 或 Chat ID")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, data=payload)
        if res.status_code == 200:
            print_log("✅ Telegram 訊息已成功送出！")
        else:
            print_log(f"❌ Telegram 發送失敗：{res.text}")
    except Exception as e:
        print_log(f"❌ 發送時發生異常：{e}")

def run_mad_strategy():
    print_log("🚀 MAD 選股策略開始執行...")
    
    # FinMind 會自動讀取環境變數，不需要手動 login
    dl = DataLoader()
    
    # 1. 獲取市場快照，找出「活躍股」
    try:
        market_all = dl.taiwan_stock_daily_last()
        if market_all.empty:
            print_log("⚠️ 無法獲取快照，可能是 API 繁忙，嘗試改用基礎清單...")
            stock_info = dl.taiwan_stock_info()
            active_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$')]['stock_id'].unique().tolist()[:300]
        else:
            # 篩選：成交量 > 500張 (500,000股)
            active_df = market_all[
                (market_all['volume'] >= 500000) & 
                (market_all['stock_id'].str.match(r'^\d{4}$'))
            ]
            active_list = active_df['stock_id'].unique().tolist()
            print_log(f"✅ 成功獲取快照，篩選出 {len(active_list)} 檔活躍股")
    except Exception as e:
        print_log(f"❌ 獲取基礎資料失敗: {e}")
        return

    # 2. 進行深度掃描 (限制在前 580 檔，避免 API 爆額度)
    all_data = []
    target_stocks = active_list[:580]
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')

    print_log(f"📡 正在深度掃描 {len(target_stocks)} 檔標的...")
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=today)
            if not df.empty and len(df) >= 200:
                all_data.append(df)
        except:
            continue
        time.sleep(0.05)

    if not all_data:
        print_log("⚠️ 掃描結束，無符合長度之資料。")
        send_telegram_msg("⚠️ 今日掃描結束，未發現符合資料。")
        return

    # 3. 指標計算與 F1-F3 篩選
    full_df = pd.concat(all_data)
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
    
    # 統計過濾
    mrat_vals = today_df['mrat'].dropna()
    mrat_p90 = mrat_vals.quantile(0.9)
    mrat_std = mrat_vals.std()

    final_picks = today_df[
        (today_df['mrat'] > mrat_p90) & (today_df['mrat'] > (1 + mrat_std)) &
        (today_df['close'] / today_df['h20'] > 0.88) &
        (today_df['l10'] > today_df['l11_20']) &
        (today_df['amp5_max'] < today_df['amp6_15_max'])
    ]

    # 4. 組裝訊息並發送
    msg = f"*📊 MAD 選股報告 ({latest_date})*\n"
    msg += f"掃描樣本：{len(target_stocks)} 檔活躍股\n---"
    if not final_picks.empty:
        msg += "\n```\n" + final_picks[['stock_id', 'close', 'mrat']].round(3).to_string(index=False) + "\n```"
    else:
        msg += "\n_目前無符合標的。_"

    send_telegram_msg(msg)
    print_log(f"✅ 流程完成！選中 {len(final_picks)} 檔。")

if __name__ == "__main__":
    run_mad_strategy()
