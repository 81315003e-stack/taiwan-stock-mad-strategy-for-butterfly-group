import os
import datetime
import time
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    print(">>> [版本：6.0] 究極通關版！修正清單抓取邏輯 <<<")
    
    # 1. 初始化
    dl = DataLoader() 
    
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    # 2. 獲取股票清單
    try:
        stock_info = dl.taiwan_stock_info()
        # 診斷：印出前幾行看看
        print(f"成功獲取清單，欄位有: {stock_info.columns.tolist()}")
        
        # 寬鬆過濾：只要代號是 4 位數字的通常就是一般個股 (排除權證、長代碼標的)
        stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        print(f"過濾完成，符合條件的股票共 {len(stock_list)} 檔")
    except Exception as e:
        print(f"❌ 獲取清單失敗: {e}")
        return

    if not stock_list:
        print("❌ 過濾後無標的，請檢查 stock_info 內容。")
        return

    all_data = []
    # 為了測試，我們先抓「前 50 檔」確保一定有資料且不爆流量
    test_range = stock_list[:50] 
    print(f"📡 正在掃描 {len(test_range)} 檔標的 (範圍: {start_date} 至 {today_str})")

    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date, end_date=today_str)
            if not df.empty and len(df) > 200:
                all_data.append(df)
                print(f"✅ {sid} 抓取成功")
            else:
                # 即使沒抓到也印一下原因
                pass
            time.sleep(0.1) 
        except:
            continue

    if not all_data:
        print("❌ 沒抓到有效數據。可能原因：1. API 額度用盡 2. 網路連線異常。")
        return

    full_df = pd.concat(all_data)
    print(f"📊 數據整合完成 ({len(all_data)} 檔)，計算 MAD 選股因子...")

    # --- 3. 計算因子 ---
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # --- 4. 篩選今日結果 ---
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_values = today_df['mrat'].dropna()
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

        print(f"\n🎯 --- {latest_date} MAD 策略選股結果 ---")
        if final_picks.empty:
            print("目前樣本中無符合所有條件的強勢標的。")
        else:
            print(final_picks[['stock_id', 'close', 'mrat']].to_string(index=False))
    else:
        print("❌ MRAT 計算失敗。")

if __name__ == "__main__":
    run_mad_strategy()
