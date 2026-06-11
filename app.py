import streamlit as st
import pandas as pd
import yfinance as yf
from pykrx import stock
from datetime import datetime, timedelta
import math

# 1. 페이지 및 상단 UI 설정
st.set_page_config(page_title="국내/해외 통합 기대수익률 계산기", layout="wide")

st.title("📊 국내/해외 통합 기대수익률(R) 계산기")
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
    st.markdown("### 📝 데이터 직접 입력 (비상용)")
    st.caption("시스템 오류로 데이터가 안 불러와질 때만 활성화하세요.")
    manual_override = st.checkbox("수동 입력 모드 활성화")
    manual_price = st.number_input("현재 주가", value=0)
    manual_bps = st.number_input("BPS (주당순자산)", value=0)
    manual_roe_current = st.number_input("현재 분기 ROE (%)", value=0.0, step=0.1)
    manual_roe_5y = st.number_input("5년 평균 ROE (%)", value=0.0, step=0.1)

# 3. 데이터 통합 크롤링 함수 (한국/미국 분기 처리)
def get_clean_data(ticker_code):
    # A. 한국 주식 처리 (6자리 숫자 패턴)
    if ticker_code.isdigit() and len(ticker_code) == 6:
        today = datetime.today()
        current_price, current_pbr, current_roe, current_bps = None, None, None, None
        
        # 최근 영업일 기준 현재가 및 기본 펀더멘털 추출
        for i in range(5):
            t_date = (today - timedelta(days=i)).strftime("%Y%m%d")
            df_f = stock.get_market_fundamental(t_date, t_date, ticker_code)
            df_o = stock.get_market_ohlcv_by_date(t_date, t_date, ticker_code)
            
            if not df_f.empty and not df_o.empty and df_f['PBR'].iloc[0] > 0:
                current_pbr = df_f['PBR'].iloc[0]
                per = df_f['PER'].iloc[0]
                current_roe = (current_pbr / per * 100) if per > 0 else None
                current_price = df_o['종가'].iloc[0]
                current_bps = df_f['BPS'].iloc[0]
                break
        
        # 과거 5개년 연간 데이터 기반 5년 평균 ROE 역산
        start_date = (today - timedelta(days=5*365)).strftime("%Y%m%d")
        end_date = today.strftime("%Y%m%d")
        df_hist = stock.get_market_fundamental_by_date(start_date, end_date, ticker_code, freq="Y")
        
        if not df_hist.empty:
            df_hist['ROE'] = df_hist.apply(lambda row: (row['PBR'] / row['PER'] * 100) if row['PER'] > 0 else None, axis=1)
            valid_roes = df_hist['ROE'].dropna()
            roe_5y = valid_roes.mean() if not valid_roes.empty else current_roe
        else:
            roe_5y = current_roe
            
        corp_name = stock.get_market_ticker_name(ticker_code)
        return current_price, current_bps, current_roe, roe_5y, corp_name

    # B. 미국 및 해외 주식 처리
    else:
        stock_yf = yf.Ticker(ticker_code)
        info = stock_yf.info
        
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        bps = info.get('bookValue')
        if bps is None and price is not None and info.get('priceToBook') is not None:
            bps = price / info.get('priceToBook')
            
        roe_current = info.get('returnOnEquity')
        if roe_current is not None:
            roe_current = roe_current * 100
            
        # 미국 주식 5년 평균 ROE 구하기
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
            if roe_list:
                roe_5y = sum(roe_list[:5]) / len(roe_list[:5])
        except:
            pass
            
        if roe_5y is None:
            roe_5y = roe_current
            
        return price, bps, roe_current, roe_5y, info.get('longName', ticker_code)

# 4. 데이터 엔진 구동
price, bps, roe_current, roe_5y, corp_name = None, None, None, None, ticker_input

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
            st.error(f"데이터를 불러오는 중 오류가 발생했습니다. 지속될 경우 수동 모드를 이용해 주세요.")

