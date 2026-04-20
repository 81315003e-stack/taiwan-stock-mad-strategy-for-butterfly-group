import os
import datetime
import time
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    # 1. 初始化 (FinMind 會自動讀取環境變數中的 FINMIND_TOKEN)
    token = os.getenv('FINMIND_TOKEN')
    
    # 建立 DataLoader 時帶入 token 即可，不需要再呼叫 .login()
    try:
        dl = DataLoader(api_token=token)
    except:
        dl = DataLoader()
    
    print(f"[{datetime.datetime.now()}] 登入成功，開始準備選股程序...")

    # 2. 獲取股票清單
    stock_info = dl.taiwan_stock_info()
    
    # 診斷欄位名稱並過濾股票
    cols = stock_info.columns.tolist()
    if 'industry_category' in cols:
        # 排除掉非股票類標的 (如 ETF)
        filter_out = ['ETF', '受益證券', '存託憑證', '認購權證']
        stock_list = stock_info[~stock_info['industry_category'].isin(filter_out)]['stock_id'].unique().tolist()
    else:
        stock_list = stock_info['stock_id'].unique().tolist()
    
    # 設定抓取一整年的資料以計算 MA200
    start_date = (datetime.datetime.now() - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    
    all_data = []
    # 為了避免 API 流量爆掉，我們先抓 100 檔標的測試
    test_range = stock_list[:100] 

    print(f"📡 正在抓取 {len(test_range)} 檔股票資料...")
    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            if not df.empty and len(df) > 200:
                all_data.append(df)
        except Exception:
            continue
        # 稍微停頓避免 API 限制
        time.sleep(0.2)
            
    if not all_data:
        print("❌ 沒抓到足夠數據，可能是今日 API 流量已達上限。")
        return

    full_df = pd.concat(all_data)

    # 3. 計算 MAD 因子
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # F1-F3 準備
    full_df['h20'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    full_df['amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 篩選最新日期的橫截面數據
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    mrat_values = today_df['mrat'].dropna()
    if len(mrat_values) > 0:
        q90 = mrat_values.quantile(0.9)
        std_val = mrat_values.std()
        
        # 核心策略條件篩選
        today_df['pass_mrat'] = (today_df['mrat'] > q90) & (today_df['mrat'] > (1 + std_val))
        today_df['f1_pass'] = (today_df['close'] / today_df['h20']) > 0.88
        today_df['f2_pass'] = today_df['l10'] > today_df['l11_20']
        today_df['f3_pass'] = today_df['amp5_max'] < today_df['amp6_15_max']

        final_picks = today_df[
            (today_df['pass_mrat']) & (today_df['f1_pass']) & 
            (today_df['f2_pass']) & (today_df['f3_pass'])
        ]

        print(f"\n🎯 --- {latest_date} MAD 策略選股名單 ---")
        if final_picks.empty:
            print("目前樣本中無符合所有條件的強勢標的。")
        else:
            print(final_picks[['stock_id', 'close', 'mrat']].to_string(index=False))
    else:
        print("❌ 無法計算橫截面指標，請確認資料跨度是否足夠。")

if __name__ == "__main__":
    run_mad_strategy()
