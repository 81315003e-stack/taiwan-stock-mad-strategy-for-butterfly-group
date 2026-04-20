import os
import datetime
import time
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    token = os.getenv('FINMIND_TOKEN')
    dl = DataLoader()
    if token:
        dl.login(api_token=token)
    
    print(f"[{datetime.datetime.now()}] 系統啟動，準備執行 MAD 篩選...")

    # 1. 獲取清單
    stock_info = dl.taiwan_stock_info()
    # 過濾出一般股票 (排除 ETF 等)
    stock_list = stock_info[stock_info['type'] == 'twstock']['stock_id'].unique().tolist()
    
    # 算 MA200 需要約 280 個交易日，我們抓 365 天最保險
    start_date = (datetime.datetime.now() - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    
    all_data = []
    # --- 測試階段：先縮小到 20-30 檔，確保 API 額度夠用 ---
    test_range = stock_list[:30] 

    print(f"📡 預計掃描 {len(test_range)} 檔標的，起始日期：{start_date}")

    for sid in test_range:
        try:
            # 抓取調整後股價
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            
            if not df.empty:
                data_len = len(df)
                if data_len > 200:
                    all_data.append(df)
                    print(f"✅ {sid} 抓取成功 (共 {data_len} 筆)")
                else:
                    print(f"⚠️ {sid} 資料長度不足 ({data_len} 筆)，跳過")
            else:
                print(f"❌ {sid} API 回傳空值")
            
            # 稍微停頓 0.5 秒，保護 API 不被鎖
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❗ {sid} 發生錯誤: {str(e)}")
            continue
            
    if not all_data:
        print("\n[!!!] 最終結果：沒有任何股票符合資料長度要求。")
        return

    full_df = pd.concat(all_data)
    print(f"\n📊 數據整合完成，開始計算因子...")

    # --- 後續計算邏輯不變 ---
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

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

        print(f"\n🎯 --- {latest_date} MAD 選股名單 ---")
        if final_picks.empty:
            print("目前這 30 檔中無符合條件標的。")
        else:
            print(final_picks[['stock_id', 'close', 'mrat']].to_string(index=False))
    else:
        print("❌ MRAT 計算失敗，請檢查資料時間跨度。")

if __name__ == "__main__":
    run_mad_strategy()
