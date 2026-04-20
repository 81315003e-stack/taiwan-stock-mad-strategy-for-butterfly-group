import os
import datetime
import time
import requests
import pandas as pd
import numpy as np
from FinMind.data import DataLoader

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not (token and chat_id): return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})

def run_mad_strategy():
    print(f">>> [版本：11.0] 防禦性診斷版啟動 <<<")
    
    # 建立 DataLoader 時直接確認 Token 狀態
    token = os.getenv('FINMIND_TOKEN')
    dl = DataLoader()
    if token:
        try:
            dl.login(api_token=token)
        except Exception as e:
            print(f"⚠️ Token 登入失敗: {e}")

    # --- 關鍵防禦機制：確保 taiwan_stock_info 有抓到東西 ---
    try:
        stock_info = dl.taiwan_stock_info()
        if stock_info.empty:
            raise ValueError("API 回傳了空清單")
        
        # 篩選代號
        stock_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$') == True]['stock_id'].unique().tolist()
        print(f"✅ 成功獲取清單，共 {len(stock_list)} 檔標的")
    except Exception as e:
        error_detail = f"❌ 獲取股票清單失敗！\n錯誤原因：{str(e)}\n這通常是 FinMind 伺服器繁忙或 Token 異常，請稍後再試。"
        print(error_detail)
        send_telegram_msg(error_detail)
        return

    # 之後的選股邏輯 (方案 B) 保持不變...
    # (此處保留之前的計算與篩選代碼)
