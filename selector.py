import os
import datetime
import time
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    print(">>> [版本：5.0] 最終啟動版！補足 end_date 與選股邏輯 <<<")
    
    # 1. 初始化
    dl = DataLoader() # Token 已由系統環境變數自動載入
    
    # 設定日期範圍
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')
    
    # 2. 獲取股票清單
    stock_info = dl.taiwan_stock_info()
    # 過濾出一般股票標的
    if 'type' in stock_info.columns:
        stock_list = stock_info[stock_info['type'] == 'twstock']['stock_id'].unique().tolist()
    else:
        stock_list = stock_info['stock_id'].unique().tolist()

    all_data = []
    # 為了測試效率與 API 額度，我們抓前 100 檔標的
    test_range = stock_list[:100] 
    print(f"📡 正在掃描 {len(test_range)} 檔標的 (範圍: {start_date} 至 {today_str})")

    for sid in test_range:
        try:
            # 關鍵修復：補上 end_date=today_str
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date, end_date=today_str)
            
            if not df.empty and len(df) > 200:
                all_data.append(df)
            time.sleep(0.1) # 快速掃描
        except:
            continue

    if not all_data:
        print("❌ 沒抓到數據。可能是 API 流量已達上限。請等待一小時後再試。")
        return

    full_df = pd.concat(all_data)
    print(f"📊 成功抓取 {len(all_data)} 檔有效資料，開始計算 MAD 指標...")

    # 3. 計算因子 (MAD 策略核心)
    # MRAT = MA21 / MA200
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # F1~F3 條件計算
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 篩選今日結果
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        
        # 核心篩選條件
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
