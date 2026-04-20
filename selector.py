import os
import datetime
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    # 1. 初始化 (FinMind 會自動從環境變數抓取 FINMIND_TOKEN)
    token = os.getenv('FINMIND_TOKEN')
    
    # 建立 DataLoader。在 1.9.7 版本中，這一步就會觸發 Login success
    dl = DataLoader() 
    
    print(f"[{datetime.datetime.now()}] 系統初始化完成，準備開始選股...")

    # 2. 獲取股票清單
    stock_info = dl.taiwan_stock_info()
    
    # 根據日誌，確認欄位名稱 (通常是 'industry_category' 或 'type')
    # 我們這裡採安全寫法：直接抓所有代碼，測試前 100 檔
    stock_list = stock_info['stock_id'].unique().tolist()
    
    # 設定回溯時間 (計算 MA200 需要約一年的資料)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    
    all_data = []
    # 為了避免 API 流量爆掉，我們先從前 100 檔開始跑
    test_range = stock_list[:100] 

    print(f"📡 正在抓取 {len(test_range)} 檔股票資料...")
    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            if not df.empty and len(df) > 200:
                all_data.append(df)
        except:
            continue
            
    if not all_data:
        print("❌ 未抓取到足夠數據，請檢查 API 權限或市場日期。")
        return

    full_df = pd.concat(all_data)

    # 3. 計算 MAD 核心因子
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # F1-F3 條件計算
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 篩選最新日期的資料進行橫截面分析
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 計算 MRAT 的標準差與分位數
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        
        # 核心過濾邏輯
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
            print("今日無符合條件的股票。")
        else:
            print(final_picks[['stock_id', 'close', 'mrat']].to_string(index=False))
    else:
        print("無法計算 MRAT 指標。")

if __name__ == "__main__":
    run_mad_strategy()
