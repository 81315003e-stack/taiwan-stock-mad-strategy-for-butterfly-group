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
    if not token or not chat_id: return
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
    end_idx = int(raw_end) if raw_end and raw_end.strip() else 200   # 先用小批次測試

    print_log(f"🚀 MAD + TTM EPS 寬鬆診斷版啟動：{start_idx} ~ {end_idx}")

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
    fin_start = (datetime.datetime.now() - datetime.timedelta(days=2000)).strftime('%Y-%m-%d')  # 拉更長

    all_price_data = []

    # === 階段 1：技術面（不變）===
    print_log("📡 階段 1：技術面 MAD 篩選...")
    for sid in target_stocks:
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=price_start, end_date=today)
            if df.empty or len(df) < 200: continue

            vol_col = next((c for c in df.columns if c.lower() in ['trading_volume', 'volume']), None)
            if not vol_col or df.iloc[-1][vol_col] < 500_000: continue

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

    # === 階段 2：TTM EPS（大幅放寬 + Log）===
    print_log(f"📡 階段 2：TTM EPS 檢查 ({len(all_price_data)} 檔)...")
    final_data_list = []
    stats = {"total": 0, "enough_data": 0, "positive_ttm": 0, "growth_ge_5": 0}

    for df in all_price_data:
        sid = df['stock_id'].iloc[0]
        try:
            fin_df = dl.taiwan_stock_financial_statement(stock_id=sid, start_date=fin_start)
            if fin_df.empty: continue

            eps_df = fin_df[fin_df['type'] == 'EPS'].copy()
            eps_df['value'] = pd.to_numeric(eps_df['value'], errors='coerce')
            eps_values = eps_df['value'].dropna().values

            stats["total"] += 1

            if len(eps_values) < 8:
                continue
            stats["enough_data"] += 1

            current_ttm = eps_values[-4:].sum()
            prev_ttm = eps_values[-8:-4].sum()

            if current_ttm <= 0:
                continue
            stats["positive_ttm"] += 1

            if prev_ttm > 0:
                ttm_growth = (current_ttm - prev_ttm) / prev_ttm
            else:
                ttm_growth = 0.0   # 前一年虧損，今年轉正也算好

            # === 極寬鬆條件（先讓它跑得動）===
            if ttm_growth >= 0.05 or current_ttm >= 1.5:   # 成長5% 或 TTM EPS 夠高
                stats["growth_ge_5"] += 1
                df = df.copy()
                df['ttm_eps'] = round(current_ttm, 3)
                df['ttm_growth'] = round(ttm_growth, 4)
                final_data_list.append(df)

        except:
            continue
        time.sleep(0.07)

    print_log(f"TTM 統計 → 有足夠資料:{stats['enough_data']} | 正 TTM:{stats['positive_ttm']} | 通過:{stats['growth_ge_5']}")

    if not final_data_list:
        print_log("⚠️ 即使放寬仍無標的，請再告訴我統計數字，我繼續放寬")
        return

    # === 階段 3：產生報告 ===
    full_df = pd.concat(final_data_list, ignore_index=True)
    full_df.columns = [c.lower() for c in full_df.columns]

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()

    msg = f"*📊 MAD + TTM EPS 寬鬆報告 ({latest_date})*\n"
    msg += f"分段：{start_idx}~{end_idx} | TTM成長≥5% 或 TTM_EPS≥1.5\n---\n"
    msg += "代號 價格 TTM_EPS 成長% MRAT\n"

    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += f"`{row['stock_id']}` {row['close']:>5.1f} {row.get('ttm_eps',0):>6.2f} {row.get('ttm_growth',0)*100:>6.1f}% {row.get('mrat',0):.3f}\n"

    send_telegram_msg(msg)
    print_log(f"✅ 完成！找到 {len(today_df)} 檔符合標的")

if __name__ == "__main__":
    run_batched_strategy()
