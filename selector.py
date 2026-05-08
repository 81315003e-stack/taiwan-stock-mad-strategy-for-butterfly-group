import os
import datetime
import time
import requests
import pandas as pd
import numpy as np
from FinMind.data import DataLoader
import sys

def print_log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
    sys.stdout.flush()

def send_telegram_msg(message):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass

def run_batched_strategy():
    # --- 分批參數 ---
    raw_start = os.getenv('SLICE_START')
    raw_end = os.getenv('SLICE_END')
    start_idx = int(raw_start) if raw_start and raw_start.strip() else 0
    end_idx = int(raw_end) if raw_end and raw_end.strip() else 500

    print_log(f"🚀 MAD + EPS 分批掃描啟動：範圍 {start_idx} ~ {end_idx}")

    dl = DataLoader()

    # 1. 取得股票清單
    try:
        stock_info = dl.taiwan_stock_info()
        full_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$')]['stock_id'].unique().tolist()
        target_stocks = full_list[start_idx:end_idx]
        print_log(f"✅ 載入清單成功，本批次 {len(target_stocks)} 檔")
    except Exception as e:
        print_log(f"❌ 獲取清單失敗: {e}")
        return

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=500)).strftime('%Y-%m-%d')
    rev_start = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime('%Y-%m-%d')  # 財報用

    all_price_data = []

    # === 階段 1：技術面 MAD (MRAT) 篩選 ===
    print_log("📡 階段 1：掃描價格動能 (MA21/MA200 > 1.0)...")
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=today)
            if df.empty or len(df) < 200:
                continue

            # 成交量 > 500張
            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            if not vol_col or df.iloc[-1][vol_col] < 500_000:
                continue

            # 計算 MAD / MRAT
            df['ma21'] = df['close'].rolling(21).mean()
            df['ma200'] = df['close'].rolling(200).mean()
            df['mrat'] = df['ma21'] / df['ma200']

            if df['mrat'].iloc[-1] > 1.0:
                df = df.copy()  # 避免 SettingWithCopyWarning
                df['stock_id'] = sid
                all_price_data.append(df)
        except Exception:
            continue
        time.sleep(0.02)

    if not all_price_data:
        print_log("⚠️ 本批次無符合動能標的。")
        return

    # === 階段 2：基本面 EPS YoY 篩選 ===
    print_log(f"📡 階段 2：針對 {len(all_price_data)} 檔檢查 EPS 成長率...")
    final_data_list = []

    for df in all_price_data:
        sid = df['stock_id'].iloc[0]
        try:
            # 抓取綜合損益表 (含 EPS)
            fin_df = dl.taiwan_stock_financial_statement(
                stock_id=sid, 
                start_date=rev_start
            )
            if fin_df.empty or len(fin_df) < 10:
                continue

            # 過濾 EPS 資料
            eps_df = fin_df[fin_df['type'] == 'EPS'].copy()
            if len(eps_df) < 2:
                continue

            eps_df = eps_df.sort_values('date').reset_index(drop=True)
            
            # 最新季 EPS YoY
            latest_eps = eps_df.iloc[-1]['value']
            yoy_eps = eps_df.iloc[-5]['value'] if len(eps_df) >= 5 else None  # 假設季資料，-4 或 -5 視實際而定

            if yoy_eps and yoy_eps != 0:
                eps_yoy = (latest_eps - yoy_eps) / yoy_eps
            else:
                eps_yoy = 0

            # 可調整門檻（建議從 0.15 開始測試）
            if eps_yoy >= 0.15:
                df = df.copy()
                df['eps_yoy'] = eps_yoy
                df['latest_eps'] = latest_eps
                final_data_list.append(df)
                
        except Exception as e:
            # print_log(f"EPS 抓取失敗 {sid}: {e}")  # 除錯時可打開
            continue
        time.sleep(0.08)  # 財報 API 較慢，適度延遲

    if not final_data_list:
        print_log("⚠️ 本批次無符合 EPS 成長標的。")
        return

    # === 階段 3：指標計算與報告 ===
    full_df = pd.concat(final_data_list, ignore_index=True)
    full_df.columns = [c.lower() for c in full_df.columns]

    # 技術指標
    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['l10_min'] = full_df.groupby('stock_id')['min'].transform(lambda x: x.rolling(10).min())
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()

    today_df['ma21_dist'] = (today_df['close'] - today_df['ma21']) / today_df['ma21']

    def get_signal(row):
        if row['close'] >= row['h20_max']:
            return "🔥 帶量突破"
        if 0 <= row['ma21_dist'] <= 0.03:
            return "🛡️ 回測支撐"
        if row.get('amp5_max', 0) < row.get('amp6_15_max', 0):  # 若有前段可補
            return "⌛ 蓄勢待發"
        return "👀 趨勢向上"

    today_df['signal'] = today_df.apply(get_signal, axis=1)

    # 發送 Telegram
    msg = f"*📊 MAD + EPS 報告 ({latest_date})*\n"
    msg += f"分段：{start_idx}~{end_idx} | EPS YoY ≥ 15%\n---\n"
    msg += "代號 價格 EPS_YoY% 時機\n"

    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += f"`{row['stock_id']}` {row['close']:>5.1f} {row['eps_yoy']*100:>5.1f}% {row['signal']}\n"

    send_telegram_msg(msg)
    print_log(f"✅ 分段 {start_idx} 執行完畢，找到 {len(today_df)} 檔符合標的")

if __name__ == "__main__":
    run_batched_strategy()
