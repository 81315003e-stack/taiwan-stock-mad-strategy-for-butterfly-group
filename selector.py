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
    end_idx = int(raw_end) if raw_end and raw_end.strip() else 200

    print_log(f"🚀 MAD + TTM EPS 診斷寬鬆版啟動：{start_idx} ~ {end_idx}")

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

    print_log("📡 階段 1：技術面 MAD 篩選...")
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=price_start, end_date=today)
            if df.empty or len(df) < 200: continue
            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            if not vol_col or df.iloc[-1][vol_col] < 500000: continue

            df['ma21'] = df['close'].rolling(21).mean()
            df['ma200'] = df['close'].rolling(200).mean()
            df['mrat'] = df['ma21'] / df['ma200']

            if df['mrat'].iloc[-1] > 1.0:
                df = df.copy()
                df['stock_id'] = sid
                all_price_data.append(df)
        except:
            continue
        time.sleep(0.012)

    print_log(f"階段1 通過 {len(all_price_data)} 檔")
    if not all_price_data:
        return

    # 階段 2：寬鬆版 + 印出實際數值
    print_log(f"📡 階段 2：TTM EPS 檢查 ({len(all_price_data)} 檔)...")
    final_data_list = []

    for df in all_price_data:
        sid = df['stock_id'].iloc[0]
        try:
            fin_df = dl.taiwan_stock_financial_statement(stock_id=sid, start_date=fin_start)
            if fin_df.empty: continue

            eps_mask = fin_df['type'].astype(str).str.contains('EPS|盈餘|每股', case=False, na=False)
            eps_df = fin_df[eps_mask].copy()
            if eps_df.empty: continue

            eps_df['value'] = pd.to_numeric(eps_df['value'], errors='coerce')
            eps_values = eps_df['value'].dropna().values
            if len(eps_values) < 4: continue

            current_ttm = round(eps_values[-4:].sum(), 3)
            prev_ttm = round(eps_values[-8:-4].sum(), 3) if len(eps_values) >= 8 else 0
            ttm_growth = (current_ttm - prev_ttm) / prev_ttm if prev_ttm > 0 else 0.0

            print_log(f"[{sid}] TTM_EPS = {current_ttm:.2f} | 成長率 = {ttm_growth*100:6.1f}%")

            # 目前寬鬆門檻（先讓它有輸出）
            if current_ttm >= 0.8 or ttm_growth >= 0.05:   # 可再調整
                df = df.copy()
                df['ttm_eps'] = current_ttm
                df['ttm_growth'] = round(ttm_growth, 4)
                final_data_list.append(df)

        except:
            continue
        time.sleep(0.07)

    print_log(f"最終通過 {len(final_data_list)} 檔")

    if not final_data_list:
        print_log("⚠️ 仍無通過")
        return

    # 報告部分（含蓄勢待發）
    full_df = pd.concat(final_data_list, ignore_index=True)
    full_df.columns = [c.lower() for c in full_df.columns]

    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()

    today_df['ma21_dist'] = (today_df['close'] - today_df['ma21']) / today_df['ma21']

    def get_signal(row):
        if row['close'] >= row.get('h20_max', 0):
            return "🔥 帶量突破"
        if 0 <= row.get('ma21_dist', 0) <= 0.03:
            return "🛡️ 回測支撐"
        if row.get('amp5_max', 0) < row.get('amp6_15_max', 999):
            return "⌛ 蓄勢待發"
        return "👀 趨勢向上"

    today_df['signal'] = today_df.apply(get_signal, axis=1)

    msg = f"*📊 MAD + TTM EPS 報告 ({latest_date})*\n"
    msg += f"分段：{start_idx}~{end_idx} | 找到 {len(today_df)} 檔\n---\n"
    msg += "代號 價格 TTM_EPS 成長% 訊號\n"

    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += f"`{row['stock_id']}` {row['close']:>5.1f} {row.get('ttm_eps',0):>6.2f} "
        msg += f"{row.get('ttm_growth',0)*100:>5.1f}% {row['signal']}\n"

    send_telegram_msg(msg)
    print_log(f"✅ 完成！找到 {len(today_df)} 檔")

if __name__ == "__main__":
    run_batched_strategy()
