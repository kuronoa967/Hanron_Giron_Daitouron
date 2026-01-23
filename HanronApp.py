import streamlit as st
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from huggingface_hub import InferenceClient
from st_aggrid import AgGrid, GridOptionsBuilder
import pandas as pd

st.markdown(
    """
    <style>
    .st-emotion-cache-1r1cntt {
        padding-bottom: 0rem !important;
    }
    .st-emotion-cache-10p9htt {
        margin-bottom: 0rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

HF_TOKEN = st.secrets["HF_TOKEN"]
client = InferenceClient(api_key=HF_TOKEN)

if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase_admin"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()

API_KEY = st.secrets["firebase_auth"]["api_key"]

st.set_page_config(layout="wide")

if "page" not in st.session_state:
    st.session_state.page = "chat"   # 通常はチャット画面

if "user" not in st.session_state:
    st.session_state.user = None     # None = 未ログイン

if "chats" not in st.session_state:
    st.session_state.chats = []

if "messages" not in st.session_state:
    st.session_state.messages = []

if "new_chat" not in st.session_state:
    st.session_state.new_chat = False

if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None

if "force_select_index" not in st.session_state:
    st.session_state.force_select_index = None

if "topic" not in st.session_state:
    st.session_state.topic = None

if "grid_key" not in st.session_state:
    st.session_state.grid_key = "grid_key_1"

def load_chats(uid):
    chats_ref = db.collection("users").document(uid).collection("chats")
    docs = chats_ref.order_by("createdAt").stream()

    chats = []
    for doc in docs:
        data = doc.to_dict()
        chats.append({
            "id": doc.id,
            "title": data.get("title", "無題"),
            "topic": data.get("topic"),
            "createdAt": data.get("createdAt")
        })
    return chats
    
def create_chat(uid, title, topic):
    chat_ref = (
        db.collection("users")
        .document(uid)
        .collection("chats")
        .document()
    )

    chat_ref.set({
        "title": title,
        "topic": topic,
        "createdAt": firestore.SERVER_TIMESTAMP
    })
    return chat_ref.id
    
def save_message(uid, chat_id, role, content):
    messages_ref = (
        db.collection("users")
        .document(uid)
        .collection("chats")
        .document(chat_id)
        .collection("messages")
    )

    messages_ref.add({
        "role": role,
        "content": content,
        "At": firestore.SERVER_TIMESTAMP
    })

def load_messages(uid, chat_id):
    messages_ref = (
        db.collection("users")
        .document(uid)
        .collection("chats")
        .document(chat_id)
        .collection("messages")
        .order_by("At")
    )

    docs = messages_ref.stream()

    messages = []
    for doc in docs:
        data = doc.to_dict()
        messages.append({
            "role": data["role"],
            "content": data["content"],
        })

    return messages

def generate_AI_message(prompt, uid=None, chat_id=None):
    messages = []
    system_prompt = f"あなたは論理的な議論者です。ユーザーの主張に対して、事実と根拠をもとに短い文章で反論してください。議論は次のテーマに限定してください：{st.session_state['topic']}。それ以外の話題を入力された場合は"
    messages.append({"role": "system", "content": system_prompt})
    if uid is not None and chat_id is not None:
        past_messages = load_messages(uid, chat_id)
        for m in past_messages:
            if m["role"] == "user" or m["role"] == "assistant":
                messages.append(m)
    else:
        for m in st.session_state.messages:
            if m["role"] == "user" or m["role"] == "assistant":
                messages.append(m)
    messages.append({"role": "user", "content": prompt})
    with st.spinner("反論を生成中..."):
        completion = client.chat.completions.create(
            model="meta-llama/Llama-3.1-8B-Instruct",
            messages=messages,
            max_tokens=200,
            temperature=0.7,
        )
    answer = completion.choices[0].message.content
    if uid is not None and chat_id is not None:
        save_message(uid, chat_id, "assistant", answer)
    else:
        st.session_state.messages.append({"role": "assistant", "content": answer})
    return answer

def show_account_page():
    # -------------------------
    # 未ログインの場合
    # -------------------------
    if st.session_state.user is None:
        st.title("ログイン / 新規登録")

        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")

        col1, col2 = st.columns(2)

        # 新規登録
        with col1:
            if st.button("新規登録"):
                if not email or not password:
                    st.error("メールアドレスとパスワードを入力してください")
                    st.stop()
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
                payload = {
                    "email": email,
                    "password": password,
                    "returnSecureToken": True
                }

                r = requests.post(url, json=payload)
                data = r.json()

                if "localId" in data:
                    uid = data["localId"]

                    # Firestore に保存（初回 or 上書き）
                    db.collection("users").document(uid).set({
                        "email": email
                    }, merge=True)

                    # ★ ログイン状態を保存
                    st.session_state.user = {
                        "uid": uid,
                        "email": email
                    }

                    st.session_state.chats = load_chats(uid)
                    
                    st.success("登録成功")
                    st.session_state.page = "chat"
                    st.rerun()
                else:
                    st.error(data)

        # ログイン
        with col2:
            if st.button("ログイン"):
                if not email or not password:
                    st.error("メールアドレスとパスワードを入力してください")
                    st.stop()
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
                payload = {
                    "email": email,
                    "password": password,
                    "returnSecureToken": True
                }

                r = requests.post(url, json=payload)
                data = r.json()

                if "localId" in data:
                    uid = data["localId"]

                    # Firestore に保存（初回 or 上書き）
                    db.collection("users").document(uid).set({
                        "email": email
                    }, merge=True)

                    # ★ ログイン状態を保存
                    st.session_state.user = {
                        "uid": uid,
                        "email": email
                    }

                    st.session_state.chats = load_chats(uid)

                    st.success("ログイン成功")
                    st.session_state.messages = []
                    st.session_state.new_chat = True
                    st.session_state.current_chat_id = None
                    st.session_state.page = "chat"
                    st.rerun()
                else:
                    st.error(data)

    # -------------------------
    # ログイン済みの場合
    # -------------------------
    else:
        st.title("アカウント")

        st.write("メールアドレス:")
        st.code(st.session_state.user["email"])

        if st.button("ログアウト", type="primary"):
            st.session_state.user = None
            st.session_state.page = "chat"
            st.session_state.topic = None
            st.success("ログアウトしました")
            st.rerun()

def show_chat_page():
    if st.session_state.user and st.session_state.current_chat_id:
        messages = load_messages(
            st.session_state.user["uid"],
            st.session_state.current_chat_id
        )

        for msg in messages:
            st.chat_message(msg["role"]).write(msg["content"])
    else :
        for msg in st.session_state.messages:
            if msg["role"] == "system":
                continue
            st.chat_message(msg["role"]).write(msg["content"])
                
    prompt = st.chat_input("意見を入力してください…")

    if prompt:
        if st.session_state.user and st.session_state.current_chat_id is None:
            uid = st.session_state.user["uid"]
            new_chat_id = create_chat(uid, title=prompt, topic=prompt)
            st.session_state.current_chat_id = new_chat_id
            st.session_state.new_chat = False
            st.session_state.topic = prompt
            
            save_message(uid, new_chat_id, "user", prompt)
            generate_AI_message(prompt, uid=uid, chat_id=new_chat_id)
            
            st.session_state.chats = load_chats(uid)
            st.session_state.force_select_index = True
            st.rerun()
        elif st.session_state.user:
            uid = st.session_state.user["uid"]
            chat_id = st.session_state.current_chat_id
            
            save_message(uid, chat_id, role="user", content=prompt)
            generate_AI_message(prompt, uid=uid, chat_id=chat_id)
            
            st.rerun()
        else :
            if st.session_state.topic is None:
                st.session_state.topic = prompt

            st.chat_message("user").write(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            generate_AI_message(prompt)
            
            st.rerun()

with st.sidebar:
    if st.button("新規チャット", key="btn_new_chat", use_container_width=True):
        st.session_state.current_chat_id = None
        st.session_state.messages = []
        st.session_state.force_select_index = False
        st.session_state.page = "chat"
        st.session_state.new_chat = True
        st.session_state.topic = None
        if st.session_state.grid_key == "grid_key_1":
            st.session_state.grid_key = "grid_key_2"
        else:
            st.session_state.grid_key = "grid_key_1"
        st.rerun()
    
    # ② 真ん中：チャット一覧
    if st.session_state.user is None:
        # 未ログイン時
        st.markdown(
            """
            <div style="
                padding: 11.5rem 1rem;
                color: #888;
                font-size: 0.9rem;
                text-align: center;
            ">
                ログインすると<br>
                チャット履歴が保存されます
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        chat_titles = []
        for chat in st.session_state.chats:
            chat_titles.append(chat["title"])
            
        if not chat_titles:
            st.markdown(
                """
                <div style="
                    padding: 11.5rem 1rem;
                    color: #888;
                    font-size: 0.9rem;
                    text-align: center;
                ">
                    まだチャットが<br>
                    ありません
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            if chat_titles:
                # ------- DataFrame に変換 -------
                df = pd.DataFrame(st.session_state.chats)
                df = df.sort_values("createdAt", ascending=False).reset_index(drop=True)
                gb = GridOptionsBuilder.from_dataframe(df)

                selected_rows = []
                if st.session_state.force_select_index is not None and st.session_state.force_select_index:
                    selected_rows = [df.index[0]]
                elif st.session_state.current_chat_id is not None:
                    for i, row in df.iterrows():
                        if row["id"] == st.session_state.current_chat_id:
                            selected_rows = [i]
                            break
                gb.configure_selection('single', use_checkbox=False, pre_selected_rows=selected_rows)
                
                gb.configure_column("id", header_name="ID", hide=True)
                gb.configure_column("title", header_name="タイトル", width=200)
                gb.configure_column("topic", header_name="トピック", hide=True)
                gb.configure_column("createdAt", header_name="投稿日", hide=True)
                grid_options = gb.build()
            
                grid_response = AgGrid(
                    df,
                    gridOptions=grid_options,
                    height=400,
                    fit_columns_on_grid_load=True,
                    key=st.session_state.grid_key
                )
            
                # ------- 選択されたらチャットIDを取得 -------
                selected = grid_response["selected_rows"]
                
                if selected is not None and len(selected) > 0:
                    row = selected.iloc[0]
                    chat_id = row["id"]

                    if st.session_state.current_chat_id != chat_id:
                        st.session_state.force_select_index = False
                        st.session_state.current_chat_id = chat_id
                        st.session_state.topic = row["topic"]
                        st.session_state.new_chat = False
                        st.session_state.page = "chat"
                        st.rerun()
            
            else:
                st.write("まだチャットはありません")

    # ③ 一番下：アカウントボタン
    if st.button("アカウント", use_container_width=True):
        st.session_state.page = "account"

if st.session_state.page == "chat":
    show_chat_page()

elif st.session_state.page == "account":
    show_account_page()
