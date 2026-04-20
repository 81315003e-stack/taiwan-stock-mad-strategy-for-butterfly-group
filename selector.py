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
    print(f">>> [版本：8.3] 究極診斷版啟動 ({datetime.datetime.now()}) <<<")
    dl = DataLoader() 
    
    # 1. 獲取清單
    try:
        stock_info = dl.taiwan_stock_info()
        # 確保代號乾淨且為 4 位數
        stock_list = stock_info[stock_info['stock_id'].str.strip().str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        print(f"✅ 獲取清單：共 {len(stock_list)} 檔標的")
    except Exception as e:
        print(f"❌ 獲取清單失敗: {e}")
        return

    # 2. 抓取資料
    # 我們不設定 end_date，讓 API 自己回傳到最新有資料的那天
    start_date_str = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    all_data = []
    # 測試範圍：我們從台股權值股 (2330, 2317, 2454...) 開始抓，這些一定有資料
    test_range = ['2330', '2317', '2454', '2308', '2382', '3231', '2301', '2881'] + stock_list[:50]
    # 去重並保持順序
    test_range = list(dict.fromkeys(test_range))

    print(f"📡 正在掃描 {len(test_range)} 檔標的，起始日期：{start_date_str}")

    for sid in test_range:
        try:
            # 關鍵修改：移除 end_date，讓 API 給出「截至目前最新」的資料
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date_str)
            
            if not df.empty:
                # 策略需要 MA200，資料長度必須夠長
                if len(df) > 200:
                    all_data.append(df)
                    if len(all_data) <= 5: # 只印前5檔確認
                        print(f"✅ {sid} 抓取成功，最新日期：{df['date'].max()} ({len(df)} 筆)")
                else:
                    # 這檔資料不夠長，略過
                    pass
            time.sleep(0.1) 
        except:
            continue

    if not all_data:
        # 如果還是空的，這次我們直接把 API 原始的回傳狀態印出來
        send_telegram_msg("❌ 警告：所有測試標的均回傳空值。\n這代表資料庫目前的『調整後股價』模組可能正在維護或尚未產出今日數據。")
        return

    full_df = pd.concat(all_data)
    
    # 3. 計算因子 $MRAT = \frac{MA_{21}}{MA_{200}}$
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    
    # ... 其餘計算邏輯保持不變 ...
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 篩選名單
    mrat_values = today_df['mrat'].dropna()
    final_picks = pd.DataFrame()

    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        
        today_df['pass_mrat'] = (today_df['mrat'] > q90) & (today_df['mrat'] > (1 + std_val))
        today_df['f1_pass'] = (today_df['close'] / today_df['h20']) > 0.88
        today_df['f2_pass'] = today_df['l10'] > today_df['l11_20']
        today_df['f3_pass'] = today_df['amp5_max'] < today_df['amp6_15_max']

        final_picks = today_df[(today_df['pass_mrat']) & (today_df['f1_pass']) & 
                               (today_df['f2_pass']) & (today_df['f3_pass'])]

    # 4. Telegram 發送
    msg = f"*📊 MAD 選股報告 ({latest_date})*\n"
    if not final_picks.empty:
        msg += "```\n" + final_picks[['stock_id', 'close', 'mrat']].round(3).to_string(index=False) + "\n```"
    else:
        msg += "_本週樣本內無符合標的。_"

    send_telegram_msg(msg)

if __name__ == "__main__":
    run_mad_strategy()
