import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import re
import os

# --- 1. 페이지 설정 및 데이터 로드 ---
st.set_page_config(page_title="지역별 정신건강 데이터 분석 시스템", layout="wide")

@st.cache_data # 공백 문자 제거됨
def load_data():
    file_name = "(26-02-23)regional_data.xlsx" 
    base_path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_path, file_name)

    if not os.path.exists(file_path):
        file_path = file_name

    try:
        df_sido = pd.read_excel(file_path, sheet_name="시도", engine='openpyxl')
        df_sigungu = pd.read_excel(file_path, sheet_name="시군구", engine='openpyxl')
        return df_sido, df_sigungu
    except Exception as e:
        st.error(f"❌ 파일을 읽는 중 오류 발생: {e}")
        return None, None

df_sido, df_sigungu = load_data()
if df_sido is None: st.stop()

# --- 2. 변수 매핑 및 유틸리티 ---
VARIABLES_MAP = {
    "1. 인구 및 사회경제적 배경": ["총인구수", "근로소득", "인당근로소득"],
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

# --- 3. 사이드바 설정 ---
st.sidebar.title("🔍 분석 설정")
region_level = st.sidebar.radio("분석 단위 선택", ["시도", "시군구"])
current_df = df_sido if region_level == "시도" else df_sigungu
loc_col = "시도" if region_level == "시도" else "시군구"

all_regions = sorted(current_df[loc_col].unique().tolist())
default_regions = ["전국", "서울특별시", "경기도"] if region_level == "시도" and "전국" in all_regions else [all_regions[0]]
selected_regions = st.sidebar.multiselect("분석 대상 지역", all_regions, default=default_regions)

# --- 4. 메인 화면 ---
st.title(f"📊 {region_level} 데이터 분석 시스템")

selected_all_vars = []
cols = st.columns(3)
for i, (cat_name, keywords) in enumerate(VARIABLES_MAP.items()):
    if region_level == "시군구" and cat_name in ["3. 정신질환 치료 및 의료 이용", "4. 등록 장애인 현황"]: continue
    with cols[i % 3]:
        with st.expander(cat_name, expanded=True):
            var_list = get_unique_vars(keywords, current_df)
            for v in var_list:
                if st.checkbox(v, key=f"chk_{region_level}_{v}"):
                    selected_all_vars.append(v)

st.divider()
view_mode = st.radio("⚙️ 시각화 모드", ["선택 지역 평균 추이 (여러 지표 비교)", "지역별 개별 추이 (한 지표 집중 비교)"], horizontal=True)

# --- 5. 데이터 처리 (연도 정수 변환) ---
def process_data_v2(df, regions, var_name, loc_column):
    var_cols = [c for c in df.columns if get_base_name(c) == var_name]
    if not var_cols: return pd.DataFrame()
    temp = df[df[loc_column].isin(regions)][[loc_column] + var_cols]
    melted = temp.melt(id_vars=[loc_column], var_name="item", value_name="value")
    
    def extract_year(text):
        match = re.search(r'_(\d{2,4})', text)
        if match:
            y = match.group(1)
            # 숫자로 변환하여 리턴 (정렬 문제 해결)
            full_year = f"20{y}" if len(y) == 2 and int(y) < 50 else y
            return int(full_year)
        return None
        
    melted['year'] = melted['item'].apply(extract_year)
    melted['value'] = pd.to_numeric(melted['value'], errors='coerce')
    return melted.dropna(subset=['year', 'value']).sort_values('year')

# --- 6. 시각화 ---
if selected_all_vars and selected_regions:
    fig = go.Figure()
    colors = px.colors.qualitative.Bold

    if "평균 추이" in view_mode:
        for i, var in enumerate(selected_all_vars):
            data = process_data_v2(current_df, selected_regions, var, loc_col)
            if data.empty: continue
            
            avg_data = data.groupby('year')['value'].mean().reset_index()
            
            # 단위가 너무 다른 지표들을 위한 축 배정
            # 2개 지표까지는 좌(y), 우(y2)축을 각각 배정하여 깨짐 방지
            yaxis_type = "y2" if i == 1 else "y"
            
            fig.add_trace(go.Scatter(
                x=avg_data['year'], y=avg_data['value'], 
                name=var, mode='lines+markers',
                yaxis=yaxis_type,
                line=dict(width=3, color=colors[i % len(colors)])
            ))
            
        # 레이아웃 설정 (X축 type='category' 제거하여 숫자 순서대로 정렬)
        layout_update = {
            "xaxis": dict(title="연도", dtick=1, gridcolor='lightgrey'), # dtick=1로 매년 표시
            "yaxis": dict(title=selected_all_vars[0], side="left", showgrid=True),
            "hovermode": "x unified",
            "template": "plotly_white",
            "legend": dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        }
        
        if len(selected_all_vars) >= 2:
            layout_update["yaxis2"] = dict(
                title=selected_all_vars[1],
                anchor="x", overlaying="y", side="right", showgrid=False
            )
        fig.update_layout(**layout_update)

    else:
        target_var = selected_all_vars[0]
        data = process_data_v2(current_df, selected_regions, target_var, loc_col)
        for i, reg in enumerate(selected_regions):
            reg_data = data[data[loc_col] == reg].sort_values('year')
            fig.add_trace(go.Scatter(x=reg_data['year'], y=reg_data['value'], name=reg, mode='lines+markers'))
        fig.update_layout(title=f"지역별 {target_var} 추이", xaxis=dict(dtick=1), template="plotly_white")

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 지역과 지표를 선택해 주세요.")
