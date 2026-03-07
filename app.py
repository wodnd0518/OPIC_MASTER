import streamlit as st
from openai import OpenAI
import firebase_admin
from firebase_admin import credentials, firestore
import json
import random
from datetime import datetime, timezone

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
            return 'deep'    # 첫째날: 진한 주황
        elif hours_ago <= 48:
            return 'light'   # 둘째날: 흐린 주황
    except Exception:
        pass
    return None

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

tab1, tab2, tab3 = st.tabs(["✦ 표현 배우기", "📂 내 단어장", "🎮 플래시카드 게임"])

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

            답변 마지막에 반드시 [DATA] 구분자를 쓰고 그 뒤에 아래 JSON 형식으로만 데이터를 출력해줘.

            JSON 형식을 엄격히 지켜줘:
            {{"cards": [{{"word": "표현", "meaning": "한국어뜻", "sentence": "영어예문", "sentence_meaning": "예문한국어해석", "synonym_sentence": "유사표현활용문장"}}]}}
            """

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}]
                )
                full_text = response.choices[0].message.content
                json_part = full_text.split("[DATA]")[1].strip()
                json_part = json_part.replace("```json", "").replace("```", "").strip()
                cards_data = json.loads(json_part)
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
                            st.session_state['saved_flags'][i] = True
                            st.rerun()

# --- 4. 탭 2: 내 단어장 ---
with tab2:
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
                if st.button("삭제", key=f"del_{c['id']}"):
                    db.collection('opic_cards').document(c['id']).delete()
                    st.rerun()

# --- 5. 탭 3: 플래시카드 게임 ---
with tab3:
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
                    deck = all_cards.copy()
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
                                    deck.pop(idx)
                                    st.session_state['game_deck'] = deck
                                    if len(deck) > 0:
                                        st.session_state['game_idx'] = idx % len(deck)
                                    st.session_state['game_show_answer'] = False
                                    st.rerun()
                            with c2:
                                if st.button("🔁  다시 볼게", use_container_width=True):
                                    # Firebase에 복습 시각 기록
                                    db.collection('opic_cards').document(card['id']).update({
                                        'review_flagged_at': firestore.SERVER_TIMESTAMP
                                    })
                                    st.session_state['game_idx'] = (idx + 1) % len(deck)
                                    st.session_state['game_show_answer'] = False
                                    st.rerun()
