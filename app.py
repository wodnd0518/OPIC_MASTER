import streamlit as st
from openai import OpenAI
import firebase_admin
from firebase_admin import credentials, firestore
import json
import random
from datetime import datetime, timezone, timedelta, date

# --- 1. 초기 설정 (Firebase & OpenAI) ---
if not firebase_admin._apps:
    firebase_creds = dict(st.secrets["firebase"])
    firebase_creds["private_key"] = firebase_creds["private_key"].replace("\\n", "\n")
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred)
db = firestore.client()

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def get_review_style(review_flagged_at):
    """복습 표시 색상 반환. (진한 주황 → 흐린 주황 → None)"""
    if review_flagged_at is None:
        return None
    try:
        now = datetime.now(timezone.utc)
        dt = review_flagged_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours_ago = (now - dt).total_seconds() / 3600
        if hours_ago <= 24:
            return 'deep'
        elif hours_ago <= 48:
            return 'light'
    except Exception:
        pass
    return None

def is_recently_known(known_at, review_flagged_at=None):
    """
    알았어! 처리한 지 48시간 이내인 카드를 제외.
    단, 같은 턴에서 다시볼게(review_flagged_at)가 알았어!(known_at)보다
    나중에 찍혔다면 다음 턴에 반드시 포함.
    """
    if known_at is None:
        return False
    try:
        now = datetime.now(timezone.utc)
        dt_known = known_at
        if dt_known.tzinfo is None:
            dt_known = dt_known.replace(tzinfo=timezone.utc)
        if (now - dt_known).total_seconds() / 3600 > 48:
            return False
        # 다시볼게가 알았어! 이후에 기록됐으면 → 다음 턴 포함
        if review_flagged_at is not None:
            dt_review = review_flagged_at
            if dt_review.tzinfo is None:
                dt_review = dt_review.replace(tzinfo=timezone.utc)
            if dt_review > dt_known:
                return False
        return True
    except Exception:
        return False

KST = timezone(timedelta(hours=9))

def get_today_kst():
    return datetime.now(KST).date()

STREAK_THRESHOLD = 3  # 하루에 이 횟수 이상 액션해야 완료로 인정

def record_activity():
    """액션 발생 시 카운트 증가. 오늘 첫 3번째 액션일 때만 스트릭 갱신."""
    today = str(get_today_kst())
    doc_ref = db.collection('user_data').document('streak')
    doc = doc_ref.get()
    data = doc.to_dict() if doc.exists else {}

    activity_counts = data.get('activity_counts', {})
    prev_count = activity_counts.get(today, 0)
    activity_counts[today] = prev_count + 1

    streak = data.get('streak_count', 0)
    last_date_str = data.get('last_active_date')

    # 오늘 처음으로 3번째 액션을 완료한 순간에만 스트릭 계산
    if prev_count + 1 == STREAK_THRESHOLD:
        if last_date_str is None:
            streak = 1
        else:
            diff = (date.fromisoformat(today) - date.fromisoformat(last_date_str)).days
            if diff == 1:
                streak += 1
            elif diff > 1:
                streak = 1
        last_date_str = today

    # 60일 이전 데이터 정리
    cutoff = str(get_today_kst() - timedelta(days=60))
    activity_counts = {k: v for k, v in activity_counts.items() if k >= cutoff}

    doc_ref.set({
        'streak_count': streak,
        'last_active_date': last_date_str,
        'activity_counts': activity_counts
    })