# 5. 시뮬레이션 및 결과 시각화
if price and bps:
    st.header(f"🏢 {corp_name} 투자 분석 결과")
    
    m_col1, m_col2, m_col3 = st.columns(3)
    is_kr = ticker_input.isdigit()
    unit = "원" if is_kr else "$"
    
    m_col1.metric("현재 주가", f"{price:,.0f}{unit}" if is_kr else f"{unit}{price:,.2f}")
    m_col2.metric("BPS (주당순자산)", f"{bps:,.0f}{unit}" if is_kr else f"{unit}{bps:,.2f}")
    m_col3.metric("현재 PBR", f"{price/bps:.2f}배")
    
    st.markdown("### ⚖️ 시나리오별 기대수익률 및 15% 적정 매수가격")
    
    scenarios = []
    if roe_current is not None: scenarios.append(("현재 분기 ROE 기준", roe_current))
    if roe_5y is not None: scenarios.append(("5년 평균 ROE 기준", roe_5y))
    
    if not scenarios:
        st.warning("ROE 데이터 추출에 실패했습니다. 왼쪽 사이드바에서 수동으로 입력해 주세요.")
    else:
        res_list = []
        for title, roe_val in scenarios:
            r_dec = roe_val / 100
            
            # 10년 후 가치 계산
            future_value = bps * ((1 + r_dec) ** n_years)
            # 가치 승수
            multiplier = future_value / price
            # 기대수익률(R)
            if multiplier > 0:
                exp_return = (10 ** (math.log10(multiplier) / n_years)) - 1
            else:
                exp_return = 0
            # 15% 수익률 만족 매수가
            target_buy_price = bps * (((1 + r_dec) / 1.15) ** n_years)
            
            res_list.append({
                "분석 시나리오": title,
                "적용 ROE": f"{roe_val:.2f}%",
                f"{n_years}년 후 가치": f"{future_value:,.0f}{unit}" if is_kr else f"{unit}{future_value:,.2f}",
                "10년 가치 승수": f"{multiplier:.2f}배",
                "예상 기대수익률(R)": f"{exp_return*100:.2f}%",
                "15% 목표 매수가": f"{target_buy_price:,.0f}{unit}" if is_kr else f"{unit}{target_buy_price:,.2f}"
            })
            
        st.table(pd.DataFrame(res_list).set_index("분석 시나리오"))
        
        # 6. 리스크 및 우려 점검 요약
        st.markdown("---")
        st.markdown("### 🚨 투자 시 우려되는 점 (리스크 리포트)")
        
        base_roe = roe_5y if roe_5y is not None else roe_current
        pbr_val = price / bps
        
        r_dec_base = base_roe / 100
        f_val_base = bps * ((1 + r_dec_base) ** n_years)
        base_exp_return = (10 ** (math.log10(f_val_base / price) / n_years)) - 1 if price > 0 and f_val_base > 0 else 0
        
        risks = []
        if base_exp_return < 0.15:
            risks.append(f"현재 가격 기준 예상 기대수익률({base_exp_return*100:.2f}%)이 요구수익률 15%보다 낮습니다. 주가가 더 하락하여 안전마진이 확보될 때까지 분할 매수를 고려해야 합니다.")
        if pbr_val > 3.0:
            risks.append(f"현재 PBR이 {pbr_val:.2f}배로 자산 가치 대비 멀티플이 과도하게 잡혀 있습니다. 시장 충격 시 낙폭이 클 수 있습니다.")
        if roe_5y is not None and roe_current is not None and roe_current < roe_5y * 0.8:
            risks.append(f"최근 분기 ROE({roe_current:.2f}%)가 5년 평균({roe_5y:.2f}%) 대비 20% 이상 급감했습니다. 일시적 업황 악화인지 고유 경쟁력 악화인지 정성적 분석이 필수적입니다.")
        if base_roe < 10.0:
            risks.append(f"적용된 ROE가 {base_roe:.2f}%로 주주 자본을 굴리는 속도가 시장 평균보다 느립니다. 장기 복리 효과를 누리기 어려울 수 있습니다.")
            
        if risks:
            for risk in risks:
                st.warning(f"• {risk}")
        else:
            st.success("🎉 재무 지표 관점에서 뚜렷한 리스크 징후가 발견되지 않은 우량한 상태입니다.")
else:
    st.info("종목 분석을 시작하려면 왼쪽 사이드바에 올바른 티커를 입력하고 기다려주세요.")
