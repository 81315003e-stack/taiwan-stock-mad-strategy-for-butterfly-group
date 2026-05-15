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
        print_log("❌ Telegram Token 或 Chat_ID 未設定！")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            print_log("✅ Telegram 訊息發送成功")
        else:
            print_log(f"❌ Telegram 發送失敗 ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        print_log(f"❌ Telegram 例外錯誤: {e}")

def run_batched_strategy():
    raw_start = os.getenv('SLICE_START')
    raw_end = os.getenv('SLICE_END')
    start_idx = int(raw_start) if raw_start and raw_start.strip() else 0
    end_idx = int(raw_end) if raw_end and raw_end.strip() else 300

    print_log(f"🚀 MAD + TTM EPS 穩定版啟動：{start_idx} ~ {end_idx}")

    dl = DataLoader()
    dl.login_by_token(api_token=os.getenv('FINMIND_API_TOKEN'))  # ← 加這行
    
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

    # ── 階段 1：技術面 MAD 篩選 ──────────────────────────────────────
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
        time.sleep(0.012)

    print_log(f"階段1 通過 {len(all_price_data)} 檔")
    if not all_price_data:
        return

    # ── 階段 2：基本面 TTM EPS 檢查 ──────────────────────────────────
    print_log(f"📡 階段 2：TTM EPS 檢查 ({len(all_price_data)} 檔)...")
    final_data_list = []

    for df in all_price_data:
        sid = df['stock_id'].iloc[0]
        try:
            fin_df = dl.taiwan_stock_financial_statement(stock_id=sid, start_date=fin_start)
            if fin_df.empty:
                continue

            eps_mask = fin_df['type'].astype(str).str.contains(
                'EPS|每股盈餘|每股|基本每股|稀釋每股', case=False, na=False
            )
            eps_df = fin_df[eps_mask].copy()

            if eps_df.empty:
                print_log(f"  SKIP {sid}: 無 EPS 欄位，type 有: {fin_df['type'].unique()[:5]}")
                continue

            eps_df['date'] = pd.to_datetime(eps_df['date'], errors='coerce')
            eps_df = eps_df.sort_values('date', ascending=True)
            eps_df['value'] = pd.to_numeric(eps_df['value'], errors='coerce')
            eps_values = eps_df['value'].dropna().values

            if len(eps_values) < 4:
                continue

            current_ttm = round(eps_values[-4:].sum(), 3)
            prev_ttm = round(eps_values[-8:-4].sum(), 3) if len(eps_values) >= 8 else None

            if current_ttm < 0.2:
                continue

            if prev_ttm is not None and prev_ttm > 0:
                ttm_growth = (current_ttm - prev_ttm) / prev_ttm
            else:
                ttm_growth = 0.0

            if current_ttm >= 0.1 and ttm_growth >= 0.0:
                df = df.copy()
                df['ttm_eps'] = current_ttm
                df['ttm_growth'] = round(ttm_growth, 4)
                final_data_list.append(df)

        except Exception as e:
            print_log(f"  ERR {sid}: {e}")
            continue
        time.sleep(0.07)

    print_log(f"基本面通過 {len(final_data_list)} 檔")
    if not final_data_list:
        print_log("⚠️ 無股票通過基本面")
        return

    # ── 階段 3：報告 ─────────────────────────────────────────────────
    full_df = pd.concat(final_data_list, ignore_index=True)
    full_df.columns = [c.lower() for c in full_df.columns]
    print_log(f"DEBUG full_df columns: {list(full_df.columns)}")

    full_df['date'] = pd.to_datetime(full_df['date'])        # ← 確保日期格式
    full_df = full_df.sort_values('date')                    # ← 確保排序正確

    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    print_log(f"DEBUG latest_date={latest_date}, today_df={len(today_df)} 檔")  # ← debug 在這裡

    if today_df.empty:
        print_log("⚠️ today_df 為空，無法產生報告")   # ← 縮排 8 格
        return                                         # ← 縮排 8 格

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

    # 發送 Telegram
    msg = f"*📊 MAD + TTM EPS 報告 ({latest_date})*\n"
    msg += f"分段：{start_idx}~{end_idx} | 找到 {len(today_df)} 檔\n---\n"
    msg += "代號 價格 TTM_EPS 成長% 訊號\n"

    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += f"`{row['stock_id']}` {row['close']:>5.1f} {row.get('ttm_eps', 0):>6.2f} "
        msg += f"{row.get('ttm_growth', 0) * 100:>5.1f}% {row['signal']}\n"

    print_log(f"準備發送 Telegram 訊息，長度: {len(msg)} 字元")
    send_telegram_msg(msg)
    print_log(f"✅ 完成！找到 {len(today_df)} 檔")

if __name__ == "__main__":
    run_batched_strategy()
