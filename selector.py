import os
import datetime
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    # 1. 初始化與登入
    token = os.getenv('FINMIND_TOKEN')
    dl = DataLoader()
    if token:
        dl.login(api_token=token)
    
    print(f"[{datetime.datetime.now()}] 開始執行 MAD 選股策略...")

    # 2. 獲取股票清單 (以證券交易所上市股票為主，避免小數量的冷門股)
    stock_info = dl.taiwan_stock_info()
    stock_list = stock_info[stock_info['category'] == '股票']['stock_id'].unique().tolist()
    
    # 設定回溯時間，為了算 MA200，我們至少需要 280 天以上的資料
    start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    
    all_data = []
    # 為了避免 GitHub Action 執行過久，建議先從權值股或前 300 檔開始測試
    # 若你的 FinMind 權限足夠，可以移除 [:300] 跑全市場
    test_range = stock_list[:300] 

    for sid in test_range:
        try:
            # 抓取調整後股價 (Adjusted Price)
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            if not df.empty and len(df) > 200:
                all_data.append(df)
        except:
            continue
            
    if not all_data:
        print("未抓取到足夠數據，請檢查 API Token 或網路狀況。")
        return

    full_df = pd.concat(all_data)

    # 3. 計算因子與條件 (Group by stock_id)
    # 核心因子：MRAT = MA(21) / MA(200)
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # F1 準備：近20日高點
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())

    # F2 準備：近10日低點、前11-20日低點
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())

    # F3 準備：振幅 (Amplitude)
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 篩選最新一天的資料進行「橫截面分析」
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 計算全市場 MRAT 的分位數與標準差
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        
        # 核心過濾：MRAT 分位 > 90% 且 MRAT > 1 + 標準差
        today_df['pass_mrat'] = (today_df['mrat'] > q90) & (today_df['mrat'] > (1 + std_val))
    else:
        today_df['pass_mrat'] = False

    # 5. Price-action 三大過濾
    # F1: Close/近20日高點 > 0.88
    today_df['f1_pass'] = (today_df['close'] / today_df['h20']) > 0.88
    # F2: 近10日低點高於前10日(11-20日)低點
    today_df['f2_pass'] = today_df['l10'] > today_df['l11_20']
    # F3: 近5日振幅小於前10日(6-15日)振幅
    today_df['f3_pass'] = today_df['amp5_max'] < today_df['amp6_15_max']

    # 6. 最終選股
    final_picks = today_df[
        (today_df['pass_mrat']) & 
        (today_df['f1_pass']) & 
        (today_df['f2_pass']) & 
        (today_df['f3_pass'])
    ]

    # 7. 輸出結果
    print(f"\n--- {latest_date} MAD 策略選股結果 ---")
    if final_picks.empty:
        print("今日無符合條件的股票。")
    else:
        print(final_picks[['stock_id', 'close', 'mrat']].to_string(index=False))

if __name__ == "__main__":
    run_mad_strategy()
