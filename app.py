import streamlit as st
import yfinance as yf
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="기대수익률(R) 계산기", layout="centered")
st.title("📈 기업 기대수익률(R) 계산기")
st.markdown("공식: $R = \\frac{1 + \\text{ROE}}{\\text{PBR}^{\\frac{1}{n}}} - 1$")
st.markdown("---")

# 2. 데이터 크롤링 함수
def get_financial_data(ticker):
    # 한국 주식 (6자리 숫자)
    if ticker.isdigit() and len(ticker) == 6:
        # 주말/휴일 대응: 최근 5일 중 가장 최신 영업일 데이터 탐색
        for i in range(5):
            target_date = (datetime.today() - timedelta(days=i)).strftime("%Y%m%d")
            df = stock.get_market_fundamental(target_date, target_date, ticker)
            if not df.empty:
                pbr = df['PBR'].iloc[0]
                per = df['PER'].iloc[0]
                
                if pd.isna(pbr) or pd.isna(per) or per == 0:
                    return None, None
                
                roe = pbr / per # ROE 산출
                return roe, pbr
        return None, None
        
    # 미국 주식 및 기타
    else:
        try:
            info = yf.Ticker(ticker).info
            roe = info.get('returnOnEquity', None)
            pbr = info.get('priceToBook', None)
            return roe, pbr
        except:
            return None, None

# 3. 사용자 입력부
col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("종목 티커 (예: 삼성전자=005930, 애플=AAPL)", "005930")
with col2:
    n_years = st.number_input("투자기간 N (년)", min_value=1, value=10, step=1)

# 4. 실행 및 결과 출력
if st.button("데이터 크롤링 및 분석", type="primary"):
    with st.spinner("재무 데이터를 분석하고 있습니다..."):
        roe, pbr = get_financial_data(ticker)
        
        if roe is not None and pbr is not None:
            # 기본 기대수익률 계산
            expected_return = ((1 + roe) / (pbr ** (1 / n_years))) - 1
            
            # 기대수익률 15% 기준 목표 PBR 계산
            target_pbr = ((1 + roe) / 1.15) ** n_years
            
            st.success(f"### 🎯 연평균 기대수익률(R): **{expected_return * 100:.2f}%**")
            
            st.markdown("#### 📊 수집된 지표 및 가치 평가")
            st.write(f"- **현재 ROE:** {roe * 100:.2f}%")
            st.write(f"- **현재 PBR:** {pbr:.2f}배")
            st.write(f"- **15% 수익 달성을 위한 목표 PBR:** **{target_pbr:.2f}배** 이하")
            
            st.markdown("---")
            st.markdown("#### 🚨 투자 시 우려되는 점 (리스크 점검)")
            
            concerns_found = False
            if expected_return < 0.15:
                st.warning("- **수익률 부족**: 현재 가격(PBR) 기준 기대수익률이 15%를 하회합니다. 더 높은 안전마진이 필요할 수 있습니다.")
                concerns_found = True
            if pbr > 3:
                st.warning("- **고평가 우려**: 현재 PBR이 3배를 초과하여 자산 가치 대비 프리미엄이 높게 형성되어 있습니다.")
                concerns_found = True
            if roe < 0.1:
                st.warning("- **수익성 확인 필요**: ROE가 10% 미만으로, 자본 배치 효율성이 다소 낮습니다.")
                concerns_found = True
                
            if not concerns_found:
                st.info("- 현재 재무 지표상 뚜렷한 가치평가 리스크가 발견되지 않았습니다. (추가적인 비즈니스 모델 분석 필요)")
                
        else:
            st.error("해당 종목의 데이터를 불러올 수 없습니다. 티커를 다시 확인해 주세요.")
