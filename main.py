import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import timedelta
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_tavily import TavilySearch
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="AI 주식 분석기", layout="wide")

# 도구 설정
# 뉴스 검색 도구
search_tool = TavilySearch(max_results=3)

# AI 애널리스트 설정
llm = ChatOpenAI(model="gpt-5-mini", temperature=0)

# 핵심 함수 : 주가 데이터 가져오기
def get_stock_date(ticker):
    # 최근 1개월 데이터
    stock = yf.Ticker(ticker)
    df = stock.history(period="1mo")

    # 등락률 계산
    df['Change'] = df['Close'].pct_change() * 100
    df.index = df.index.date # 시간 제거하고 날짜만 남김
    return df

# 핵심 함수: 급등락 날짜 감지 및 뉴스 분석
def analyze_volatility(ticker, df):
    analysis_results = []
    
    threshold = 3.0 
    significant_days = df[abs(df['Change']) >= threshold].sort_index(ascending=False)

    if significant_days.empty:
        return "최근 한 달간 특이한 급등락(3% 이상)이 없었습니다."

    progress_text = "주가 급변일 분석 중..."
    my_bar = st.progress(0, text=progress_text)
    total_days = len(significant_days)

    for i, (date, row) in enumerate(significant_days.iterrows()):
        date_str = date.strftime("%Y-%m-%d")
        change_rate = row['Change']
        direction = "급등" if change_rate > 0 else "폭락"
        
        my_bar.progress((i + 1) / total_days, text=f"{date_str} 분석 중...")

        query = f"{date_str} {ticker} stock news reason for price move"
        
        try:
            # 1. 검색 실행
            search_response = search_tool.invoke(query)
            
            # [수정] 데이터 구조에 따라 유연하게 처리
            news_items = []
            
            # Case A: 딕셔너리로 온 경우 (디버깅 로그와 같은 경우)
            if isinstance(search_response, dict) and 'results' in search_response:
                news_items = search_response['results']
            
            # Case B: 바로 리스트로 온 경우 (LangChain 버전에 따라 다를 수 있음)
            elif isinstance(search_response, list):
                news_items = search_response
            
            # 뉴스 데이터 추출
            if news_items and len(news_items) > 0:
                # 내용 합치기
                news_content = "\n".join([item.get('content', '') for item in news_items])
                # 첫 번째 기사의 URL 가져오기
                url = news_items[0].get('url', '#')
            else:
                news_content = "관련 뉴스 검색 결과가 없습니다."
                url = "#"

        except Exception as e:
            print(f"Search Error: {e}")
            news_content = "검색 중 오류 발생"
            url = "#"

        # AI 분석
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "당신은 금융 애널리스트입니다. 주가 변동과 뉴스를 보고 원인을 한 문장으로 명확히 요약하세요."),
                ("human", """
                [종목]: {ticker}
                [날짜]: {date}
                [변동률]: {change:.2f}% ({direction})
                [뉴스 검색 결과]:
                {news}
                
                위 정보를 바탕으로 왜 주가가 변동했는지 핵심 원인을 '헤드라인 스타일'로 요약해줘.
                정보가 부족하면 '정보 부족'이라고만 답해.
                """)
            ])
            
            chain = prompt | llm
            reason = chain.invoke({
                "ticker": ticker, 
                "date": date_str, 
                "change": change_rate, 
                "direction": direction,
                "news": news_content
            }).content
        except Exception as e:
            reason = "AI 분석 실패"

        analysis_results.append({
            "date": date_str,
            "change": change_rate,
            "reason": reason,
            "url": url
        })
    
    my_bar.empty()
    return analysis_results

# UI 구성
st.title("AI 주식 뉴스 분석기")
st.caption("주가가 급등/급락한 날짜를 자동으로 찾고, 그 이유를 뉴스에서 찾아줍니다.")

ticker = st.text_input("분석할 미국 주식 티커를 입력하세요 (예: TSLA, AAPL, NVDA)", value="MSFT").upper()

if st.button("분석 시작", type="primary"):
    with st.spinner(f"{ticker} 데이터를 수집하고 분석합니다..."):
        try:
            # 주가 데이터 수집
            df = get_stock_date(ticker)

            # 차트 그리기
            st.line_chart(df['Close'])

            # 급등락 원인 분석
            st.subheader("변동성 원인 분석 리포트")
            results = analyze_volatility(ticker, df)

            if isinstance(results, str):
                st.info(results)
            else:
                for item in results:
                    color = "red" if item['change'] < 0 else "green"
                    icon = "📉" if item['change'] < 0 else "🚀"

                    with st.expander(f"{item['date']} | {icon} |{item['change']:.2f}% 변동", expanded=True):
                        st.markdown(f"분석 결과 : {color}[{item['reason']}]")
                        st.markdown(f"[관련 뉴스 보기]({item['url']})")
        except Exception as e:
            st.error(f"오류 발생: {e}")
            st.write("티커가 정확한지 확인해주세요.")
