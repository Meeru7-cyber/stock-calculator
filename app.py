import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import math

# 1. 페이지 설정
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

# 문자열 변환 안전 함수
def to_float(val):
    try:
        v = str(val).replace(',', '').strip()
        if not v or v in ['-', 'N/A', '']: return None
        return float(v)
    except:
        return None

# 3. 데이터 크롤링 핵심 엔진
def get_clean_data(ticker_code):
    p, b, r_c, r_5, c_name = None, None, None, None, ticker_code
    
    # [A] 한국 주식 (순수 네이버 금융 크롤링)
    if ticker_code.isdigit() and len(ticker_code) == 6:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        name_tag = soup.select_once('.wrap_company h2 a')
        if name_tag: c_name = name_tag.text
        
        price_tag = soup.select_once('.no_today .blind')
        if price_tag: p = to_float(price_tag.text)
        
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
                    if roes_quarter: r_c = roes_quarter[-1]
                    elif roes_annual: r_c = roes_annual[-1]
                    if roes_annual: r_5 = sum(roes_annual) / len(roes_annual)
                elif title == 'BPS(원)':
                    for v in reversed(vals):
                        if v is not None:
                            b = v
                            break
                            
        return p, b, r_c, r_5, c_name

    # [B] 미국 주식 (야후 파이낸스)
    else:
        stock_yf = yf.Ticker(ticker_code)
        info = stock_yf.info
        p = info.get('currentPrice') or info.get('regularMarketPrice')
        b = info.get('bookValue')
        if b is None and p is not None and info.get('priceToBook'):
            b = p / info.get('priceToBook')
            
        r_c = info.get('returnOnEquity')
        if r_c: r_c *= 100
            
        r_5 = None
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
            if roe_list: r_5 = sum(roe_list[:5]) / len(roe_list[:5])
        except: pass
        if r_5 is None: r_5 = r_c
        
        return p, b, r_c, r_5, info.get('longName', ticker_code)

# ==========================================
# 4. 분석 실행 (💡 여기가 핵심 수정 부분입니다!)
# 사전에 빈 상자를 만들어두어 에러를 방지합니다.
# ==========================================
price, bps, roe_current, roe_5y, corp_name = None, None, None, None, ticker_input

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
                st.warning("네이버 금융 보안망에 의해 자동 수집이 차단되었습니다. 왼쪽 사이드바의 '수동 모드 활성화'를 체크하고 직접 입력해 주세요.")

# 5. 결과 대시보드
if price is not None and bps is not None:
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
