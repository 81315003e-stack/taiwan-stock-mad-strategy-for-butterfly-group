import os
import datetime
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    # 1. 初始化 (FinMind 在 1.9.x 版通常會自動抓環境變數中的 Token)
    token = os.getenv('FINMIND_TOKEN')
    
    # 直接在初始化時嘗試帶入 token
    try:
        dl = DataLoader(api_token=token)
    except:
        dl = DataLoader()
    
    print(f"[{datetime.datetime.now()}] 環境初始化完成，準備開始選股...")

    # 2. 獲取股票清單
    stock_info = dl.taiwan_stock_info()
    stock_list = stock_info[stock_info['category'] == '股票']['stock_id'].unique().tolist()
    
    # 為了算 MA200，抓取過去一年的資料
    start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    
    all_data = []
    # 建議先跑前 200 檔測試，確認邏輯通了再全開
    test_range = stock_list[:200] 

    print(f"正在抓取 {len(test_range)} 檔股票資料...")
    for sid in test_range:
        try:
            # 抓取調整後股價
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            if not df.empty and len(df) > 200:
                all_data.append(df)
        except:
            continue
            
    if not all_data:
        print("❌ 未抓取到足夠數據，請檢查權限或市場是否開盤。")
        return

    full_df = pd.concat(all_data)

    # 3. 計算因子與條件
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # F1 準備：近20日高點
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    # F2 準備：低點比較
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    # F3 準備：振幅比較
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 篩選最新日期資料
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 橫截面分析
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        today_df['pass_mrat'] = (today_df['mrat'] > q90) & (today_df['mrat'] > (1 + std_val))
    else:
        today_df['pass_mrat'] = False

    # 5. Price-action 三大過濾
    today_df['f1_pass'] = (today_df['close'] / today_df['h20']) > 0.88
    today_df['f2_pass'] = today_df['l10'] > today_df['l11_20']
    today_df['f3_pass'] = today_df['amp5_max'] < today_df['amp6_15_max']

    # 6. 最終選股
    final_picks = today_df[
        (today_df['pass_mrat']) & (today_df['f1_pass']) & 
        (today_df['f2_pass']) & (today_df['f3_pass'])
    ]

    # 7. 輸出結果
    print(f"\n✅ --- {latest_date} MAD 策略選股結果 ---")
    if final_picks.empty:
        print("今日市場波動可能不符條件，無推薦標的。")
    else:
        # 只顯示需要的欄位
        print(final_picks[['stock_id', 'close', 'mrat']].to_string(index=False))

if __name__ == "__main__":
    run_mad_strategy()
