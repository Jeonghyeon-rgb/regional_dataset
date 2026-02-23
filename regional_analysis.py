import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import re
import os

# --- 1. 페이지 설정 및 데이터 로드 ---
st.set_page_config(page_title="지역별 정신건강 데이터 분석 시스템", layout="wide")

@st.cache_data  # [수정] 중복된 데코레이터 제거
def load_data():
    # 파일명을 깃허브와 동일하게 맞추세요. (추천: regional_data.xlsx)
    file_name = "(26-02-23)regional_data.xlsx" 
    base_path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_path, file_name)

    if not os.path.exists(file_path):
        # 깃허브 서버 환경에서는 파일명만으로도 시도
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

# --- 2. 변수 매핑 및 유틸리티 함수 ---
VARIABLES_MAP = {
    "1. 인구 및 사회경제적 배경": ["총인구수", "근로소득", "인당근로소득"],
    "2. 정신건강 결과 지표": ["자살률", "우울경험", "스트레스"],
    "3. 정신질환 치료 및 의료 이용": ["치료_", "입원및외래_", "정신의료기관"],
    "4. 등록 장애인 현황": ["등록정신장애인수"],
    "5. 인력 및 예산": ["정신건강복지센터", "결산", "예산", "관리자"],
    "6. 건강생활실태 및 기타": ["비만", "건강수준", "흡연율", "범죄발생"]
}

def get_base_name(column_name):
    """컬럼명에서 연도(_2022 등)를 제거하여 순수 지표명만 추출"""
    return re.sub(r'_(\d{2,4})', '', column_name).strip()

def get_unique_vars(keywords, df):
    """키워드가 포함된 컬럼들을 찾아 연도를 제거한 고유 지표명 리스트 반환"""
    matched = [c for c in df.columns if any(k in c for k in keywords)]
    return sorted(list(set([get_base_name(c) for c in matched])))

# --- 3. 사이드바 설정 ---
st.sidebar.title("🔍 분석 설정")
region_level = st.sidebar.radio("분석 단위 선택", ["시도", "시군구"])
current_df = df_sido if region_level == "시도" else df_sigungu
loc_col = "시도" if region_level == "시도" else "시군구"

# 지역 선택
all_regions = sorted(current_df[loc_col].unique().tolist())
default_regions = ["전국", "서울특별시", "경기도"] if region_level == "시도" and "전국" in all_regions else [all_regions[0]]
selected_regions = st.sidebar.multiselect("분석 대상 지역", all_regions, default=default_regions)

# --- 4. 메인 화면: 지표 선택 ---
st.title(f"📊 {region_level} 단위 경제·사회·정신건강 데이터셋")
st.info("💡 데이터셋의 연도 표기 형식이 `_YYYY`로 통일되어 안정적인 시계열 분석이 가능합니다.")

selected_all_vars = []
cols = st.columns(3)

for i, (cat_name, keywords) in enumerate(VARIABLES_MAP.items()):
    # 시군구 데이터에 없는 카테고리 필터링 (필요 시 조정)
    if region_level == "시군구" and cat_name in ["3. 정신질환 치료 및 의료 이용", "4. 등록 장애인 현황"]: 
        continue
        
    with cols[i % 3]:
        with st.expander(cat_name, expanded=True):
            var_list = get_unique_vars(keywords, current_df)
            for v in var_list:
                if st.checkbox(v, key=f"chk_{region_level}_{v}"):
                    selected_all_vars.append(v)

st.divider()
view_mode = st.radio("⚙️ 시각화 모드", ["선택 지역 평균 추이 (여러 지표 비교)", "지역별 개별 추이 (한 지표 집중 비교)"], horizontal=True)

