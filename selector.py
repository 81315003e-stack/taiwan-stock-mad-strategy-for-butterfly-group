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
    print(f">>> [版本：9.0] MAD 原始資料策略啟動 ({datetime.datetime.now()}) <<<")
    dl = DataLoader()
    
    # 考量到 17:30 更新，我們抓取到「昨天」最穩；若在晚上執行，可改為今日
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    # 1. 獲取股票清單 (4位數個股)
    stock_info = dl.taiwan_stock_info()
    stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
    
    all_data = []
    # 每週跑一次，建議掃描量可以開到 300-500 檔
    target_stocks = stock_list[:300] 
    print(f"📡 準備掃描 {len(target_stocks)} 檔標的，區間：{start_date} ~ {end_date}")

    for sid in target_stocks:
        try:
            # 使用原始資料 taiwan_stock_daily
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            if not df.empty and len(df) >= 200:
                all_data.append(df)
        except:
            continue
        time.sleep(0.05)

    if not all_data:
        print("❌ 檢索結果：未獲取到任何有效資料。")
        send_telegram_msg("⚠️ 系統警告：未能從 API 獲取任何有效股價資料。")
        return

    full_df = pd.concat(all_data)
    print(f"📊 數據整合完成 ({len(all_data)} 檔)，開始計算 MAD 指標...")

    # 2. 計算核心指標
    # MRAT = MA(21) / MA(200)
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # F1: 近20日高點
    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    # F2: 低點比較 (近10日 vs 近11-20日)
    full_df['l10_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    # F3: 振幅收斂 (近5日 vs 近6-15日)
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 3. 橫截面篩選
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) == 0:
        print("❌ 指標計算後無有效值。")
        return

    mrat_p90 = mrat_values.quantile(0.9)
    mrat_std = mrat_values.std()

    # 執行條件過濾
    c_mrat = (today_df['mrat'] > mrat_p90) & (today_df['mrat'] > (1 + mrat_std))
    c_f1 = (today_df['close'] / today_df['h20_max']) > 0.88
    c_f2 = today_df['l10_min'] > today_df['l11_20_min']
    c_f3 = today_df['amp5_max'] < today_df['amp6_15_max']

    final_picks = today_df[c_mrat & c_f1 & c_f2 & c_f3]

    # 4. Telegram 發送
    msg = f"*📊 MAD 策略報告 ({latest_date})*\n"
    msg += f"公式：$MRAT = MA_{{21}} / MA_{{200}}$\n"
    msg += "---"
    if not final_picks.empty:
        msg += "\n```\n"
        msg += final_picks[['stock_id', 'close', 'mrat']].round(3).to_string(index=False)
        msg += "\n```"
    else:
        msg += "\n_本週樣本內無符合標的。_"

    send_telegram_msg(msg)
    print(f"✅ 任務圓滿完成，選中 {len(final_picks)} 檔股票。")

if __name__ == "__main__":
    run_mad_strategy()
