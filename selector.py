import os
import datetime
import time
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def run_mad_strategy():
    # --- 關鍵修復點：刪除所有 .login() 指令 ---
    print(">>> [版本：4.0] 啟動成功！這版已經徹底移除 .login 指令 <<<")
    
    token = os.getenv('FINMIND_TOKEN')
    
    # 建立 DataLoader 的正確方式
    try:
        dl = DataLoader(api_token=token)
        print("✅ DataLoader 初始化成功")
    except Exception as e:
        dl = DataLoader()
        print(f"⚠️ 使用無 Token 模式初始化: {e}")

    # 1. 獲取股票清單
    try:
        stock_info = dl.taiwan_stock_info()
        print(f"✅ 成功抓取股票清單，共 {len(stock_info)} 筆資料")
    except Exception as e:
        print(f"❌ 抓取清單失敗: {e}")
        return

    # 2. 測試抓取（我們先抓 5 檔，確保 API 流量不會被鎖住）
    stock_list = stock_info['stock_id'].unique().tolist()
    test_range = stock_list[:5] 
    start_date = (datetime.datetime.now() - datetime.timedelta(days=400)).strftime('%Y-%m-%d')
    
    print(f"📡 診斷測試中，抓取標的：{test_range}")
    
    all_data = []
    for sid in test_range:
        try:
            df = dl.taiwan_stock_daily_adj(stock_id=sid, start_date=start_date)
            if not df.empty:
                print(f"✅ {sid}: 抓取成功 ({len(df)} 筆)")
                all_data.append(df)
            else:
                print(f"❌ {sid}: API 回傳空值")
            time.sleep(1) # 強制延遲 1 秒，這是為了保護你的 API Token 不被封鎖
        except Exception as e:
            print(f"❗ {sid} 錯誤: {e}")

    if not all_data:
        print("\n[結果] 沒抓到數據。如果是『回傳空值』，代表你今天的 API 額度用完了。")
        return

    print("\n--- 恭喜！環境驗證完全通過！ ---")

if __name__ == "__main__":
    run_mad_strategy()
