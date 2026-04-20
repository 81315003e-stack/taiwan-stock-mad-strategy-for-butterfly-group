import os
import datetime
import time
import requests
import pandas as pd
import numpy as np
from FinMind.data import DataLoader
import sys

# 強制 print 立即輸出到 GitHub Actions Log 中
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
            print_log("✅ Telegram 訊息已成功送出")
        else:
            print_log(f"❌ Telegram 發送失敗：{res.text}")
    except Exception as e:
        print_log(f"❌ 發送異常：{e}")

def run_mad_strategy():
    print_log("🚀 MAD 完整策略版 15.0 啟動...")
    dl = DataLoader()
    
    # 1. 獲取市場清單 (鎖定 4 位數代碼)
    try:
        stock_info = dl.taiwan_stock_info()
        stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        print_log(f"✅ 成功獲取清單，共 {len(stock_list)} 檔標的")
    except Exception as e:
        print_log(f"❌ 獲取清單失敗: {e}")
        return

    # 2. 批量檢索資料 (限制 550 檔以符合 API 每小時 600 次限制)
    target_stocks = stock_list[:550] 
    all_data = []
    
    # 診斷計數器
    count_too_short = 0
    count_low_volume = 0
    
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')

    print_log(f"📡 正在掃描前 {len(target_stocks)} 檔標的之歷史資料...")
    
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=today)
            
            # 檢查資料長度 (至少要 200 交易日才能算 MA200)
            if df.empty or len(df) < 200:
                count_too_short += 1
                continue
            
            # 自動偵測成交量欄位 (FinMind 常用 'Trading_Volume' 或 'volume')
            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            
            if vol_col:
                # 方案 B：檢查最後一個交易日的成交量是否 >= 500 張 (500,000 股)
                if df.iloc[-1][vol_col] >= 500000:
                    all_data.append(df)
                else:
                    count_low_volume += 1
            else:
                count_low_volume += 1
                
        except:
            continue
        time.sleep(0.02) # 保護 API 頻率

    print_log(f"📊 掃描結束。篩選結果：符合成交量門檻 {len(all_data)} 檔 (天數不足 {count_too_short}, 量不足 {count_low_volume})")

    if not all_data:
        send_telegram_msg(f"⚠️ 診斷報告：今日掃描 {len(target_stocks)} 檔，皆不符合量大或天數條件。系統運作正常。")
        return

    # 3. 核心指標計算 (全部向量化處理)
    full_df = pd.concat(all_data)
    
    # 欄位統一轉換為小寫以利計算
    full_df.columns = [c.lower() for c in full_df.columns]
    
    # 核心因子：MRAT = MA(21) / MA(200)
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    
    # Price-action 過濾所需欄位
    # F1: Close/近20日高點
    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    # F2: 近10日低點 vs 前10日(近11~20日)低點
    full_df['l10_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    # F3: 近5日振幅 vs 前10日(近6~15日)振幅
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 進行最新交易日的橫截面篩選
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_vals = today_df['mrat'].dropna()
    if mrat_vals.empty:
        print_log("❌ 錯誤：計算後無有效 mrat 資料")
        return

    mrat_p90 = mrat_vals.quantile(0.9) # 90% 分位
    mrat_std = mrat_vals.std()      # 橫截面標準差

    # 執行條件篩選
    # 條件 1: MAD 核心篩選
    c_mad = (today_df['mrat'] > mrat_p90) & (today_df['mrat'] > (1 + mrat_std))
    # 條件 2: F1 過濾
    c_f1 = (today_df['close'] / today_df['h20_max']) > 0.88
    # 條件 3: F2 過濾 (底部墊高)
    c_f2 = today_df['l10_min'] > today_df['l11_20_min']
    # 條件 4: F3 過濾 (波動收斂)
    c_f3 = today_df['amp5_max'] < today_df['amp6_15_max']

    final_picks = today_df[c_mad & c_f1 & c_f2 & c_f3]

    # 5. Telegram 發送報告
    msg = f"*📊 MAD 智慧選股報告 ({latest_date})*\n"
    msg += f"掃描樣本：{len(target_stocks)} 檔 (活躍股 {len(all_data)} 檔)\n"
    msg += f"公式：$MRAT = MA_{{21}} / MA_{{200}}$\n"
    msg += "---"
    
    if not final_picks.empty:
        msg += "\n```\n"
        # 顯示代號、收盤價、MRAT
        msg += final_picks[['stock_id', 'close', 'mrat']].round(3).to_string(index=False)
        msg += "\n```"
    else:
        msg += "\n_本週樣本內無符合條件標的。_"

    send_telegram_msg(msg)
    print_log(f"✅ 策略執行圓滿完成，最新日期為 {latest_date}")

if __name__ == "__main__":
    try:
        run_mad_strategy()
    except Exception as fatal_e:
        print_log(f"💥 程式發生致命錯誤：{fatal_e}")
