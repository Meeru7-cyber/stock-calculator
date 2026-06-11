import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from pykrx import stock
from datetime import datetime, timedelta
import math

# 1. 페이지 및 상단 UI 설정
st.set_page_config(page_title="고급 가치투자 계산기", layout="wide")
st.title("📊 가치투자 기대수익률(R) 계산기")
st.markdown("---")

# 2. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 분석 설정")
    ticker_input = st.text_input("종목 입력 (한국은 6자리 숫자, 미국은 영문)", "005930").strip()
    n_years = st.number_input("투자기간 N (년)", min_value=1, value=10, step=1)
    
    st.markdown("---")
    st.markdown("### 📝 수동 데이터 입력 (비상용)")
    manual_override = st.checkbox("수동 모드 활성화")
    manual_price = st.number_input("현재 주가", value=0)
    manual_bps = st.number_input("BPS (주당순자산)", value=0)
    manual_roe_current = st.number_input("현재 분기 ROE (%)", value=0.0, step=0.1)
    manual_roe_5y = st.number_input("5년 평균 ROE (%)", value=0.0, step=0.1)

# 데이터 정제용 안전 함수
def to_float(val):
    try:
        v = str(val).replace(',', '').strip()
        if not v or v in ['-', 'N/A', '']: return None
        return float(v)
    except:
        return None

# 3. 데이터 통합 크롤링 엔진 (이중화 처리)
def get_clean_data(ticker_code):
    price, bps, roe_current, roe_5y, corp_name = None, None, None, None, ticker_code
    
    # [A] 한국 주식 (네이버 금융 + pykrx 백업)
    if ticker_code.isdigit() and len(ticker_code) == 6:
        # 1차 시도: 네이버 금융 (우회 접속)
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
            }
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            name_tag = soup.select_once('.wrap_company h2 a')
            if name_tag: corp_name = name_tag.text
            
            price_tag = soup.select_once('.no_today .blind')
            if price_tag: price = to_float(price_tag.text)
            
            table = soup.select_once('table.tb_type1_ifrs')
            if table:
                for row in table.select('tbody tr'):
                    th = row.select_once('th')
                    if not th: continue
                    title = th.text.strip()
                    tds = row.select('td')
                    vals = [to_float(td.text) for td in tds]
                    
                    if title == 'ROE(%)':
                        roes_annual = [v for v in vals[:4] if v is not None]
                        roes_quarter = [v for v in vals[4:] if v is not None]
                        if roes_quarter: roe_current = roes_quarter[-1]
                        elif roes_annual: roe_current = roes_annual[-1]
                        if roes_annual: roe_5y = sum(roes_annual) / len(roes_annual)
                    elif title == 'BPS(원)':
                        for v in reversed(vals):
                            if v is not None:
                                bps = v
                                break
        except Exception:
            pass # 네이버 차단 시 백업 엔진으로 자동 진입
            
        # 2차 시도: pykrx (한국거래소 공식 데이터 백업)
        if None in (price, bps, roe_current, roe_5y):
            today = datetime.today()
            if corp_name == ticker_code:
                corp_name = stock.get_market_ticker_name(ticker_code)
                
            for i in range(5):
                t_date = (today - timedelta(days=i)).strftime("%Y%m%d")
                df_f = stock.get_market_fundamental(t_date, t_date, ticker_code)
                df_o = stock.get_market_ohlcv_by_date(t_date, t_date, ticker_code)
                
                if not df_f.empty and not df_o.empty and df_f['PBR'].iloc[0] > 0:
                    if price is None: price = df_o['종가'].iloc[0]
                    if bps is None: bps = df_f['BPS'].iloc[0]
                    
                    pbr = df_f['PBR'].iloc[0]
                    per = df_f['PER'].iloc[0]
                    if roe_current is None and per > 0:
                        roe_current = (pbr / per) * 100
                    break
                    
            if roe_5y is None:
                start_date = (today - timedelta(days=5*365)).strftime("%Y%m%d")
                df_hist = stock.get_market_fundamental_by_date(start_date, today.strftime("%Y%m%d"), ticker_code, freq="Y")
                if not df_hist.empty:
                    df_hist['ROE'] = df_hist.apply(lambda row: (row['PBR'] / row['PER'] * 100) if row['PER'] > 0 else None, axis=1)
                    valid_roes = df_hist['ROE'].dropna()
                    if not valid_roes.empty: roe_5y = valid_roes.mean()
                    else: roe_5y = roe_current

        return price, bps, roe_current, roe_5y, corp_name

    # [B] 미국 주식 (yfinance)
    else:
        stock_yf = yf.Ticker(ticker_code)
        info = stock_yf.info
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        bps = info.get('bookValue')
        if bps is None and price is not None and info.get('priceToBook'):
            bps = price / info.get('priceToBook')
            
        roe_current = info.get('returnOnEquity')
        if roe_current: roe_current *= 100
            
        roe_5y = None
        try:
            fin = stock_yf.financials
            bs = stock_yf.balance_sheet
            roe_list = []
            if not fin.empty and not bs.empty:
                ni_row = next((fin.loc[k] for k in ['Net Income', 'Net Income Common Stockholders'] if k in fin.index), None)
                eq_row = next((bs.loc[k] for k in ['Stockholders Equity', 'Total Stockholder Equity'] if k in bs.index), None)
                if ni_row is not None and eq_row is not None:
                    common_cols = fin.columns.intersection(bs.columns)
                    for col in common_cols:
                        if pd.notna(ni_row[col]) and pd.notna(eq_row[col]) and eq_row[col] != 0:
                            roe_list.append((ni_row[col] / eq_row[col]) * 100)
            if roe_list: roe_5y = sum(roe_list[:5]) / len(roe_list[:5])
        except: pass
        if roe_5y is None: roe_5y = roe_current
        
        return price, bps, roe_current, roe_5y, info.get('longName', ticker_code)

