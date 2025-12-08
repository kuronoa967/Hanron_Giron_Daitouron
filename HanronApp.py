import streamlit as st
from huggingface_hub import InferenceClient
from google.cloud import firestore
import firebase_admin
from firebase_admin import credentials, auth
import json

# --- Firebase Admin SDK 初期化（Service Account Key） ---
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firestore"]))
    firebase_admin.initialize_app(cred)

db = firestore.Client(project=st.secrets["firestore"]["project_id"])

# --- Session State ---
if "user" not in st.session_state:
    st.session_state["user"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "topic" not in st.session_state:
    st.session_state["topic"] = None

# --- ログイン画面 ---
if st.session_state["user"] is None:
    st.title("ログイン")
    email = st.text_input("メールアドレス")
    password = st.text_input("パスワード", type="password")

    if st.button("ログイン"):
        try:
            user = auth.get_user_by_email(email)   # Admin側から UID が取得できる
            st.session_state["user"] = user

            # Firestore から履歴を読み込み
            doc = db.collection("conversations").document(user.uid).get()
            if doc.exists:
                data = doc.to_dict()
                st.session_state["messages"] = data.get("messages", [])
                st.session_state["topic"] = data.get("topic", None)

            st.success("ログイン成功！")
        except Exception as e:
            st.error("ログイン失敗: " + str(e))

else:
    st.title("AI議論パートナー")
    st.write("User UID:", st.session_state["user"].uid)

    HF_TOKEN = st.secrets["HF_TOKEN"]
    client = InferenceClient(api_key=HF_TOKEN)

    # 履歴表示
    for msg in st.session_state["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    prompt = st.chat_input("あなたの主張を入力してください…")

    if prompt:
        if st.session_state["topic"] is None:
            st.session_state["topic"] = prompt
            system_prompt = f"""
            あなたは論理的で冷静な議論AIです。
            ユーザーの主張に対して反論してください。
            議論テーマ: 「{st.session_state['topic']}」
            """
            st.session_state["messages"].append({"role": "system", "content": system_prompt})

        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        with st.spinner("AIが反論を考えています…"):
            completion = client.chat.completions.create(
                model="meta-llama/Llama-3.1-8B-Instruct",
                messages=st.session_state["messages"],
                temperature=0.7,
                max_tokens=200,
            )
            answer = completion.choices[0].message.content

        st.session_state["messages"].append({"role": "assistant", "content": answer})
        st.chat_message("assistant").write(answer)

        # ---- Firestore に保存 ----
        db.collection("conversations").document(st.session_state["user"].uid).set({
            "messages": st.session_state["messages"],
            "topic": st.session_state["topic"],
        })

    if st.sidebar.button("会話をリセット"):
        st.session_state["messages"] = []
        st.session_state["topic"] = None
        db.collection("conversations").document(st.session_state["user"].uid).set({})
        st.success("リセットしました")

    if st.sidebar.button("ログアウト"):
        st.session_state.clear()
