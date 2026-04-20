import os
import datetime
import time
import pandas as pd
from FinMind.data import DataLoader

def run_mad_strategy():
    token = os.getenv('FINMIND_TOKEN')
    dl = DataLoader()
    if token:
        dl.login(api_token=token)
    
    print(f"[{datetime.datetime.now()}] 診斷啟動...")

    # 1. 測試抓取「一檔」指標股（例如台積電 2330）
    test_sid = "2330"
    start_date = (datetime.datetime.now() - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    
    print(f"📡 正在測試 API 連線情況 (標的: {test_sid})...")
    try:
        df = dl.taiwan_stock_daily_adj(stock_id=test_sid, start_date=start_date)
        
        if df.empty:
            print(f"❌ 警告：API 回傳了空表格。這通常代表流量已達上限或 Token 權限不足。")
        else:
            print(f"✅ 成功！抓到 {len(df)} 筆資料。")
            print(f"最新一筆資料日期：{df['date'].max()}")
            
            # 如果測試成功，才繼續跑後面的 10 檔就好（先不跑 100 檔）
            print("\n🚀 開始小規模試跑...")
            # ... (後續選股邏輯)
            
    except Exception as e:
        print(f"❗ API 噴錯了：{str(e)}")

if __name__ == "__main__":
    run_mad_strategy()
