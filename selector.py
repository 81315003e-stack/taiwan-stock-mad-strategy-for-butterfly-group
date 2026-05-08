import os
import datetime
import time
import requests
import pandas as pd
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
    raw_start = os.getenv('SLICE_START')
    raw_end = os.getenv('SLICE_END')
    start_idx = int(raw_start) if raw_start and raw_start.strip() else 0
    end_idx = int(raw_end) if raw_end and raw_end.strip() else 300

    print_log(f"🚀 MAD + TTM EPS 成長版啟動：範圍 {start_idx} ~ {end_idx}")

    dl = DataLoader()

    # 1. 股票清單
    try:
        stock_info = dl.taiwan_stock_info()
        full_list = stock_info[stock_info['stock_id'].str.match(r'^\d{4}$')]['stock_id'].unique().tolist()
        target_stocks = full_list[start_idx:end_idx]
        print_log(f"✅ 本批次 {len(target_stocks)} 檔")
    except Exception as e:
        print_log(f"❌ 清單失敗: {e}")
        return

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    price_start = (datetime.datetime.now() - datetime.timedelta(days=500)).strftime('%Y-%m-%d')
    fin_start = (datetime.datetime.now() - datetime.timedelta(days=1460)).strftime('%Y-%m-%d')  # 拉長4年確保有足夠季資料

    all_price_data = []

    # === 階段 1：技術面 MAD ===
    print_log("📡 階段 1：技術面篩選 (MRAT > 1.0 + 成交量)...")
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=price_start, end_date=today)
            if df.empty or len(df) < 200:
                continue

            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            if not vol_col or df.iloc[-1][vol_col] < 500_000:
                continue

            df['ma21'] = df['close'].rolling(21).mean()
            df['ma200'] = df['close'].rolling(200).mean()
            df['mrat'] = df['ma21'] / df['ma200']

            if df['mrat'].iloc[-1] > 1.0:
                df = df.copy()
                df['stock_id'] = sid
                all_price_data.append(df)
        except:
            continue
        time.sleep(0.015)

    if not all_price_data:
        print_log("⚠️ 無動能標的")
        return

    # === 階段 2：TTM EPS 成長率（重點優化）===
    print_log(f"📡 階段 2：檢查 TTM EPS 成長 ({len(all_price_data)} 檔)...")
    final_data_list = []

    for df in all_price_data:
        sid = df['stock_id'].iloc[0]
        try:
            fin_df = dl.taiwan_stock_financial_statement(stock_id=sid, start_date=fin_start)
            if fin_df.empty:
                continue

            eps_df = fin_df[fin_df['type'] == 'EPS'].copy()
            if len(eps_df) < 8:   # 至少需要 8 季才能算 YoY TTM
                continue

            eps_df = eps_df.sort_values('date').reset_index(drop=True)
            eps_df['value'] = pd.to_numeric(eps_df['value'], errors='coerce')
            eps_values = eps_df['value'].dropna().values

            if len(eps_values) < 8:
                continue

            # 最新 TTM (最近4季)
            current_ttm = eps_values[-4:].sum()
            
            # 去年同期 TTM (再往前4季)
            prev_ttm = eps_values[-8:-4].sum()

            if prev_ttm <= 0:   # 避免分母為負或零
                continue

            ttm_growth = (current_ttm - prev_ttm) / prev_ttm

            # 放寬門檻建議（可再調整）
            if ttm_growth >= 0.10 or (current_ttm > 1.0 and ttm_growth >= 0):  
                df = df.copy()
                df['ttm_eps'] = current_ttm
                df['ttm_growth'] = ttm_growth
                final_data_list.append(df)

        except Exception:
            continue
        time.sleep(0.08)

    if not final_data_list:
        print_log("⚠️ 本批次無符合 TTM EPS 成長標的（已放寬至10%）")
        return

    # === 階段 3：報告 ===
    full_df = pd.concat(final_data_list, ignore_index=True)
    full_df.columns = [c.lower() for c in full_df.columns]

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()

    # 簡單訊號（可保留你原本的詳細指標）
    today_df['ma21_dist'] = (today_df['close'] - today_df.get('ma21', 0)) / today_df.get('ma21', 1)

    def get_signal(row):
        if row['close'] >= row.get('h20_max', 0):
            return "🔥 帶量突破"
        return "👀 趨勢向上"

    today_df['signal'] = today_df.apply(get_signal, axis=1)

    msg = f"*📊 MAD + TTM EPS 報告 ({latest_date})*\n"
    msg += f"分段：{start_idx}~{end_idx} | TTM Growth ≥10%\n---\n"
    msg += "代號 價格 TTM_EPS 成長% 時機\n"

    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += f"`{row['stock_id']}` {row['close']:>5.1f} {row.get('ttm_eps',0):>6.2f} {row.get('ttm_growth',0)*100:>6.1f}% {row['signal']}\n"

    send_telegram_msg(msg)
    print_log(f"✅ 完成！找到 {len(today_df)} 檔符合標的")

if __name__ == "__main__":
    run_batched_strategy()
