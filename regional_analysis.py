import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import re

# --- 1. 페이지 설정 및 데이터 로드 ---
st.set_page_config(page_title="정신건강 데이터셋 분석", layout="wide")

@st.cache_data
def load_data():
    # 파일명을 저장소에 올린 이름과 정확히 일치시켜주세요. (예: data.xlsx)
    file_name = "(26-01-11)data.xlsx" 
    
    # 서버 환경에서 경로를 더 정확히 잡기 위한 로직
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, file_name)
    if not os.path.exists(file_path):
        file_path = file_name

    try:
        df_sido = pd.read_excel(file_path, sheet_name="시도")
        df_sigungu = pd.read_excel(file_path, sheet_name="시군구")
        return df_sido, df_sigungu
    except Exception as e:
        st.error(f"❌ 파일을 찾을 수 없거나 읽는 중 오류가 발생했습니다: {e}")
        # 현재 폴더에 어떤 파일이 있는지 출력 (디버깅용)
        st.info(f"현재 폴더 파일 목록: {os.listdir('.')}")
        return None, None

df_sido, df_sigungu = load_data()

# --- 2. 변수 매핑 함수 ---
VARIABLES_MAP = {
    "1. 인구 및 사회경제적 배경": ["총인구수", "근로소득"],
    "2. 정신건강 결과 지표": ["인구10만명당자살률_", "인구10만명당자살률_", "인구10만명당자살률_", "우울경험표준화율", "스트레스"],
    "3. 정신질환 치료 및 의료 이용 현황": ["치료_", "입원및외래_", "정신의료기관"],
    "4. 등록 장애인 현황": ["등록정신장애인수"],
    "5. 인프라, 인력 및 예산": ["정신건강_", "결산", "예산", "관리자"],
    "6. 건강생활실태 및 기타": ["비만", "건강수준", "현재흡연율"]
}

def get_unique_vars(keywords, df):
    matched = [c for c in df.columns if any(k in c for k in keywords)]
    return sorted(list(set([re.sub(r'_\d+.*| \d+.*', '', c) for c in matched])))

# --- 3. 사이드바: 지역 설정 ---
st.sidebar.title("🔍 지역 설정")
region_level = st.sidebar.radio("분석 단위", ["시도", "시군구"])
current_df = df_sido if region_level == "시도" else df_sigungu
loc_col = "시도" if region_level == "시도" else "시군구"

all_regions = sorted(current_df[loc_col].unique().tolist())
default_regions = all_regions if region_level == "시도" else [all_regions[0]]
selected_regions = st.sidebar.multiselect("분석 대상 지역 선택", all_regions, default=default_regions)

# --- 4. 메인 화면: 지표 선택 ---
st.title(f"📊 {region_level} 정신건강 데이터 분석")
st.markdown("### 📋 분석할 지표를 선택하세요")

selected_all_vars = []
cols = st.columns(3)

for i, (cat_name, keywords) in enumerate(VARIABLES_MAP.items()):
    if region_level == "시군구" and ("3." in cat_name or "4." in cat_name):
        continue
    with cols[i % 3]:
        with st.expander(cat_name, expanded=True):
            var_list = get_unique_vars(keywords, current_df)
            for v in var_list:
                if st.checkbox(v, key=f"chk_{v}"):
                    selected_all_vars.append(v)

st.divider()

# --- 5. 시각화 모드 선택 (추가된 기능) ---
st.markdown("### ⚙️ 시각화 방식 설정")
view_mode = st.radio(
    "보기 모드를 선택하세요",
    ["선택한 지역 평균 추이 보기", "지역별 Raw Data 개별 비교하기"],
    horizontal=True
)

# --- 6. 데이터 처리 함수 ---
def process_data(df, regions, var_name, loc_column):
    var_cols = [c for c in df.columns if var_name in c]
    temp = df[df[loc_column].isin(regions)][[loc_column] + var_cols]
    melted = temp.melt(id_vars=[loc_column], var_name="item", value_name="value")
    melted['value'] = pd.to_numeric(melted['value'], errors='coerce')
    
    def clean_year(text):
        match = re.search(r'\d+', text)
        if match:
            y = match.group()
            return f"20{y}" if len(y) == 2 else y
        return None
    
    melted['year'] = melted['item'].apply(clean_year)
    return melted.dropna(subset=['year', 'value'])

# --- 7. 시각화 실행 ---
if selected_all_vars and selected_regions:
    fig = go.Figure()
    colors = px.colors.qualitative.Plotly

    if view_mode == "선택한 지역 평균 추이 보기":
        # 기존 평균값 로직
        for i, var in enumerate(selected_all_vars):
            data = process_data(current_df, selected_regions, var, loc_col)
            avg_data = data.groupby('year')['value'].mean().reset_index()
            yaxis_type = "y2" if i == 1 else "y"
            fig.add_trace(go.Scatter(
                x=avg_data['year'], y=avg_data['value'], 
                name=f"{var} (평균)", mode='lines+markers',
                line=dict(width=4, color=colors[i % len(colors)]),
                yaxis=yaxis_type
            ))
        title_text = "선택된 지역들의 지표별 평균 추이"
    
    else:
        # 지역별 Raw Data 개별 로직 (첫 번째 선택된 지표 기준)
        target_var = selected_all_vars[0]
        data = process_data(current_df, selected_regions, target_var, loc_col)
        
        for i, reg in enumerate(selected_regions):
            reg_data = data[data[loc_col] == reg].sort_values('year')
            fig.add_trace(go.Scatter(
                x=reg_data['year'], y=reg_data['value'], 
                name=reg, mode='lines+markers',
                line=dict(width=2)
            ))
        title_text = f"지역별 {target_var} 개별 추이 비교"
        if len(selected_all_vars) > 1:
            st.warning(f"⚠️ 개별 비교 모드에서는 첫 번째로 선택한 [{target_var}] 지표만 표시됩니다.")

    # 레이아웃 공통 설정
    layout_dict = {
        "title": title_text,
        "xaxis": dict(title="연도"),
        "yaxis": dict(title="지표 값", side="left"),
        "hovermode": "x unified",
        "legend": dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    }
    
    if view_mode == "선택한 지역 평균 추이 보기" and len(selected_all_vars) >= 2:
        layout_dict["yaxis2"] = dict(title="지표 값 (우측)", overlaying="y", side="right")

    fig.update_layout(**layout_dict)
    st.plotly_chart(fig, use_container_width=True)

    # 데이터 상세 보기 표
    with st.expander("📝 상세 데이터 확인"):
        if view_mode == "지역별 Raw Data 개별 비교하기":
            raw_pivot = data.pivot(index=loc_col, columns='year', values='value')
            st.dataframe(raw_pivot)
        else:
            # 평균값 모드일 때의 표 구성
            combined_avg = None
            for var in selected_all_vars:
                d = process_data(current_df, selected_regions, var, loc_col)
                a = d.groupby('year')['value'].mean().reset_index().rename(columns={'value': var})
                combined_avg = a if combined_avg is None else pd.merge(combined_avg, a, on='year')
            st.dataframe(combined_avg.set_index('year'))

else:
    st.info("💡 상단 카테고리에서 지표를 선택하고, 왼쪽 사이드바에서 지역을 선택해 주세요.")
