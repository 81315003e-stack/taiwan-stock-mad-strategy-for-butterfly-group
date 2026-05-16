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
        print_log("❌ Telegram Token 或 Chat_ID 未設定！")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}

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
    dl.login_by_token(api_token=os.getenv('FINMIND_API_TOKEN'))

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
            if not vol_col or df.iloc[-1][vol_col] < 1000000:
                continue

            df['ma21'] = df['close'].rolling(21).mean()
            df['ma200'] = df['close'].rolling(200).mean()
            df['mrat'] = df['ma21'] / df['ma200']

            if df['mrat'].iloc[-1] > 1.05:
                df = df.copy()
                df['stock_id'] = sid
                all_price_data.append(df)
        except Exception as e:
            print_log(f"  ERR 價格 {sid}: {e}")
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

            # 嚴格基本面條件
            if current_ttm >= 1.0 and ttm_growth >= 0.10:
                df = df.copy()
                df['ttm_eps'] = current_ttm
                df['ttm_growth'] = round(ttm_growth, 4)
                final_data_list.append(df)

        except Exception as e:
            print_log(f"  ERR 財報 {sid}: {e}")
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

    full_df['date'] = pd.to_datetime(full_df['date'])
    full_df = full_df.sort_values('date')

    full_df['h20_max'] = full_df.groupby('stock_id')['max'].transform(lambda x: x.rolling(20).max())
    full_df['daily_amp'] = full_df['max'] - full_df['min']
    full_df['amp5_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.rolling(5).max())
    full_df['amp6_15_max'] = full_df.groupby('stock_id')['daily_amp'].transform(lambda x: x.shift(5).rolling(10).max())

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()
    print_log(f"DEBUG latest_date={latest_date}, today_df={len(today_df)} 檔")

    if today_df.empty:
        print_log("⚠️ today_df 為空，無法產生報告")
        return

    # 技術與風險欄位
    today_df['ma21_dist'] = (today_df['close'] - today_df['ma21']) / today_df['ma21']
    today_df['ma200_dist'] = (today_df['close'] - today_df['ma200']) / today_df['ma200']

    today_df['stop_price'] = today_df['ma21'] * 0.97
    today_df['target_price'] = today_df['h20_max'] * 1.05

    denom = today_df['close'] - today_df['stop_price']
    today_df['rr_ratio'] = np.where(denom > 0, (today_df['target_price'] - today_df['close']) / denom, np.nan)

    today_df['entry_low'] = today_df['ma21'] * 0.99
    today_df['entry_high'] = today_df['ma21'] * 1.02

    def get_signal(row):
        if row['close'] >= row.get('h20_max', 0):
            return "🔥 帶量突破"
        if 0 <= row.get('ma21_dist', 0) <= 0.03:
            return "🛡️ 回測支撐"
        if row.get('amp5_max', 0) < row.get('amp6_15_max', 999):
            return "⌛ 蓄勢待發"
        return "👀 趨勢向上"

    def get_comment(row):
        good_fund = row.get('ttm_eps', 0) >= 5 and row.get('ttm_growth', 0) >= 0.30
        dist = row.get('ma21_dist', 0)
        rr = row.get('rr_ratio', np.nan)

        hot = dist > 0.08
        near_support = 0 <= dist <= 0.03
        below_ma21 = dist < 0

        if good_fund and near_support:
            return "📌 多頭關注：基本面佳，靠近 MA21，可考慮分批佈局"
        if good_fund and hot:
            return "⚠️ 基本面佳但價位偏熱，建議等待拉回接近 MA21 再進場"
        if below_ma21:
            return "⚠️ 價格跌破 MA21，短線結構轉弱，偏向觀望或減碼"
        if not np.isnan(rr) and rr < 1.0:
            return "⚠️ 風險報酬不佳（RR<1），不建議追價"
        return "👀 結構多頭，但需搭配風險承受度評估進場時機"

    today_df['signal'] = today_df.apply(get_signal, axis=1)
    today_df['comment'] = today_df.apply(get_comment, axis=1)

    # 發送 Telegram
    date_str = str(latest_date.date())
    msg = "=== MAD + TTM EPS " + date_str + " ===\n"
    msg += f"分段：{start_idx}~{end_idx} | 找到 {len(today_df)} 檔\n---\n"
    msg += "代號 價格 TTM_EPS 成長% 入場區間 RR 訊號 說明\n"
"
    msg += f"分段：{start_idx}~{end_idx} | 找到 {len(today_df)} 檔
---
"
    msg += "代號 價格 TTM_EPS 成長% 入場區間 RR 訊號 說明
"

    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += (
            f"{row['stock_id']:>6} {row['close']:>7.1f} "
            f"{row.get('ttm_eps', 0):>7.2f} {row.get('ttm_growth', 0) * 100:>6.1f}% "
            f"[{row['entry_low']:.1f}-{row['entry_high']:.1f}] "
            f"RR={row['rr_ratio']:.1f} {row['signal']} {row['comment']}
"
        )

    print_log(f"準備發送 Telegram 訊息，長度: {len(msg)} 字元")
    send_telegram_msg(msg)
    print_log(f"✅ 完成！找到 {len(today_df)} 檔")


if __name__ == "__main__":
    run_batched_strategy()
