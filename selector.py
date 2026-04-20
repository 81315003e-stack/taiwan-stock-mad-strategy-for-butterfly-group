import os
import datetime
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    dl = DataLoader()
    # 這裡建議手動回溯，避開當天尚未產生的資料
    # 因為你是每週執行，我們抓到「昨天」或是「上週五」最穩
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')

    # 1. 獲取全市場清單 (使用你提到的 4 位數過濾)
    stock_info = dl.taiwan_stock_info()
    stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
    
    all_data = []
    print(f"📡 開始檢索資料區間：{start_date} ~ {end_date}")

    # 2. 批量抓取原始資料 (taiwan_stock_daily)
    for sid in stock_list[:500]: # 建議先掃描前 500 檔權值股，效率最高
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            if not df.empty and len(df) >= 200:
                all_data.append(df)
        except:
            continue

    if not all_data: return
    full_df = pd.concat(all_data)

    # 3. 向量化計算指標 (效率優於 Loop)
    # 分組計算各檔股票的 MA
    full_df['ma21'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(21).mean())
    full_df['ma200'] = full_df.groupby('stock_id')['close'].transform(lambda x: x.rolling(200).mean())
    full_df['mrat'] = full_df['ma21'] / full_df['ma200']

    # 計算 F1~F3 所需欄位
    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['l11_20_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.shift(10).rolling(10).min())
    
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.shift(5).rolling(10).max())

    # 4. 進行最新交易日的橫截面分析
    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    
    # 計算市場統計值
    mrat_std = today_df['mrat'].std()
    mrat_p90 = today_df['mrat'].quantile(0.9)

    # 5. 執行篩選條件
    condition_mrat = (today_df['mrat'] > mrat_p90) & (today_df['mrat'] > (1 + mrat_std))
    condition_f1 = (today_df['close'] / today_df['h20_max']) > 0.88
    condition_f2 = today_df['l10_min'] > today_df['l11_20_min']
    condition_f3 = today_df['amp5_max'] < today_df['amp6_15_max']

    final_picks = today_df[condition_mrat & condition_f1 & condition_f2 & condition_f3]

    print(f"✅ 篩選完成！日期：{latest_date}，選中 {len(final_picks)} 檔。")
    return final_picks
