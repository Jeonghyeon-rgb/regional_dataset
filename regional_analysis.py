import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import re
import os

# --- 1. 페이지 설정 및 데이터 로드 ---
st.set_page_config(page_title="지역별 통합 데이터 분석 시스템", layout="wide")

@st.cache_data
def load_combined_data():
    mental_file = "(26-02-23)regional_data.xlsx"
    econ_file = "(26-02-23)data_for_econ.xlsx"
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    def get_df(file_name, sheet):
        path = os.path.join(base_path, file_name)
        if not os.path.exists(path): path = file_name
        return pd.read_excel(path, sheet_name=sheet, engine='openpyxl')

    try:
        sido_m = get_df(mental_file, "시도")
        sigungu_m = get_df(mental_file, "시군구")
        sido_e = get_df(econ_file, "시도")
        sigungu_e = get_df(econ_file, "시군구")

        if '시도별' in sido_e.columns: sido_e = sido_e.rename(columns={'시도별': '시도'})
        df_sido = pd.merge(sido_m, sido_e, on="시도", how="outer")
        df_sigungu = pd.merge(sigungu_m, sigungu_e, on="시군구", how="outer")
        return df_sido, df_sigungu
    except Exception as e:
        st.error(f"❌ 파일을 읽는 중 오류 발생: {e}")
        return None, None

df_sido, df_sigungu = load_combined_data()
if df_sido is None: st.stop()

# --- 2. 변수 매핑 및 유틸리티 ---
VARIABLES_MAP = {
    "1. 인구 및 사회경제적 배경": ["총인구수", "근로소득", "인당근로소득", "1인당_GRDP", "GRDP_실질", "경제성장률"],
    "2. 정신건강 결과 지표": ["자살률", "우울경험", "스트레스"],
    "3. 정신질환 치료 및 의료 이용": ["치료_", "입원및외래_", "정신의료기관"],
    "4. 등록 장애인 현황": ["등록정신장애인수"],
    "5. 인력 및 예산": ["정신건강복지센터", "결산", "예산", "관리자"],
    "6. 건강생활실태 및 기타": ["비만", "건강수준", "흡연율", "범죄발생"]
}

def get_base_name(column_name):
    return re.sub(r'_(\d{2,4})', '', column_name).strip()

def get_unique_vars(keywords, df):
    matched = [c for c in df.columns if any(k in c for k in keywords)]
    return sorted(list(set([get_base_name(c) for c in matched])))

# --- 3. 사이드바: 계층적 지역 선택 로직 ---
st.sidebar.title("🔍 계층적 지역 선택")

# 1단계: 상위 시도 선택 (전국 포함)
all_sidos = sorted([str(x) for x in df_sido['시도'].unique() if pd.notna(x)])
selected_sido = st.sidebar.selectbox("대상 시도(광역) 선택", all_sidos, index=all_sidos.index("전국") if "전국" in all_sidos else 0)

# 2단계: 해당 시도에 속한 시군구 필터링
if selected_sido == "전국":
    sub_regions = []
else:
    # 시군구 데이터에서 선택한 시도에 해당하는 행만 필터링 (시군구별(1) 컬럼 기준)
    sub_regions = sorted(df_sigungu[df_sigungu['시군구별(1)'] == selected_sido]['시군구'].unique().tolist())

# 3단계: 최종 비교 대상 선택 (전국 + 선택한 시도 + 선택한 시군구들)
st.sidebar.markdown("---")
st.sidebar.subheader("📍 세부 비교 대상 설정")
comparison_list = st.sidebar.multiselect(
    "그래프에 표시할 지역을 선택하세요",
    options=["전국"] + [selected_sido] + sub_regions if selected_sido != "전국" else all_sidos,
    default=["전국", selected_sido] if selected_sido != "전국" else ["전국"]
)

# --- 4. 메인 화면: 지표 선택 ---
st.title(f"📊 {selected_sido} 지역 심층 비교 분석")
st.info("💡 전국 데이터, 광역 데이터(시도), 기초 데이터(시군구)를 한 그래프에서 직접 비교할 수 있습니다.")

selected_all_vars = []
cols = st.columns(3)
# 시도와 시군구 컬럼이 모두 포함된 통합 풀(Pool)에서 지표 추출
combined_cols_df = pd.concat([df_sido, df_sigungu], axis=1)

for i, (cat_name, keywords) in enumerate(VARIABLES_MAP.items()):
    with cols[i % 3]:
        with st.expander(cat_name, expanded=True):
            var_list = get_unique_vars(keywords, combined_cols_df)
            for v in var_list:
                if st.checkbox(v, key=f"chk_{v}"):
                    selected_all_vars.append(v)

# --- 5. 시각화 로직 ---
if selected_all_vars and comparison_list:
    fig = go.Figure()
    
    # 지표는 한 번에 하나씩 개별 비교하는 모드가 적합 (스케일 문제 예방)
    target_var = selected_all_vars[0]
    
    for reg in comparison_list:
        # 1. 시도 데이터셋에서 검색
        data = process_data_v2(df_sido, [reg], target_var, "시도")
        
        # 2. 시도에 없으면 시군구 데이터셋에서 검색
        if data.empty:
            data = process_data_v2(df_sigungu, [reg], target_var, "시군구")
        
        # 3. 만약 '전국'인데 값이 없다면? (사용자 요청: 전국값 없을 시 평균 제시)
        if reg == "전국" and (data.empty or data['value'].isnull().all()):
            # 시도 데이터셋의 전체 평균 계산 (전국 행 제외)
            all_sido_data = process_data_v2(df_sido, [s for s in all_sidos if s != "전국"], target_var, "시도")
            if not all_sido_data.empty:
                data = all_sido_data.groupby('year')['value'].mean().reset_index()
                data['시도'] = "전국(시도평균)"
                reg_label = "전국(시도평균)"
            else:
                continue
        else:
            reg_label = reg

        if not data.empty:
            fig.add_trace(go.Scatter(
                x=data['year'], 
                y=data['value'], 
                name=reg_label, 
                mode='lines+markers',
                line=dict(width=4 if "전국" in reg_label else 2) # 전국선은 두껍게
            ))

    fig.update_layout(
        title=f"<b>{target_var}</b> 추이 비교 ({', '.join(comparison_list)})",
        xaxis=dict(title="연도", dtick=1),
        yaxis=dict(title="지표 값", autorange=True),
        hovermode="x unified",
        template="plotly_white",
        height=600
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 왼쪽 사이드바에서 비교할 지역을 선택하고, 위에서 분석 지표를 클릭하세요.")
