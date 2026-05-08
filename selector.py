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

    print_log(f"🚀 MAD + TTM EPS + ROE 版啟動：{start_idx} ~ {end_idx}")

    dl = DataLoader()

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
    fin_start = (datetime.datetime.now() - datetime.timedelta(days=2000)).strftime('%Y-%m-%d')

    all_price_data = []

    # 階段 1：技術面
    print_log("📡 階段 1：技術面 MAD 篩選...")
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=price_start, end_date=today)
            if df.empty or len(df) < 200:
                continue

            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            if not vol_col or df.iloc[-1][vol_col] < 500000:
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

    print_log(f"階段1 通過 {len(all_price_data)} 檔")
    if not all_price_data:
        print_log("⚠️ 無動能標的")
        return

    # 階段 2：TTM EPS + ROE
    print_log(f"📡 階段 2：TTM EPS + ROE 檢查 ({len(all_price_data)} 檔)...")
    final_data_list = []
    stats = {"enough": 0, "pass": 0}

    for df in all_price_data:
        sid = df['stock_id'].iloc[0]
        try:
            fin_df = dl.taiwan_stock_financial_statement(stock_id=sid, start_date=fin_start)
            if fin_df.empty:
                continue

            # EPS
            eps_df = fin_df[fin_df['type'] == 'EPS'].copy()
            eps_df['value'] = pd.to_numeric(eps_df['value'], errors='coerce')
            eps_values = eps_df['value'].dropna().values

            if len(eps_values) < 8:
                continue
            stats["enough"] += 1

            current_ttm = eps_values[-4:].sum()
            prev_ttm = eps_values[-8:-4].sum() if len(eps_values) >= 8 else 0

            if current_ttm <= 0:
                continue

            ttm_growth = (current_ttm - prev_ttm) / prev_ttm if prev_ttm > 0 else 0.0

            # ROE
            roe_df = fin_df[fin_df['type'] == 'ROE'].copy()
            roe_df['value'] = pd.to_numeric(roe_df['value'], errors='coerce')
            latest_roe = roe_df['value'].dropna().iloc[-1] if not roe_df['value'].dropna().empty else 0

            # 門檻設定（目前中高門檻）
            if (ttm_growth >= 0.15 or current_ttm >= 2.5) and latest_roe >= 12 and current_ttm >= 1.0:
                stats["pass"] += 1
                df = df.copy()
                df['ttm_eps'] = round(current_ttm, 3)
                df['ttm_growth'] = round(ttm_growth, 4)
                df['roe'] = round(latest_roe, 2)
                final_data_list.append(df)

        except:
            continue
        time.sleep(0.08)

    print_log(f"TTM統計 → 有資料:{stats['enough']} | 通過:{stats['pass']}")

    if not final_data_list:
        print_log("⚠️ 本批次無符合標的")
        return

    # 階段 3：技術指標與訊號
    full_df = pd.concat(final_data_list, ignore_index=True)
    full_df.columns = [c.lower() for c in full_df.columns]

    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()

    today_df['ma21_dist'] = (today_df['close'] - today_df['ma21']) / today_df['ma