def render_streak():
    """스트릭 위젯 렌더링."""
    doc = db.collection('user_data').document('streak').get()
    data = doc.to_dict() if doc.exists else {}

    streak = data.get('streak_count', 0)
    activity_counts = data.get('activity_counts', {})
    legacy_dates = set(data.get('activity_dates', []))  # 이전 형식 호환
    today = get_today_kst()
    # 일요일 시작 (weekday: Mon=0 ... Sun=6)
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    days_kr = ['일', '월', '화', '수', '목', '금', '토']

    # 요일별 활성 여부 미리 계산 (새 형식 OR 구 형식 모두 인정)
    day_dates = [sunday + timedelta(days=i) for i in range(7)]
    is_active_list = [
        activity_counts.get(str(d), 0) >= STREAK_THRESHOLD or str(d) in legacy_dates
        for d in day_dates
    ]
    today_count = activity_counts.get(str(today), 0)

    week_html = ""
    for i, day in enumerate(day_dates):
        is_today = (day == today)
        is_active = is_active_list[i]

        # 왼쪽/오른쪽 연결선 색상 (양쪽 노드 모두 active일 때만 초록)
        left_color  = "#22c55e" if (i > 0 and is_active and is_active_list[i-1]) else "rgba(255,255,255,0.12)"
        right_color = "#22c55e" if (i < 6 and is_active and is_active_list[i+1]) else "rgba(255,255,255,0.12)"
        left_vis  = "visibility:hidden;" if i == 0 else ""
        right_vis = "visibility:hidden;" if i == 6 else ""

        # 원 스타일
        if is_active:
            c_style  = "background:linear-gradient(135deg,#22c55e,#16a34a);color:white;font-size:0.8rem;border:none;"
            c_content = "✓"
        elif is_today and today_count > 0:
            c_style  = "border:2px dashed #f59e0b;color:#fbbf24;font-size:0.6rem;font-weight:700;"
            c_content = f"{today_count}/3"
        elif is_today:
            c_style  = "border:2px dashed #7c3aed;"
            c_content = ""
        else:
            c_style  = "border:2px solid rgba(255,255,255,0.15);"
            c_content = ""

        today_bg = "background:rgba(124,58,237,0.1);border-radius:8px;" if is_today else ""

        week_html += (
            f"<div style='flex:1;display:flex;flex-direction:column;align-items:center;gap:5px;padding:4px 0;{today_bg}'>"
            f"  <span style='color:#94a3b8;font-size:0.68rem;font-weight:500;'>{days_kr[i]}</span>"
            f"  <div style='display:flex;align-items:center;width:100%;'>"
            f"    <div style='flex:1;height:2px;background:{left_color};{left_vis}'></div>"
            f"    <div style='width:28px;height:28px;border-radius:50%;flex-shrink:0;"
            f"display:flex;align-items:center;justify-content:center;{c_style}'>{c_content}</div>"
            f"    <div style='flex:1;height:2px;background:{right_color};{right_vis}'></div>"
            f"  </div>"
            f"</div>"
        )

    today_done = today_count >= STREAK_THRESHOLD
    if streak == 0:
        title = "아직 스트릭이 없어요"
        sub   = f"오늘 {STREAK_THRESHOLD}번 액션하면 불꽃이 켜져요! ({today_count}/{STREAK_THRESHOLD})"
        fire_color = "#64748b"
        fire_filter = "grayscale(1) opacity(0.4)"
    else:
        title = f"{streak}일 연속 학습 중!"
        sub   = f"오늘 {today_count}/{STREAK_THRESHOLD} 완료! 조금만 더요 🔥" if not today_done else "오늘 완료! 내일도 이어가요 💪"
        fire_color = "#f97316"
        fire_filter = f"drop-shadow(0 0 10px {fire_color})"

    st.markdown(f"""
    <div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
                border-radius:16px;padding:14px 16px;margin-bottom:24px;box-sizing:border-box;'>
        <div style='display:flex;align-items:center;gap:10px;margin-bottom:12px;'>
            <span style='font-size:1.8rem;line-height:1;filter:{fire_filter};flex-shrink:0;'>🔥</span>
            <div style='min-width:0;'>
                <div style='color:#e2e8f0;font-weight:700;font-size:1rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{title}</div>
                <div style='color:#94a3b8;font-size:0.75rem;'>{sub}</div>
            </div>
        </div>
        <div style='display:flex;align-items:center;width:100%;'>
            {week_html}
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 2. UI 레이아웃 ---
st.set_page_config(page_title="OPIC Master", layout="wide", page_icon="🎯")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    min-height: 100vh;
}

h1 {
    background: linear-gradient(90deg, #a78bfa, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.2rem !important;
    font-weight: 700 !important;
    margin-bottom: 0.2rem !important;
}

h2, h3 { color: #e2e8f0 !important; }

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    color: #94a3b8;
    font-weight: 500;
    padding: 8px 20px;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #7c3aed, #2563eb) !important;
    color: white !important;
}

.stTextInput input {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    padding: 12px 16px !important;
}
.stTextInput input:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.2) !important;
}

.stButton > button {
    background: linear-gradient(135deg, #7c3aed, #2563eb) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
    transition: opacity 0.2s ease, transform 0.1s ease !important;
}
.stButton > button:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}
.stButton > button:active {
    transform: translateY(0px) !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 16px !important;
    padding: 4px !important;
    backdrop-filter: blur(10px) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 32px rgba(124, 58, 237, 0.2) !important;
}

.stAlert {
    background: rgba(96, 165, 250, 0.1) !important;
    border: 1px solid rgba(96, 165, 250, 0.25) !important;
    border-radius: 10px !important;
    color: #bfdbfe !important;
}

.streamlit-expanderHeader {
    background: rgba(255,255,255,0.05) !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-weight: 600 !important;
}

p, label, .stMarkdown { color: #cbd5e1 !important; }
hr { border-color: rgba(255,255,255,0.1) !important; }
.stSpinner > div { border-top-color: #7c3aed !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 🎯 OPIC Master")
st.markdown("<p style='color:#94a3b8; margin-top:-10px; margin-bottom:20px;'>OPIC IH/AL을 향한 스마트 플래시카드</p>", unsafe_allow_html=True)

render_streak()

tab1, tab2, tab3, tab4, tab5 = st.tabs(["✦ 표현 배우기", "🔍 검색하기", "🤖 AI 질문", "📂 내 단어장", "🎮 플래시카드 게임"])

# --- 3. 탭 1: 핵심 표현 추출 ---
with tab1:
    topic = st.text_input("공부하고 싶은 주제를 입력하세요", value="Costco", placeholder="예: Costco, 여행, 취미...")

    if st.button("핵심 표현 추출하기"):
        with st.spinner(f"'{topic}' 관련 IH/AL 등급 표현을 가져오는 중..."):
            prompt = f"""
            너는 OPIC IH/AL을 목표로 하는 한국인 학생을 가르치는 원어민 영어 강사야.
            주제: {topic}

            아래 기준으로 표현 6개를 골라줘:
            - 4개: IH/AL 시험에서 실제로 점수를 올려주는 고급 표현 (많이 사용되는 고급 단어/구동사/관용구/콜로케이션 위주)
            - 2개: 원어민이 일상에서 쓰는 재치있고 재미있는 슬랭/관용표현 (영어가 흥미로워지는 것)

            각 표현마다 아래를 제공해줘:
            - 유용한 표현(word): 구동사/관용구/슬랭 형태로
            - 뜻(meaning): 한국어로 (슬랭은 뉘앙스까지 설명)
            - 예문(sentence): OPIC 답변에서 바로 쓸 수 있는 자연스러운 영어 예문
            - 문장의 의미(sentence_meaning): 예문의 한국어 해석
            - 유사표현을 넣은 문장(synonym_sentence): 비슷한 표현을 사용한 영어 문장 1개

            아래 JSON 형식으로만 응답해줘 (다른 텍스트 없이):
            {{"cards": [{{"word": "표현", "meaning": "한국어뜻", "sentence": "영어예문", "sentence_meaning": "예문한국어해석", "synonym_sentence": "유사표현활용문장"}}]}}
            """

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a JSON-only response assistant. Always respond with valid JSON only, no markdown, no explanations."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                cards_data = json.loads(response.choices[0].message.content)
                st.session_state['current_cards'] = cards_data['cards']
                st.session_state['current_topic'] = topic
                st.session_state['saved_flags'] = [False] * len(cards_data['cards'])
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

    if 'current_cards' in st.session_state:
        st.divider()
        st.markdown("### 마음에 드는 표현을 저장하세요!")
        st.markdown(f"<p style='color:#7c3aed; font-size:0.85rem; margin-top:-12px;'>Topic: {st.session_state.get('current_topic','')}</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        for i, card in enumerate(st.session_state['current_cards']):
            with st.container(border=True):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.markdown(f"### {card['word']}")
                    st.markdown(f"<span style='color:#a78bfa; font-weight:600;'>뜻</span> <span style='color:#e2e8f0;'>{card['meaning']}</span>", unsafe_allow_html=True)
                    st.info(f"**예문:** {card['sentence']}\n\n*{card['sentence_meaning']}*")
                    st.markdown(f"<span style='color:#60a5fa; font-size:0.9rem;'>유사표현 ›</span> <span style='color:#cbd5e1; font-size:0.9rem;'>{card['synonym_sentence']}</span>", unsafe_allow_html=True)
                with col2:
                    if st.session_state['saved_flags'][i]:
                        st.markdown("<div style='text-align:center; color:#34d399; font-size:1.5rem; padding-top:20px;'>✓</div>", unsafe_allow_html=True)
                    else:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("저장", key=f"like_{i}"):
                            db.collection('opic_cards').add({
                                'topic': st.session_state['current_topic'],
                                'word': card['word'],
                                'meaning': card['meaning'],
                                'sentence': card['sentence'],
                                'sentence_meaning': card['sentence_meaning'],
                                'synonym_sentence': card['synonym_sentence'],
                                'created_at': firestore.SERVER_TIMESTAMP,
                                'review_flagged_at': None
                            })
                            record_activity()
                            st.session_state['saved_flags'][i] = True
                            st.rerun()

# --- 4. 탭 2: 검색하기 ---
with tab2:
    st.markdown("### 표현 검색하기")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>단어나 표현을 검색하면 OPIC IH/AL 수준의 예문과 의미를 알려드려요.</p>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    search_word = st.text_input("검색할 표현을 입력하세요", placeholder="예: burn out, go the extra mile, savage...")

    if st.button("검색", key="search_btn"):
        if search_word.strip():
            with st.spinner(f"'{search_word}' 검색 중..."):
                search_prompt = f"""
                너는 OPIC IH/AL을 목표로 하는 한국인에게 영어 표현을 가르치는 원어민 강사야.
                검색 표현: "{search_word}"

                아래 JSON 형식으로만 응답해줘 (다른 텍스트 없이):
                - word: 검색한 표현
                - meaning: 핵심 뜻 (한국어, 슬랭이면 뉘앙스까지)
                - examples: 이 표현을 다양한 의미/상황으로 사용한 예문 4개. 각각:
                  - sentence: 영어 예문 (OPIC 답변에서 바로 쓸 수 있는 수준)
                  - sentence_meaning: 이 문장에서 쓰인 의미 (한국어, 짧게)
                  - synonym: 유사 표현 (영어, 1개)

                {{"word": "표현", "meaning": "핵심뜻(한국어)", "examples": [{{"sentence": "영어예문", "sentence_meaning": "한국어의미", "synonym": "유사표현"}}]}}
                """
                try:
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are a JSON-only response assistant. Always respond with valid JSON only, no markdown, no explanations."},
                            {"role": "user", "content": search_prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                    result = json.loads(resp.choices[0].message.content)
                    st.session_state['search_result'] = result
                    st.session_state['search_saved'] = [False] * len(result['examples'])
                    record_activity()
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")
        else:
            st.warning("표현을 입력해주세요.")

    if 'search_result' in st.session_state:
        result = st.session_state['search_result']
        st.divider()

        st.markdown(f"<h3 style='color:#e2e8f0;'>{result['word']}</h3>", unsafe_allow_html=True)
        st.markdown(f"<span style='color:#a78bfa; font-weight:600;'>핵심 뜻</span> <span style='color:#e2e8f0;'>{result['meaning']}</span>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        for i, ex in enumerate(result['examples']):
            with st.container(border=True):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.info(f"**예문:** {ex['sentence']}\n\n*{ex['sentence_meaning']}*")
                    st.markdown(f"<span style='color:#60a5fa; font-size:0.9rem;'>유사표현 ›</span> <span style='color:#cbd5e1; font-size:0.9rem;'>{ex['synonym']}</span>", unsafe_allow_html=True)
                with col2:
                    if st.session_state['search_saved'][i]:
                        st.markdown("<div style='text-align:center; color:#34d399; font-size:1.5rem; padding-top:20px;'>✓</div>", unsafe_allow_html=True)
                    else:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("저장", key=f"search_save_{i}"):
                            db.collection('opic_cards').add({
                                'topic': f"검색: {result['word']}",
                                'word': result['word'],
                                'meaning': result['meaning'],
                                'sentence': ex['sentence'],
                                'sentence_meaning': ex['sentence_meaning'],
                                'synonym_sentence': ex['synonym'],
                                'created_at': firestore.SERVER_TIMESTAMP,
                                'review_flagged_at': None
                            })
                            record_activity()
                            st.session_state['search_saved'][i] = True
                            st.rerun()

# --- 5. 탭 4: 내 단어장 ---
with tab4:
    st.markdown("### 저장된 단어장")
    cards_ref = db.collection('opic_cards').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    cards_list = [{'id': doc.id, **doc.to_dict()} for doc in cards_ref]

    if not cards_list:
        st.info("저장된 카드가 없습니다. '표현 배우기' 탭에서 표현을 저장해보세요!")
    else:
        st.markdown(f"<p style='color:#94a3b8; margin-top:-10px;'>총 {len(cards_list)}개의 카드</p>", unsafe_allow_html=True)
        for c in cards_list:
            review_style = get_review_style(c.get('review_flagged_at'))

            if review_style == 'deep':
                border_color = '#ea580c'
                bg_color = 'rgba(234,88,12,0.08)'
                glow = 'rgba(234,88,12,0.25)'
                badge_html = "<span style='background:#ea580c; color:white; padding:2px 8px; border-radius:6px; font-size:0.75rem; margin-left:8px;'>복습중 🔥</span>"
            elif review_style == 'light':
                border_color = '#fb923c'
                bg_color = 'rgba(251,146,60,0.05)'
                glow = 'rgba(251,146,60,0.15)'
                badge_html = "<span style='background:rgba(251,146,60,0.25); color:#fb923c; padding:2px 8px; border-radius:6px; font-size:0.75rem; margin-left:8px;'>복습중</span>"
            else:
                border_color = None
                bg_color = None
                glow = None
                badge_html = ""

            uid = f"rev-{c['id']}"

            with st.expander(f"{c['word']}  —  {c['meaning']}"):
                # 고유 span + :has() CSS로 이 expander 박스 자체에 테두리 적용
                st.markdown(f'<span id="{uid}" style="display:none;"></span>', unsafe_allow_html=True)
                if border_color:
                    st.markdown(f"""
                    <style>
                    [data-testid="stExpander"]:has(#{uid}) {{
                        border: 1.5px solid {border_color} !important;
                        border-radius: 12px !important;
                        background: {bg_color} !important;
                        box-shadow: 0 0 14px {glow} !important;
                    }}
                    </style>
                    """, unsafe_allow_html=True)

                topic_badge = f"<span style='background:rgba(124,58,237,0.2); color:#a78bfa; padding:2px 8px; border-radius:6px; font-size:0.8rem;'>{c['topic']}</span>"
                st.markdown(topic_badge + badge_html, unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                st.info(f"**예문:** {c['sentence']}\n\n*{c.get('sentence_meaning', '')}*")
                st.markdown(f"<span style='color:#60a5fa; font-size:0.9rem;'>유사표현 ›</span> <span style='color:#cbd5e1; font-size:0.9rem;'>{c.get('synonym_sentence', '')}</span>", unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                # 다른 예문 보기 버튼
                btn_col, del_col = st.columns([3, 1])
                with btn_col:
                    extra_key = f"extra_{c['id']}"
                    if st.button("다른 예문 보기", key=f"more_{c['id']}"):
                        if extra_key not in st.session_state:
                            with st.spinner("예문 생성 중..."):
                                extra_prompt = f"""
                                영어 표현 "{c['word']}"을 다양한 의미/상황으로 사용한 예문 3개를 알려줘.
                                각각 이 표현이 이 문장에서 어떤 뜻으로 쓰였는지 한국어로 짧게 설명해줘.
                                JSON 형식으로만 출력해줘:
                                [{{"sentence": "영어예문", "meaning": "이 문장에서의 뜻(한국어)"}}]
                                """
                                resp = client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[{"role": "user", "content": extra_prompt}]
                                )
                                raw = resp.choices[0].message.content.strip()
                                raw = raw.replace("```json", "").replace("```", "").strip()
                                st.session_state[extra_key] = json.loads(raw)
                        st.rerun()

                    if extra_key in st.session_state:
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.markdown("<span style='color:#a78bfa; font-size:0.85rem; font-weight:600;'>다양한 예문</span>", unsafe_allow_html=True)
                        for ex in st.session_state[extra_key]:
                            st.markdown(
                                f"<div style='margin:6px 0; padding:8px 12px; background:rgba(124,58,237,0.1); border-left:3px solid #7c3aed; border-radius:6px;'>"
                                f"<span style='color:#e2e8f0; font-size:0.9rem;'>{ex['sentence']}</span>"
                                f"<br><span style='color:#94a3b8; font-size:0.8rem;'>{ex['meaning']}</span>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                with del_col:
                    if st.button("삭제", key=f"del_{c['id']}"):
                        db.collection('opic_cards').document(c['id']).delete()
                        st.rerun()

# --- 7. 탭 3: AI 질문 ---
with tab3:
    st.markdown("### 🤖 나만의 영어 과외 선생님")
    st.markdown("<p style='color:#94a3b8; margin-top:-10px;'>영어 표현의 뜻, 어원, 뉘앙스 등 궁금한 건 뭐든 물어보세요!</p>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    question_input = st.text_area(
        "질문을 입력하세요",
        placeholder="예: 'get cold feet'가 왜 긴장한다는 뜻으로 쓰여요?\n예: 'literally'를 강조할 때 쓰는 건 문법적으로 맞나요?",
        height=100,
        key="ai_question_input"
    )

    if st.button("질문하기 ✨", key="ask_btn", use_container_width=True):
        if question_input.strip():
            with st.spinner("선생님이 답변을 작성 중이에요..."):
                tutor_prompt = f"""
                너는 한국인 영어 학습자의 전담 원어민 영어 과외 선생님이야.
                학생이 OPIC IH/AL을 목표로 하고 있고, 영어 표현에 진심으로 관심이 많아.

                학생 질문: {question_input}

                아래 스타일로 답변해줘:
                - 친근하고 따뜻한 선생님 말투 (한국어로)
                - 핵심 답변을 먼저, 그 다음 상세 설명
                - 어원이나 배경이 있으면 꼭 포함 (흥미롭게)
                - 실제 원어민이 쓰는 예문 1~2개 포함
                - 비슷한 표현이나 주의할 점도 간단히 언급
                - 너무 길지 않게, 핵심만 명확하게
                """
                try:
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are a warm, knowledgeable English tutor for Korean learners. Always respond in Korean with clear, engaging explanations."},
                            {"role": "user", "content": tutor_prompt}
                        ]
                    )
                    answer = resp.choices[0].message.content.strip()
                    db.collection('ai_questions').add({
                        'question': question_input.strip(),
                        'answer': answer,
                        'created_at': firestore.SERVER_TIMESTAMP
                    })
                    record_activity()
                    st.rerun()
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")
        else:
            st.warning("질문을 입력해주세요.")

    # 누적된 Q&A 목록
    questions_ref = db.collection('ai_questions').order_by('created_at', direction=firestore.Query.DESCENDING).stream()
    questions_list = [{'id': doc.id, **doc.to_dict()} for doc in questions_ref]

    if questions_list:
        st.divider()
        st.markdown(f"<p style='color:#94a3b8;'>총 {len(questions_list)}개의 질문</p>", unsafe_allow_html=True)
        for q in questions_list:
            with st.expander(f"Q. {q['question']}"):
                st.markdown(
                    f"<div style='padding:12px;background:rgba(124,58,237,0.08);border-left:3px solid #7c3aed;border-radius:8px;color:#e2e8f0;line-height:1.7;white-space:pre-wrap;'>{q['answer']}</div>",
                    unsafe_allow_html=True
                )
                if st.button("삭제", key=f"qdel_{q['id']}"):
                    db.collection('ai_questions').document(q['id']).delete()
                    st.rerun()

# --- 6. 탭 5: 플래시카드 게임 ---
with tab5:
    cards_ref2 = db.collection('opic_cards').stream()
    all_cards = [{'id': doc.id, **doc.to_dict()} for doc in cards_ref2]

    if not all_cards:
        st.info("게임을 시작하려면 '표현 배우기' 탭에서 카드를 저장하세요!")
    else:
        _, col_m, _ = st.columns([1, 3, 1])
        with col_m:
            # 게임 시작 버튼
            if not st.session_state.get('game_active', False):
                st.markdown(f"<p style='text-align:center; color:#94a3b8;'>저장된 카드 {len(all_cards)}개</p>", unsafe_allow_html=True)
                if st.button("게임 시작", use_container_width=True):
                    deck = [c for c in all_cards if not is_recently_known(c.get('known_at'), c.get('review_flagged_at'))]
                    random.shuffle(deck)
                    st.session_state['game_deck'] = deck
                    st.session_state['game_idx'] = 0
                    st.session_state['game_show_answer'] = False
                    st.session_state['game_active'] = True
                    st.rerun()

            else:
                deck = st.session_state['game_deck']

                # 모두 완료
                if len(deck) == 0:
                    st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
                    st.markdown("<h2 style='text-align:center; color:#34d399;'>모두 완료!</h2>", unsafe_allow_html=True)
                    st.markdown("<p style='text-align:center; color:#94a3b8;'>저장된 카드를 전부 외웠어요 🎉</p>", unsafe_allow_html=True)
                    st.balloons()
                    if st.button("처음으로", use_container_width=True):
                        st.session_state['game_active'] = False
                        del st.session_state['game_deck']
                        st.rerun()
                else:
                    idx = st.session_state['game_idx'] % len(deck)
                    card = deck[idx]

                    # 진행 상황 + 네비게이션
                    nav1, nav2, nav3 = st.columns([1, 4, 1])
                    with nav1:
                        if st.button("◀", use_container_width=True):
                            st.session_state['game_idx'] = (idx - 1) % len(deck)
                            st.session_state['game_show_answer'] = False
                            st.rerun()
                    with nav2:
                        st.markdown(f"<p style='text-align:center; color:#94a3b8; margin:0;'>{idx + 1} / {len(deck)}</p>", unsafe_allow_html=True)
                    with nav3:
                        if st.button("▶", use_container_width=True):
                            st.session_state['game_idx'] = (idx + 1) % len(deck)
                            st.session_state['game_show_answer'] = False
                            st.rerun()

                    st.markdown("<br>", unsafe_allow_html=True)

                    # 카드
                    with st.container(border=True):
                        st.markdown(f"<div style='text-align:center;'><span style='background:rgba(124,58,237,0.25); color:#a78bfa; padding:3px 10px; border-radius:6px; font-size:0.8rem;'>{card['topic']}</span></div>", unsafe_allow_html=True)
                        st.markdown(f"<h2 style='text-align:center; color:#e2e8f0; margin: 24px 0 8px;'>{card['word']}</h2>", unsafe_allow_html=True)

                        if not st.session_state.get('game_show_answer', False):
                            st.markdown("<p style='text-align:center; color:#64748b; margin-bottom:24px;'>뜻을 맞혀보세요!</p>", unsafe_allow_html=True)
                            if st.button("정답 보기", use_container_width=True):
                                st.session_state['game_show_answer'] = True
                                st.rerun()
                        else:
                            st.divider()
                            st.markdown(f"<p style='text-align:center; font-size:1.3rem; color:#a78bfa; font-weight:600; margin-bottom:12px;'>{card['meaning']}</p>", unsafe_allow_html=True)
                            st.info(f"**예문:** {card['sentence']}\n\n*{card.get('sentence_meaning', '')}*")
                            st.markdown(f"<span style='color:#60a5fa; font-size:0.9rem;'>유사표현 ›</span> <span style='color:#cbd5e1; font-size:0.9rem;'>{card.get('synonym_sentence', '')}</span>", unsafe_allow_html=True)
                            st.markdown("<br>", unsafe_allow_html=True)

                            c1, c2 = st.columns(2)
                            with c1:
                                if st.button("✅  알았어!", use_container_width=True):
                                    db.collection('opic_cards').document(card['id']).update({
                                        'known_at': firestore.SERVER_TIMESTAMP
                                    })
                                    record_activity()
                                    deck.pop(idx)
                                    st.session_state['game_deck'] = deck
                                    if len(deck) > 0:
                                        st.session_state['game_idx'] = idx % len(deck)
                                    st.session_state['game_show_answer'] = False
                                    st.rerun()
                            with c2:
                                if st.button("🔁  다시 볼게", use_container_width=True):
                                    db.collection('opic_cards').document(card['id']).update({
                                        'review_flagged_at': firestore.SERVER_TIMESTAMP
                                    })
                                    record_activity()
                                    st.session_state['game_idx'] = (idx + 1) % len(deck)
                                    st.session_state['game_show_answer'] = False
                                    st.rerun()
