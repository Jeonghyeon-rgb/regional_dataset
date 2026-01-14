import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import re
import os

# --- 1. 페이지 설정 및 데이터 로드 ---
st.set_page_config(page_title="정신건강 데이터셋 분석", layout="wide")

@st.cache_data
def load_data():
    file_name = "260111_data.xlsx" 
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, file_name)
    if not os.path.exists(file_path):
        file_path = file_name

    try:
        df_sido = pd.read_excel(file_path, sheet_name="시도")
        df_sigungu = pd.read_excel(file_path, sheet_name="시군구")
        return df_sido, df_sigungu
    except Exception as e:
        st.error(f"❌ 파일을 찾을 수 없거나 읽는 중 오류 발생: {e}")
        return None, None

df_sido, df_sigungu = load_data()
if df_sido is None: st.stop()

# --- 2. 변수 매핑 ---
VARIABLES_MAP = {
    "1. 인구 및 사회경제적 배경": ["총인구수", "근로소득"],
    "2. 정신건강 결과 지표": ["인구10만명당자살률_계", "인구10만명당자살률_남자", "인구10만명당자살률_여자", "우울경험", "스트레스"],
    "3. 정신질환 치료 및 의료 이용 현황": ["치료_", "입원및외래_", "정신의료기관"],
    "4. 등록 장애인 현황": ["등록정신장애인수"],
    "5. 인력 및 예산": ["정신건강_", "결산", "예산", "관리자"],
    "6. 건강생활실태 및 기타": ["비만", "건강수준", "현재흡연율", "범죄발생총건수", "인구10만명당범죄발생", "형법범"]
}

def get_unique_vars(keywords, df):
    matched = [c for c in df.columns if any(k in c for k in keywords)]
    # 끝에 붙은 연도(_숫자)만 제거하여 고유 지표명 생성
    return sorted(list(set([re.sub(r'_\d+$| \d+$', '', c).strip() for c in matched])))

# --- 3. 사이드바 설정 ---
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
    if region_level == "시군구" and ("3." in cat_name or "4." in cat_name): continue
    with cols[i % 3]:
        with st.expander(cat_name, expanded=True):
            var_list = get_unique_vars(keywords, current_df)
            for v in var_list:
                if st.checkbox(v, key=f"chk_{region_level}_{v}"):
                    selected_all_vars.append(v)

st.divider()
view_mode = st.radio("⚙️ 보기 모드", ["선택한 지역 평균 추이 보기", "지역별 Raw Data 개별 비교하기"], horizontal=True)

# --- 5. 데이터 가공 함수 (연도 추출 로직 수정) ---
def process_data(df, regions, var_name, loc_column):
    # 선택한 지표로 시작하는 컬럼만 필터링
    var_cols = [c for c in df.columns if c.startswith(var_name + "_")]
    if not var_cols: return pd.DataFrame()

    temp = df[df[loc_column].isin(regions)][[loc_column] + var_cols]
    melted = temp.melt(id_vars=[loc_column], var_name="item", value_name="value")
    melted['value'] = pd.to_numeric(melted['value'], errors='coerce')
    
    def clean_year(text):
        # [핵심 수정] 문자열의 맨 끝($)에 있는 숫자만 가져옵니다.
        # 이렇게 해야 "인구10만명"의 '10'을 연도로 오해하지 않습니다.
        match = re.search(r'(\d+)$', text)
        if match:
            y = match.group()
            if len(y) == 2:
                # 01~50은 2000년대, 나머지는 1900년대로 처리
                return f"20{y}" if int(y) < 50 else f"19{y}"
            return y
        return None
    
    melted['year'] = melted['item'].apply(clean_year)
    return melted.dropna(subset=['year', 'value']).sort_values('year')

# --- 6. 시각화 ---
if selected_all_vars and selected_regions:
    fig = go.Figure()
    colors = px.colors.qualitative.Plotly

    if view_mode == "선택한 지역 평균 추이 보기":
        for i, var in enumerate(selected_all_vars):
            data = process_data(current_df, selected_regions, var, loc_col)
            if data.empty: continue
            
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
        target_var = selected_all_vars[0]
        data = process_data(current_df, selected_regions, target_var, loc_col)
        for i, reg in enumerate(selected_regions):
            reg_data = data[data[loc_col] == reg].sort_values('year')
            fig.add_trace(go.Scatter(x=reg_data['year'], y=reg_data['value'], name=reg, mode='lines+markers'))
        title_text = f"지역별 {target_var} 개별 추이 비교"

    fig.update_layout(
        title=title_text, xaxis=dict(title="연도", type='category'),
        yaxis=dict(title="지표 값", side="left"),
        yaxis2=dict(title="지표 값 (우측)", overlaying="y", side="right", showgrid=False) if len(selected_all_vars) >= 2 else None,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 지표와 지역을 선택해 주세요.")
