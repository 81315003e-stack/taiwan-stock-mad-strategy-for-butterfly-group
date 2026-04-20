import os
import pandas as pd
from FinMind.data import DataLoader

def run_strategy():
    # 讀取隱藏在 GitHub Secrets 裡的 Token
    api_token = os.getenv('FINMIND_TOKEN', '')
    
    dl = DataLoader()
    if api_token:
        dl.login(api_token=api_token)
    
    # --- 這裡放入我們之前的選股邏輯 (抓取數據、計算因子、F1-F3 篩選) ---
    # ... (代碼省略，與前次提供一致) ...
    
    # 範例：將結果印出來，GitHub Action 的 Log 會記錄
    print("今日選股清單如下：")
    # print(picks[['date', 'stock_id']])

if __name__ == "__main__":
    run_strategy()
