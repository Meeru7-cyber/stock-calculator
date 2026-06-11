import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import math

# 1. 페이지 및 상단 UI 설정
st.set_page_config(page_title="고급 가치투자 기대수익률 계산기", layout="wide")

st.title("📊 가치투자 기대수익률(R) 계산기 (네이버금융 연동)")
st.markdown("""
**[핵심 가치투자 산식]**
- **10년 후 가치** = $BPS \\times (1 + ROE)^{10}$
- **10년 가치 승수** = $\\frac{\\text{10년 후 가치}}{\\text{현재 주가}}$
- **기대수익률(R)** = $10^{\\frac{\\log_{10}(\\text{10년 가치 승수})}{10}} - 1$
- **목표 매수가격** = 기대수익률 **15%**를 확보할 수 있는 안전마진 가격
""")
st.markdown("---")

# 2. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 분석 설정")
    ticker_input = st.text_input("종목 입력 (한국은 6자리 숫자, 미국은 영문 티커)", "005930").strip()
    n_years = st.number_input("투자기간 N (년)", min_value=1, value=10, step=1)
    
    st.markdown("---")
    st.markdown("### 📝 수동 데이터 입력 (비상용)")
    st.caption("크롤링이 실패할 경우 직접 입력하여 계산할 수 있습니다.")
    manual_override = st.checkbox("수동 모드 활성화")
    manual_price = st.number_input("현재 주가", value=0)
    manual_bps = st.number_input("BPS (주당순자산)", value=0)
    manual_roe_current = st.number_input("현재 분기 ROE (%)", value=0.0, step=0.1)
    manual_roe_5y = st.number_input("평균 ROE (%)", value=0.0, step=0.1)

# 문자열을 숫자로 안전하게 변환하는 보조 함수
def to_float(val):
    try:
        return float(val)
    except:
        return None

# 3. 데이터 크롤링 함수 (네이버 금융 + 야후 파이낸스)
def get_clean_data(ticker_code):
    # A. 한국 주식 (네이버 금융 실시간 크롤링)
    if ticker_code.isdigit() and len(ticker_code) == 6:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 종목명 및 현재가
        name_tag = soup.select_once('.wrap_company h2 a')
        corp_name = name_tag.text if name_tag else ticker_code
        
        price_tag = soup.select_once('.no_today .blind')
        price = int(price_tag.text.replace(',', '')) if price_tag else None
        
        bps, roe_current, roe_5y = None, None, None
        
        # 기업실적분석 테이블 분석
        table = soup.select_once('table.tb_type1_ifrs')
        if table:
            rows = table.select('tbody tr')
            for row in rows:
                th = row.select_once('th')
                if not th: continue
                title = th.text.strip()
                
                tds = row.select('td')
                vals = [td.text.strip().replace(',', '') for td in tds]
                
                # ROE 추출 로직 (보통 앞 4개가 연간, 뒤 6개가 분기)
                if title == 'ROE(%)':
                    roes_annual = [to_float(v) for v in vals[:4] if to_float(v) is not None]
                    roes_quarter = [to_float(v) for v in vals[4:] if to_float(v) is not None]
                    
                    if roes_quarter:
                        roe_current = roes_quarter[-1]
                    elif roes_annual:
                        roe_current = roes_annual[-1]
                        
                    if roes_annual:
                        roe_5y = sum(roes_annual) / len(roes_annual)
                        
                # BPS 추출 로직 (가장 최근 값)
                elif title == 'BPS(원)':
                    for v in reversed(vals):
                        bps_val = to_float(v)
                        if bps_val is not None:
                            bps = bps_val
                            break
                            
        return price, bps, roe_current, roe_5y, corp_name

    # B. 미국 및 해외 주식 (야후 파이낸스)
    else:
        stock_yf = yf.Ticker(ticker_code)
        info = stock_yf.info
        
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        bps = info.get('bookValue')
        if bps is None and price is not None and info.get('priceToBook') is not None:
            bps = price / info.get('priceToBook')
            
        roe_current = info.get('returnOnEquity')
        if roe_current is not None: roe_current = roe_current * 100
            
        roe_5y = None
        try:
            fin = stock_yf.financials
            bs = stock_yf.balance_sheet
            roe_list = []
            if not fin.empty and not bs.empty:
                ni_keys = ['Net Income', 'Net Income Common Stockholders']
                eq_keys = ['Stockholders Equity', 'Total Stockholder Equity']
                ni_row = next((fin.loc[k] for k in ni_keys if k in fin.index), None)
                eq_row = next((bs.loc[k] for k in eq_keys if k in bs.index), None)
                
                if ni_row is not None and eq_row is not None:
                    common_cols = fin.columns.intersection(bs.columns)
                    for col in common_cols:
                        if pd.notna(ni_row[col]) and pd.notna(eq_row[col]) and eq_row[col] != 0:
                            roe_list.append((ni_row[col] / eq_row[col]) * 100)
            if roe_list: roe_5y = sum(roe_list[:5]) / len(roe_list[:5])
        except:
            pass
            
        if roe_5y is None: roe_5y = roe_current
        return price, bps, roe_current, roe_5y, info.get('longName', ticker_code)

