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
    "3. 기타 지표": ["비만", "건강수준", "흡연율", "범죄발생", "예산", "치료_", "입원및외래_"]
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

# --- 3. 사이드바: 분석 단위 및 지역 선택 ---
st.sidebar.title("🔍 분석 설정")
region_level = st.sidebar.radio("분석 단위 선택", ["시도", "시군구"])

comparison_list = []

if region_level == "시도":
    # 기존 방식: 시도 다중 선택
    all_sidos = sorted([str(x) for x in df_sido['시도'].unique() if pd.notna(x)])
    comparison_list = st.sidebar.multiselect("비교 대상 시도 선택", all_sidos, default=["전국", "서울특별시"] if "전국" in all_sidos else [all_sidos[0]])

else:
    # 새로운 방식: 전국 + 선택 시도 + 세부 시군구
    all_sidos_for_filter = sorted([str(x) for x in df_sido['시도'].unique() if pd.notna(x) and x != "전국"])
    selected_base_sido = st.sidebar.selectbox("기준 시도(광역) 선택", all_sidos_for_filter)
    
    # 해당 시도의 시군구 필터링
    available_sigungu = sorted(df_sigungu[df_sigungu['시군구별(1)'] == selected_base_sido]['시군구'].unique().tolist())
    selected_sigungus = st.sidebar.multiselect(f"{selected_base_sido} 내 세부 지자체 선택", available_sigungu)
    
    # 비교 리스트 구성: 전국 + 기준 시도 + 선택한 시군구들
    comparison_list = ["전국", selected_base_sido] + selected_sigungus

# --- 4. 메인 화면: 지표 선택 ---
st.title(f"📊 {region_level} 단위 통합 데이터 분석")
if region_level == "시군구":
    st.info(f"💡 현재 분석: **전국** vs **{comparison_list[1]}** vs **세부 지자체({len(selected_sigungus)}개)**")

selected_all_vars = []
cols = st.columns(3)
combined_pool = pd.concat([df_sido, df_sigungu], axis=1)

for i, (cat_name, keywords) in enumerate(VARIABLES_MAP.items()):
    with cols[i % 3]:
        with st.expander(cat_name, expanded=True):
            var_list = get_unique_vars(keywords, combined_pool)
            for v in var_list:
                if st.checkbox(v, key=f"chk_{region_level}_{v}"):
                    selected_all_vars.append(v)

st.divider()
view_mode = st.radio("⚙️ 보기 모드", ["단일 지표 지역별 비교", "선택 지역 평균 추이 (여러 지표 평균)"], horizontal=True)

# --- 5. 시각화 로직 ---
if selected_all_vars and comparison_list:
    fig = go.Figure()
    
    if view_mode == "단일 지표 지역별 비교":
        target_var = selected_all_vars[0]
        
        for reg in comparison_list:
            # 1. 시도 데이터셋에서 먼저 찾기 (전국, 서울특별시 등)
            data = process_data_v2(df_sido, [reg], target_var, "시도")
            
            # 2. 없으면 시군구 데이터셋에서 찾기 (강남구 등)
            if data.empty:
                data = process_data_v2(df_sigungu, [reg], target_var, "시군구")
            
            # 3. 전국값 우선/평균 로직 (전국인데 값이 비어있을 경우)
            if reg == "전국" and (data.empty or data['value'].isnull().all()):
                all_sido_data = process_data_v2(df_sido, [s for s in df_sido['시도'].unique() if s != "전국"], target_var, "시도")
                if not all_sido_data.empty:
                    data = all_sido_data.groupby('year')['value'].mean().reset_index()
                    reg_label = "전국(시도평균)"
                else: continue
            else:
                reg_label = reg

            if not data.empty:
                fig.add_trace(go.Scatter(
                    x=data['year'], y=data['value'], name=reg_label, mode='lines+markers',
                    line=dict(width=4 if "전국" in reg_label else (3 if reg == comparison_list[1] and region_level == "시군구" else 1.5))
                ))
        fig.update_layout(title=f"<b>{target_var}</b> 지역별 추이 비교")

    else:
        # 여러 지표 평균 추이 보기 (기존 로직 유지)
        for i, var in enumerate(selected_all_vars):
            # 전국값 우선 로직 적용하여 평균 데이터 생성
            data_selected = process_data_v2(df_sido if region_level=="시도" else df_sigungu, comparison_list, var, "시도" if region_level=="시도" else "시군구")
            data_national = process_data_v2(df_sido, ["전국"], var, "시도")
            
            years = sorted(data_selected['year'].unique())
            final_vals = []
            for y in years:
                nat = data_national[data_national['year']==y]['value']
                if not nat.empty and pd.notna(nat.values[0]):
                    final_vals.append(nat.values[0])
                else:
                    final_vals.append(data_selected[data_selected['year']==y]['value'].mean())
            
            yaxis_type = "y2" if i >= 1 else "y"
            fig.add_trace(go.Scatter(x=years, y=final_vals, name=f"{var} (평균/전국)", mode='lines+markers', yaxis=yaxis_type))
        fig.update_layout(title="선택 지역 지표별 통합 추이")

    fig.update_layout(
        xaxis=dict(title="연도", dtick=1), yaxis=dict(title="지표 값", autorange=True),
        hovermode="x unified", template="plotly_white", height=600,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    if len(selected_all_vars) >= 2 and view_mode != "단일 지표 지역별 비교":
        fig.update_layout(yaxis2=dict(anchor="x", overlaying="y", side="right", showgrid=False))

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 왼쪽에서 지역을 선택하고 상단에서 지표를 클릭하세요.")
