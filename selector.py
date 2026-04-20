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
    
    print(f"[{datetime.datetime.now()}] 系統診斷啟動...")

    # 1. 獲取股票清單
    stock_info = dl.taiwan_stock_info()
    stock_list = stock_info['stock_id'].unique().tolist()
    
    # 算 MA200 需要約 280 個交易日，我們抓 400 天最安全
    start_date = (datetime.datetime.now() - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    
    all_data = []
    # --- 調整點：我們先抓「前 10 檔」就好，確保不爆流量，看看到底有沒有東西 ---
    test_range = stock_list[:10] 

    print(f"📡 正在診斷 {len(test_range)} 檔標的，起始日期：{start_date}")

    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            
            if df.empty:
                print(f"❌ {sid}: API 回傳空值 (可能是流量限制或該代碼無資料)")
            else:
                data_len = len(df)
                if data_len > 200:
                    all_data.append(df)
                    print(f"✅ {sid}: 成功抓取 {data_len} 筆資料")
                else:
                    print(f"⚠️ {sid}: 資料長度僅 {data_len} 筆，未達 200 筆要求")
            
            # 休息 1 秒，這對免費版 API 非常重要
            time.sleep(1)
            
        except Exception as e:
            print(f"❗ {sid} 發生連線錯誤: {str(e)}")
            continue
            
    if not all_data:
        print("\n[!!!] 診斷結果：全數抓取失敗，請確認 FinMind 官網的 API 使用額度是否已滿。")
        return

    # --- 之後的計算邏輯保持不變 ---
    full_df = pd.concat(all_data)
    # ... (其餘 MAD 策略邏輯)
    print("\n📊 資料整合成功，開始執行 MAD 計算...")
    # (為了精簡，此處省略後面已確認沒問題的計算 code)

if __name__ == "__main__":
    run_mad_strategy()