# 4. 분석 실행 파트
with st.spinner("데이터를 분석 중입니다..."):
    if manual_override:
        price = manual_price if manual_price > 0 else None
        bps = manual_bps if manual_bps > 0 else None
        roe_current = manual_roe_current if manual_roe_current > 0 else None
        roe_5y = manual_roe_5y if manual_roe_5y > 0 else None
        corp_name = f"수동 입력 데이터 ({ticker_input})"
    else:
        if ticker_input:
            try:
                price, bps, roe_current, roe_5y, corp_name = get_clean_data(ticker_input)
            except Exception as e:
                st.error(f"데이터 크롤링 에러 발생. 수동 모드를 이용해주세요. (상세에러: {e})")

# 5. 시뮬레이션 결과 출력
if price and bps:
    st.header(f"🏢 {corp_name} 분석 결과")
    
    col1, col2, col3 = st.columns(3)
    unit = "원" if ticker_input.isdigit() else "$"
    
    col1.metric("현재 주가", f"{price:,.0f}{unit}" if unit=="원" else f"{unit}{price:,.2f}")
    col2.metric("BPS (주당순자산)", f"{bps:,.0f}{unit}" if unit=="원" else f"{unit}{bps:,.2f}")
    col3.metric("현재 PBR", f"{price/bps:.2f}배" if bps > 0 else "N/A")
    
    st.markdown("### ⚖️ 시나리오별 기대수익률 및 15% 목표 매수가")
    
    scenarios = []
    if roe_current is not None: scenarios.append(("현재 (최근 분기) ROE", roe_current))
    if roe_5y is not None: scenarios.append(("과거 연간 평균 ROE", roe_5y))
    
    if not scenarios:
        st.warning("ROE 데이터가 없습니다. 수동 모드를 이용해주세요.")
    else:
        res_list = []
        for title, roe_val in scenarios:
            r_dec = roe_val / 100
            future_value = bps * ((1 + r_dec) ** n_years)
            multiplier = future_value / price if price > 0 else 0
            exp_return = (10 ** (math.log10(multiplier) / n_years)) - 1 if multiplier > 0 else 0
            target_buy = bps * (((1 + r_dec) / 1.15) ** n_years)
            
            res_list.append({
                "기준 시나리오": title,
                "적용 ROE": f"{roe_val:.2f}%",
                f"{n_years}년 후 가치": f"{future_value:,.0f}{unit}" if unit=="원" else f"{unit}{future_value:,.2f}",
                "10년 가치 승수": f"{multiplier:.2f}배",
                "예상 기대수익률": f"{exp_return*100:.2f}%",
                "15% 달성 매수가": f"{target_buy:,.0f}{unit}" if unit=="원" else f"{unit}{target_buy:,.2f}"
            })
            
        st.table(pd.DataFrame(res_list).set_index("기준 시나리오"))
