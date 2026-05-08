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
    end_idx = int(raw_end) if raw_end and raw_end.strip() else 200   # 先用小批次

    print_log(f"🚀 MAD + 基本面 強診斷版啟動：{start_idx} ~ {end_idx}")

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

    # 階段 2：強化診斷
    print_log(f"📡 階段 2：基本面檢查 ({len(all_price_data)} 檔)...")
    final_data_list = []
    stats = {"checked":0, "has_data":0, "has_eps":0, "pass":0}

    for idx, df in enumerate(all_price_data):
        sid = df['stock_id'].iloc[0]
        try:
            stats["checked"] += 1
            fin_df = dl.taiwan_stock_financial_statement(stock_id=sid, start_date=fin_start)
            if fin_df.empty:
                continue

            stats["has_data"] += 1

            # 顯示前幾檔的 type 幫助診斷
            if idx < 3:
                print_log(f"[{sid}] Columns: {fin_df.columns.tolist()}")
                if 'type' in fin_df.columns:
                    print_log(f"[{sid}] Types: {fin_df['type'].unique()[:15].tolist()}")

            # 抓 EPS（多種可能欄位名稱）
            eps_mask = fin_df['type'].astype(str).str.contains('EPS|盈餘|每股', case=False, na=False)
            eps_df = fin_df[eps_mask].copy()

            if eps_df.empty:
                continue
            stats["has_eps"] += 1

            eps_df['value'] = pd.to_numeric(eps_df['value'], errors='coerce')
            eps_values = eps_df['value'].dropna().values

            if len(eps_values) < 4:   # 放寬門檻
                continue

            current_ttm = eps_values[-4:].sum()
            prev_ttm = eps_values[-8:-4].sum() if len(eps_values) >= 8 else 0

            if current_ttm <= 0:
                continue

            ttm_growth = (current_ttm - prev_ttm) / prev_ttm if prev_ttm > 0 else 0.0

            # ROE
            roe_mask = fin_df['type'].astype(str).str.contains('ROE|權益報酬率', case=False, na=False)
            roe_df = fin_df[roe_mask].copy()
            roe_df['value'] = pd.to_numeric(roe_df['value'], errors='coerce')
            latest_roe = roe_df['value'].dropna().iloc[-1] if not roe_df['value'].dropna().empty else 0

            # 目前寬鬆門檻（先讓它通過）
            if current_ttm >= 1.0 and latest_roe >= 8:
                stats["pass"] += 1
                df = df.copy()
                df['ttm_eps'] = round(current_ttm, 3)
                df['ttm_growth'] = round(ttm_growth, 4)
                df['roe'] = round(latest_roe, 2)
                final_data_list.append(df)

        except Exception as e:
            continue
        time.sleep(0.07)

    print_log(f"TTM統計 → 已檢查:{stats['checked']} | 有財報:{stats['has_data']} | 有EPS:{stats['has_eps']} | 通過:{stats['pass']}")

    if not final_data_list:
        print_log("⚠️ 仍無符合標的，請把上面完整 Log（包含 type 資訊）貼給我")
        return

    # 報告部分
    full_df = pd.concat(final_data_list, ignore_index=True)
    full_df.columns = [c.lower() for c in full_df.columns]

    latest_date = full_df['date'].max()
    today_df = full_df[full_df['date'] == latest_date].copy()

    def get_signal(row):
        if row['close'] >= row.get('h20_max', 0):
            return "🔥 帶量突破"
        return "👀 趨勢向上"

    today_df['signal'] = today_df.apply(get_signal, axis=1)

    msg = f"*📊 MAD 基本面報告 ({latest_date})*\n"
    msg += f"找到 {len(today_df)} 檔 | TTM_EPS≥1.0 + ROE≥8%\n---\n"
    msg += "代號 價格 TTM_EPS 成長% ROE 訊號\n"

    for _, row in today_df.sort_values('mrat', ascending=False).iterrows():
        msg += f"`{row['stock_id']}` {row['close']:>5.1f} {row.get('ttm_eps',0):>6.2f} "
        msg += f"{row.get('ttm_growth',0)*100:>5.1f}% {row.get('roe',0):>4.1f} {row['signal']}\n"

    send_telegram_msg(msg)
    print_log(f"✅ 完成！找到 {len(today_df)} 檔")

if __name__ == "__main__":
    run_batched_strategy()
