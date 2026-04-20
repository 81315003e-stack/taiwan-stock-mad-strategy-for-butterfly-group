import os
import datetime
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    # 1. 初始化
    token = os.getenv('FINMIND_TOKEN')
    try:
        dl = DataLoader(api_token=token)
    except:
        dl = DataLoader()
    
    print(f"[{datetime.datetime.now()}] 登入成功，開始抓取股票清單...")

    # 2. 獲取股票清單並修正欄位名稱
    stock_info = dl.taiwan_stock_info()
    
    # 診斷：看看 FinMind 給了我們哪些欄位
    cols = stock_info.columns.tolist()
    print(f"現有欄位: {cols}")

    # 根據 FinMind 標準，通常類別欄位叫 'industry_category' 或 'type'
    if 'industry_category' in cols:
        # 排除掉 ETF、受益證券等，保留一般產業股票
        filter_out = ['ETF', '受益證券', '存託憑證', '認購權證']
        stock_list = stock_info[~stock_info['industry_category'].isin(filter_out)]['stock_id'].unique().tolist()
    else:
        # 如果找不到類別欄位，直接拿所有代碼（最保險）
        stock_list = stock_info['stock_id'].unique().tolist()
    
    # 設定回溯時間 (365天確保有 MA200 資料)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')
    
    all_data = []
    # 測試階段：我們先抓 150 檔，確保 GitHub Action 執行速度
    test_range = stock_list[:150] 

    print(f"正在抓取 {len(test_range)} 檔股票的調整後價格...")
    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            if not df.empty and len(df) > 200:
                all_data.append(df)
        except:
            continue
            
    if not all_data:
        print("❌ 數據不足，可能是 API 流量達到上限或連線問題。")
        return

    full_df = pd.concat(all_data)

    # 3. 計算因子
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # F1 準備
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    # F2 準備
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    # F3 準備
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 橫截面分析
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        today_df['pass_mrat'] = (today_df['mrat'] > q90) & (today_df['mrat'] > (1 + std_val))
    else:
        today_df['pass_mrat'] = False

    # 5. Price-action 條件
    today_df['f1_pass'] = (today_df['close'] / today_df['h20']) > 0.88
    today_df['f2_pass'] = today_df['l10'] > today_df['l11_20']
    today_df['f3_pass'] = today_df['amp5_max'] < today_df['amp6_15_max']

    # 6. 篩選最終名單
    final_picks = today_df[
        (today_df['pass_mrat']) & (today_df['f1_pass']) & 
        (today_df['f2_pass']) & (today_df['f3_pass'])
    ]

    # 7. 顯示結果
    print(f"\n✅ --- {latest_date} MAD 策略選股名單 ---")
    if final_picks.empty:
        print("今日無符合所有條件的強勢標的。")
    else:
        print(final_picks[['stock_id', 'close', 'mrat']].to_string(index=False))

if __name__ == "__main__":
    run_mad_strategy()
