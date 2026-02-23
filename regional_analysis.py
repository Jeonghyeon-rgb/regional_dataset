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

# --- 3. 사이드바 설정 ---
st.sidebar.title("🔍 분석 설정")
region_level = st.sidebar.radio("분석 단위 선택", ["시도", "시군구"])
current_df = df_sido if region_level == "시도" else df_sigungu
loc_col = "시도" if region_level == "시도" else "시군구"

all_regions = sorted([str(x) for x in current_df[loc_col].unique() if pd.notna(x)])
default_regions = ["전국", "서울특별시", "경기도"] if region_level == "시도" and "전국" in all_regions else [all_regions[0]]
selected_regions = st.sidebar.multiselect("분석 대상 지역", all_regions, default=default_regions)

# --- 4. 메인 화면 지표 선택 ---
st.title(f"📊 {region_level} 경제·사회·정신건강 통합 분석")

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

# --- 5. 데이터 처리 함수 ---
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

# --- 6. 시각화 실행 (전국값 우선 로직 적용) ---
if selected_all_vars and selected_regions:
    fig = go.Figure()
    colors = px.colors.qualitative.Bold

    if "평균 추이" in view_mode:
        for i, var in enumerate(selected_all_vars):
            # 1. 선택된 지역 데이터 가져오기
            data_selected = process_data_v2(current_df, selected_regions, var, loc_col)
            # 2. '전국' 데이터 별도로 가져오기 (선택 여부와 상관없이)
            data_national = process_data_v2(current_df, ["전국"], var, loc_col)
            
            if data_selected.empty: continue
            
            years = sorted(data_selected['year'].unique())
            final_values = []
            trace_name_suffix = ""

            for year in years:
                # 해당 연도의 전국 데이터 확인
                nat_val = data_national[data_national['year'] == year]['value']
                
                if not nat_val.empty and pd.notna(nat_val.values[0]):
                    # 전국 데이터가 있으면 사용
                    final_values.append(nat_val.values[0])
                    trace_name_suffix = "(전국)"
                else:
                    # 전국 데이터가 없으면 선택된 지역(전국 제외)의 평균 계산
                    mean_val = data_selected[(data_selected['year'] == year) & (data_selected[loc_col] != "전국")]['value'].mean()
                    final_values.append(mean_val)
                    if not trace_name_suffix: trace_name_suffix = "(지역평균)"

            # 그래프 추가
            yaxis_type = "y2" if i >= 1 else "y"
            fig.add_trace(go.Scatter(
                x=years, y=final_values, 
                name=f"{var} {trace_name_suffix}", 
                mode='lines+markers',
                yaxis=yaxis_type,
                line=dict(width=3, color=colors[i % len(colors)])
            ))
            
        layout_update = {
            "xaxis": dict(title="연도", dtick=1),
            "yaxis": dict(title=selected_all_vars[0], side="left", showgrid=True),
            "hovermode": "x unified", "template": "plotly_white",
            "legend": dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        }
        if len(selected_all_vars) >= 2:
            layout_update["yaxis2"] = dict(title=selected_all_vars[1], anchor="x", overlaying="y", side="right", showgrid=False)
        fig.update_layout(**layout_update)

    else:
        # 지역별 개별 비교 (기존과 동일)
        target_var = selected_all_vars[0]
        data = process_data_v2(current_df, selected_regions, target_var, loc_col)
        for i, reg in enumerate(selected_regions):
            reg_data = data[data[loc_col] == reg].sort_values('year')
            fig.add_trace(go.Scatter(x=reg_data['year'], y=reg_data['value'], name=reg, mode='lines+markers'))
        fig.update_layout(title=f"지역별 {target_var} 추이", xaxis=dict(dtick=1), template="plotly_white")

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 지역과 지표를 선택해 주세요.")
