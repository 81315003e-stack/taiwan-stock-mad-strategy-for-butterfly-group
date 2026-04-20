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
    print(f">>> [版本：10.0] 方案 B 智慧掃描啟動 <<<")
    dl = DataLoader()
    
    # 1. 獲取市場快照，找出「活躍股」
    # 我們抓取最近一個交易日的快照 (不指定代號，抓全市場)
    # 注意：若當日 17:30 後執行，可抓當日；否則建議抓前一交易日
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    try:
        # 獲取全市場今日/昨日的最後狀態
        market_all = dl.taiwan_stock_daily_last() 
        # 過濾成交量 > 500,000 股 (500張) 且代號為 4 位數
        active_df = market_all[
            (market_all['volume'] >= 500000) & 
            (market_all['stock_id'].str.match(r'^\d{4}$'))
        ]
        active_list = active_df['stock_id'].unique().tolist()
        print(f"✅ 第一階段篩選完成：從全市場中找出 {len(active_list)} 檔活躍股 (成交量 >= 500張)")
    except Exception as e:
        print(f"⚠️ 無法獲取全市場快照，改用預設清單前 500 檔。錯誤: {e}")
        stock_info = dl.taiwan_stock_info()
        active_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$')]['stock_id'].unique().tolist()[:500]

    # 2. 進行 MAD 深度掃描
    all_data = []
    # 限制總量在 580 檔以內，確保不超過每小時 600 次的限制
    target_stocks = active_list[:580] 
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')

    print(f"📡 第二階段：對 {len(target_stocks)} 檔標的進行 MAD 與 F1-F3 深度運算...")

    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=today)
            if not df.empty and len(df) >= 200:
                all_data.append(df)
        except:
            continue
        time.sleep(0.05)

    if not all_data:
        send_telegram_msg("❌ 方案 B 執行失敗：未能獲取到足夠的歷史資料。")
        return

    full_df = pd.concat(all_data)
    
    # 3. 計算 MAD 指標與 F1~F3
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 橫截面篩選
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_values = today_df['mrat'].dropna()
    mrat_p90 = mrat_values.quantile(0.9)
    mrat_std = mrat_values.std()

    # 篩選條件
    final_picks = today_df[
        (today_df['mrat'] > mrat_p90) & (today_df['mrat'] > (1 + mrat_std)) &
        (today_df['close'] / today_df['h20'] > 0.88) &
        (today_df['l10'] > today_df['l11_20']) &
        (today_df['amp5_max'] < today_df['amp6_15_max'])
    ]

    # 5. Telegram 發送
    msg = f"*📊 MAD 智慧選股報告 ({latest_date})*\n"
    msg += f"篩選標準：成交量 > 500張\n"
    msg += f"掃描樣本：{len(target_stocks)} 檔活躍股\n"
    msg += "---"
    if not final_picks.empty:
        msg += "\n```\n" + final_picks[['stock_id', 'close', 'mrat']].round(3).to_string(index=False) + "\n```"
    else:
        msg += "\n_本週樣本內無符合標的。_"

    send_telegram_msg(msg)
    print(f"✅ 執行完成，選中 {len(final_picks)} 檔。")

if __name__ == "__main__":
    run_mad_strategy()
