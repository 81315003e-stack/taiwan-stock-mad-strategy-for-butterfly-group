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
    try:
        requests.post(url, data=payload)
        print_log("✅ Telegram 訊息已送出")
    except Exception as e:
        print_log(f"❌ 發送異常：{e}")

def run_mad_strategy():
    print_log("🚀 MAD 究極穩定版啟動...")
    dl = DataLoader()
    
    # 1. 取得全市場名單 (這步在 1.9.7 是穩定的)
    try:
        stock_info = dl.taiwan_stock_info()
        # 篩選 4 位數個股 (上市/上櫃)
        stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        print_log(f"✅ 成功獲取清單，全市場共 {len(stock_list)} 檔")
    except Exception as e:
        print_log(f"❌ 獲取清單失敗: {e}")
        return

    # 2. 批量抓取 (限制 550 檔，確保不爆 API 額度)
    # 權值股與熱門股通常排在前面，這 550 檔已經綽綽有餘
    target_stocks = stock_list[:550] 
    all_data = []
    
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')

    print_log(f"📡 正在抓取 {len(target_stocks)} 檔標的之歷史資料...")
    
    for sid in target_stocks:
        try:
            # 使用最標準的 daily 接口
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=today)
            if not df.empty and len(df) >= 200:
                # 方案 B 的核心：在資料進來後檢查最後一天的成交量
                # 成交量 > 500,000 股 (500張)
                last_vol = df.iloc[-1]['Volume'] if 'Volume' in df.columns else df.iloc[-1]['volume']
                if last_vol >= 500000:
                    all_data.append(df)
        except:
            continue
        # 稍微停頓，保護 API
        time.sleep(0.02)

    if not all_data:
        print_log("⚠️ 掃描結束，無符合條件的資料。")
        return

    # 3. 合併與指標計算
    full_df = pd.concat(all_data)
    # 計算公式：MRAT = MA21 / MA200
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    
    # Price Action 欄位
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 橫截面統計
    mrat_vals = today_df['mrat'].dropna()
    if mrat_vals.empty: return
    mrat_p90 = mrat_vals.quantile(0.9)
    mrat_std = mrat_vals.std()

    # MAD 選股條件套用
    final_picks = today_df[
        (today_df['mrat'] > mrat_p90) & (today_df['mrat'] > (1 + mrat_std)) &
        (today_df['close'] / today_df['h20'] > 0.88) &
        (today_df['l10'] > today_df['l11_20']) &
        (today_df['amp5_max'] < today_df['amp6_15_max'])
    ]

    # 4. 發送結果
    msg = f"*📊 MAD 智慧選股報告 ({latest_date})*\n"
    msg += f"篩選：成交量 > 500張 (樣本 {len(target_stocks)} 檔)\n---"
    if not final_picks.empty:
        msg += "\n```\n" + final_picks[['stock_id', 'close', 'mrat']].round(3).to_string(index=False) + "\n```"
    else:
        msg += "\n_目前市場無符合標的。_"

    send_telegram_msg(msg)
    print_log(f"✅ 流程完成！資料日期：{latest_date}")

if __name__ == "__main__":
    run_mad_strategy()
