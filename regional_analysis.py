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
    klosa_file = "(26-02-23)KLoSA.xlsx" # KLoSA 파일 추가
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    def get_df(file_name, sheet):
        path = os.path.join(base_path, file_name)
        if not os.path.exists(path): path = file_name
        return pd.read_excel(path, sheet_name=sheet, engine='openpyxl')

    try:
        # 1. 데이터 로드
        sido_m = get_df(mental_file, "시도")
        sigungu_m = get_df(mental_file, "시군구")
        sido_e = get_df(econ_file, "시도")
        sigungu_e = get_df(econ_file, "시군구")
        df_klosa = get_df(klosa_file, "Sheet3") # KLoSA 데이터 로드

        # 2. 컬럼명 정리 및 병합
        if '시도별' in sido_e.columns: sido_e = sido_e.rename(columns={'시도별': '시도'})
        
        # 시도 데이터 통합 (정신건강 + 경제 + KLoSA)
        df_sido = pd.merge(sido_m, sido_e, on="시도", how="outer")
        df_sido = pd.merge(df_sido, df_klosa, on="시도", how="outer")
        
        # 시군구 데이터 통합 (정신건강 + 경제)
        df_sigungu = pd.merge(sigungu_m, sigungu_e, on="시군구", how="outer")
        
        return df_sido, df_sigungu
    except Exception as e:
        st.error(f"❌ 파일을 읽는 중 오류 발생: {e}")
        return None, None

df_sido, df_sigungu = load_combined_data()
if df_sido is None: st.stop()

# --- 2. 변수 매핑 (7. KLoSA 항목 추가) ---
VARIABLES_MAP = {
    "1. 인구 및 사회경제적 배경": ["총인구수", "근로소득", "인당근로소득", "1인당_GRDP", "GRDP_실질", "경제성장률", "GRDP"],
    "2. 정신건강 결과 지표": ["자살률", "우울경험", "스트레스"],
    "3. 정신질환 치료 및 의료 이용": ["치료_", "입원및외래_", "정신의료기관"],
    "4. 등록 장애인 현황": ["등록정신장애인수"],
    "5. 인력 및 예산": ["정신건강복지센터", "결산", "예산", "관리자"],
    "6. 건강생활실태 및 기타": ["비만", "건강수준", "흡연율", "범죄발생"],
    "7. KLoSA (고령화패널)": ["평균연령", "KLoSA_", "Health_", "SubHealth_", "WorkLimit_", "depav_", "정신질환진단", "SatOver_", "Income_평균", "우울위험군_"]
}

def get_base_name(column_name):
    return re.sub(r'_(\d{2,4})', '', column_name).strip()

def get_unique_vars(keywords, df):
    matched = [c for c in df.columns if any(k in c for k in keywords)]
    return sorted(list(set([get_base_name(c) for c in matched])))

def process_data_v2(df, regions, var_name, loc_column):
    var_cols = [c for c in df.columns if get_base_name(c) == var_name]
    if not var_cols: return pd.DataFrame()
    temp = df[df[loc_column].isin(regions)][[loc_column] + var_cols]
    melted = temp.melt(id_vars=[loc_column], var_name="item", value_name="value")
    
    def extract_year(text):
        match = re.search(r'_(\d{2,4})', text)
        if match:
            y = match.group(1)
            full_year = f"20{y}" if len(y) == 2 and int(y) < 50 else y
            return int(full_year)
        return None
        
    melted['year'] = melted['item'].apply(extract_year)
    melted['value'] = pd.to_numeric(melted['value'], errors='coerce')
    return melted.dropna(subset=['year', 'value']).sort_values('year')

# --- 3. 사이드바: 분석 단위 및 지역 선택 (완벽 분리) ---
st.sidebar.title("🔍 분석 설정")
region_level = st.sidebar.radio("분석 단위 선택", ["시도", "시군구"])

comparison_list = []
base_sido = None

if region_level == "시도":
    # [시도 모드] 기존 방식: 여러 시도를 자유롭게 선택
    all_sidos = sorted([str(x) for x in df_sido['시도'].unique() if pd.notna(x)])
    comparison_list = st.sidebar.multiselect("비교 대상 시도 선택", all_sidos, default=["전국", "서울특별시"] if "전국" in all_sidos else [all_sidos[0]])