# 4. 데이터 엔진 구동
price, bps, roe_current, roe_5y, corp_name = None, None, None, None, ticker_input

if manual_override:
    price = manual_price if manual_price > 0 else None
    bps = manual_bps if manual_bps > 0 else None
    roe_current = manual_roe_current if manual_roe_current > 0 else None
    roe_5y = manual_roe_5y if manual_roe_5y > 0 else None
    corp_name = f"수동 입력 ({ticker_input})"
else:
    if ticker_input:
        try:
            price, bps, roe_current, roe_5y, corp_name = get_clean_data(ticker_input)
        except Exception as e:
            st.error("데이터 크롤링에 실패했습니다. 수동 모드를 이용해 주세요.")

# 5. 결과 시뮬레이션 및 시각화
if price and bps:
    st.header(f"🏢 {corp_name} 투자 분석 결과")
    
    m_col1, m_col2, m_col3 = st.columns(3)
    is_kr = ticker_input.isdigit()
    unit = "원" if is_kr else "$"
    
    m_col1.metric("현재 주가", f"{price:,.0f}{unit}" if is_kr else f"{unit}{price:,.2f}")
    m_col2.metric("BPS (주당순자산)", f"{bps:,.0f}{unit}" if is_kr else f"{unit}{bps:,.2f}")
    m_col3.metric("현재 PBR", f"{price/bps:.2f}배" if bps > 0 else "N/A")
    
    st.markdown("### ⚖️ 시나리오별 기대수익률 및 15% 적정 매수가격")
    
    scenarios = []
    if roe_current is not None: scenarios.append(("현재 (최근 분기) ROE", roe_current))
    if roe_5y is not None: scenarios.append(("과거 연간 평균 ROE", roe_5y))
    
    if not scenarios:
        st.warning("ROE 데이터가 없습니다. 사이드바에서 수동으로 입력해 주세요.")
    else:
        res_list = []
        for title, roe_val in scenarios:
            r_dec = roe_val / 100
            
            future_value = bps * ((1 + r_dec) ** n_years)
            multiplier = future_value / price if price > 0 else 0
            
            if multiplier > 0:
                exp_return = (10 ** (math.log10(multiplier) / n_years)) - 1
            else:
                exp_return = 0
                
            target_buy_price = bps * (((1 + r_dec) / 1.15) ** n_years)
            
            res_list.append({
                "기준 시나리오": title,
                "적용 ROE": f"{roe_val:.2f}%",
                f"{n_years}년 후 가치": f"{future_value:,.0f}{unit}" if is_kr else f"{unit}{future_value:,.2f}",
                "10년 가치 승수": f"{multiplier:.2f}배",
                "예상 기대수익률": f"{exp_return*100:.2f}%",
                "15% 달성 매수가": f"{target_buy_price:,.0f}{unit}" if is_kr else f"{unit}{target_buy_price:,.2f}"
            })
            
        st.table(pd.DataFrame(res_list).set_index("기준 시나리오"))
        
        # 6. 리스크 리포트
        st.markdown("---")
        st.markdown("### 🚨 리스크 점검 요약")
        
        base_roe = roe_5y if roe_5y is not None else roe_current
        pbr_val = price / bps if bps > 0 else 0
        
        r_dec_base = base_roe / 100
        f_val_base = bps * ((1 + r_dec_base) ** n_years)
        base_exp_return = (10 ** (math.log10(f_val_base / price) / n_years)) - 1 if price > 0 and f_val_base > 0 else 0
        
        risks = []
        if base_exp_return < 0.15:
            risks.append(f"현재 주가 기준 기대수익률({base_exp_return*100:.2f}%)이 목표치 15%에 미달합니다. 주가 하락 시 분할 매수를 고려하세요.")
        if pbr_val > 3.0:
            risks.append(f"현재 PBR이 {pbr_val:.2f}배로, 자산가치 대비 프리미엄이 높게 형성되어 있습니다.")
        if roe_5y is not None and roe_current is not None and roe_current < roe_5y * 0.8:
            risks.append(f"최근 ROE({roe_current:.2f}%)가 평균치({roe_5y:.2f}%) 대비 급감했습니다. 실적 둔화 여부 확인이 필요합니다.")
        if base_roe < 10.0:
            risks.append(f"수익성 지표인 ROE가 {base_roe:.2f}%로 10% 미만입니다. 복리 효과가 다소 떨어질 수 있습니다.")
            
        if risks:
            for risk in risks:
                st.warning(f"• {risk}")
        else:
            st.success("🎉 현재 주요 가치 평가 지표 상 우려되는 리스크 징후가 없습니다.")
else:
    st.info("왼쪽 사이드바에 분석할 종목 코드를 입력해 주세요.")