# --- 5. 데이터 처리 함수 (연도 중간/끝 모두 대응) ---
def process_data_v2(df, regions, var_name, loc_column):
    """선택한 지표명에 해당하는 연도별 컬럼들을 추출하여 Long Format으로 변환"""
    # 연도를 제거했을 때 선택한 지표명과 일치하는 컬럼 찾기
    var_cols = [c for c in df.columns if get_base_name(c) == var_name]
    
    if not var_cols: return pd.DataFrame()

    # 데이터 추출 및 변환
    temp = df[df[loc_column].isin(regions)][[loc_column] + var_cols]
    melted = temp.melt(id_vars=[loc_column], var_name="item", value_name="value")
    
    # 연도 추출 로직
    def extract_year(text):
        match = re.search(r'_(\d{2,4})', text)
        if match:
            y = match.group(1)
            return f"20{y}" if len(y) == 2 and int(y) < 50 else y
        return None
        
    melted['year'] = melted['item'].apply(extract_year)
    melted['value'] = pd.to_numeric(melted['value'], errors='coerce')
    
    return melted.dropna(subset=['year', 'value']).sort_values('year')

# --- 6. 시각화 실행 ---
if selected_all_vars and selected_regions:
    fig = go.Figure()
    colors = px.colors.qualitative.Bold

    if "평균 추이" in view_mode:
        # 지표별로 데이터의 '평균적인 크기'를 파악하여 축을 배정하기 위한 리스트
        scales = []
        
        for i, var in enumerate(selected_all_vars):
            data = process_data_v2(current_df, selected_regions, var, loc_col)
            if data.empty: continue
            
            avg_data = data.groupby('year')['value'].mean().reset_index()
            # 해당 지표의 중간값을 구해서 스케일 파악
            median_val = avg_data['value'].median()
            scales.append((var, avg_data, median_val))

        # 스케일이 큰 지표가 뒤로 가도록 정렬 (선택 사항이나 시각화 안정성을 위해)
        # 여기서는 단순히 첫 번째 지표는 왼쪽, 나머지는 값이 너무 차이나면 오른쪽으로 보냅니다.
        
        for i, (var, avg_data, m_val) in enumerate(scales):
            # [해결책] 첫 번째 지표와 비교해서 값이 10배 이상 차이 나면 무조건 y2 사용
            if i == 0:
                yaxis_type = "y"
            else:
                # 첫 번째 지표의 중앙값과 현재 지표의 중앙값 비교
                first_median = scales[0][2]
                if abs(m_val / (first_median + 1e-9)) > 5 or abs(m_val / (first_median + 1e-9)) < 0.2:
                    yaxis_type = "y2"
                else:
                    yaxis_type = "y"

            fig.add_trace(go.Scatter(
                x=avg_data['year'], y=avg_data['value'], 
                name=var, mode='lines+markers',
                yaxis=yaxis_type,
                line=dict(width=3, color=colors[i % len(colors)])
            ))

        # 레이아웃 설정 보완
        fig.update_layout(
            xaxis=dict(title="연도", type='category'),
            yaxis=dict(title="지표 1 (좌축)", side="left", showgrid=True),
            yaxis2=dict(
                title="지표 2 (우축)",
                anchor="x",
                overlaying="y",
                side="right",
                showgrid=False,
                autorange=True # 축 범위를 데이터에 맞게 자동 조절
            ),
            hovermode="x unified",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

    else:
        # 지역별 개별 비교 (동일 지표이므로 깨질 일 없음)
        target_var = selected_all_vars[0]
        data = process_data_v2(current_df, selected_regions, target_var, loc_col)
        for i, reg in enumerate(selected_regions):
            reg_data = data[data[loc_col] == reg].sort_values('year')
            fig.add_trace(go.Scatter(x=reg_data['year'], y=reg_data['value'], name=reg, mode='lines+markers'))
        
        fig.update_layout(
            title=f"지역별 {target_var} 추이",
            xaxis_type='category',
            yaxis=dict(autorange=True), # 여기서도 자동 범위 설정
            template="plotly_white"
        )

    st.plotly_chart(fig, use_container_width=True)