else:
    # [시군구 모드] 계층적 방식: 전국 + 광역(시도) + 기초(시군구)
    all_sidos_for_filter = sorted([str(x) for x in df_sido['시도'].unique() if pd.notna(x) and x != "전국"])
    base_sido = st.sidebar.selectbox("기준 시도(광역) 선택", all_sidos_for_filter)
    
    # 해당 시도 하위 지자체 필터링
    available_sigungu = sorted(df_sigungu[df_sigungu['시군구별(1)'] == base_sido]['시군구'].unique().tolist())
    selected_sigungus = st.sidebar.multiselect(f"{base_sido} 내 세부 지자체 선택", available_sigungu)
    
    # 자동으로 전국과 기준 시도를 리스트에 포함
    comparison_list = ["전국", base_sido] + selected_sigungus

# --- 4. 메인 화면: 지표 선택 (모드별 변수 맵 적용) ---
st.title(f"📊 {region_level} 단위 통합 데이터 분석")

selected_all_vars = []
cols = st.columns(3)

# 분석 단위에 따른 지표 데이터프레임 결정
current_df = df_sido if region_level == "시도" else df_sigungu

for i, (cat_name, keywords) in enumerate(SIDO_VARIABLES_MAP.items()):
    # 시군구 모드에서는 3, 4번 카테고리 건너뜀
    if region_level == "시군구" and cat_name in ["3. 정신질환 치료 및 의료 이용", "4. 등록 장애인 현황"]:
        continue
        
    with cols[i % 3]:
        with st.expander(cat_name, expanded=True):
            # 지표 목록은 현재 분석 레벨의 데이터프레임에서 추출
            var_list = get_unique_vars(keywords, current_df)
            for v in var_list:
                if st.checkbox(v, key=f"chk_{region_level}_{v}"):
                    selected_all_vars.append(v)

st.divider()
view_mode = st.radio("⚙️ 보기 모드", ["지역별 개별 비교 (추천)", "지표별 평균 추이 (여러 지표 선택 시)"], horizontal=True)

# --- 5. 시각화 실행 ---
if selected_all_vars and comparison_list:
    fig = go.Figure()
    
    if "개별 비교" in view_mode:
        target_var = selected_all_vars[0]
        
        for reg in comparison_list:
            # 1. 시도 데이터셋 검색 (전국, 서울특별시 등)
            data = process_data_v2(df_sido, [reg], target_var, "시도")
            
            # 2. 시군구 데이터셋 검색 (강남구 등)
            if data.empty:
                data = process_data_v2(df_sigungu, [reg], target_var, "시군구")
            
            # 3. 전국값 우선/평균 로직 (전국 데이터가 비어있을 경우)
            if reg == "전국" and (data.empty or data['value'].isnull().all()):
                all_sido_data = process_data_v2(df_sido, [s for s in df_sido['시도'].unique() if s != "전국"], target_var, "시도")
                if not all_sido_data.empty:
                    data = all_sido_data.groupby('year')['value'].mean().reset_index()
                    reg_label = "전국(시도평균)"
                else: continue
            else:
                reg_label = reg

            if not data.empty:
                # 전국은 두껍게, 기준 시도는 중간, 시군구는 기본 두께
                width = 4 if "전국" in reg_label else (2.5 if reg == base_sido else 1.5)
                fig.add_trace(go.Scatter(
                    x=data['year'], y=data['value'], name=reg_label, mode='lines+markers',
                    line=dict(width=width)
                ))
        fig.update_layout(title=f"<b>{target_var}</b> 지역별 시계열 비교")
    
    else:
        # 지표별 평균 추이 (여러 지표의 스케일 차이 해결을 위한 이중 축 적용)
        for i, var in enumerate(selected_all_vars):
            data_all = process_data_v2(current_df, comparison_list, var, "시도" if region_level=="시도" else "시군구")
            if data_all.empty: continue
            
            avg_data = data_all.groupby('year')['value'].mean().reset_index()
            yaxis_type = "y2" if i >= 1 else "y"
            
            fig.add_trace(go.Scatter(x=avg_data['year'], y=avg_data['value'], name=f"{var} (선택지역 평균)", mode='lines+markers', yaxis=yaxis_type))
        
        fig.update_layout(
            yaxis2=dict(anchor="x", overlaying="y", side="right", showgrid=False)
        )

    fig.update_layout(
        xaxis=dict(title="연도", dtick=1), yaxis=dict(title="지표 값", autorange=True),
        hovermode="x unified", template="plotly_white", height=600,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("👈 왼쪽에서 분석할 지역을 선택하고, 위 박스에서 지표를 클릭하세요.")
