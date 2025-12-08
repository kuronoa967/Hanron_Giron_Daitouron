import streamlit as st
import firebase_admin
from firebase_admin import auth, credentials
from google.cloud import firestore
import json
from huggingface_hub import InferenceClient

# --- Firebase Admin SDK 初期化 ---
if not firebase_admin._apps:
    cred = credentials.Certificate({
        "type": st.secrets["firestore"]["type"],
        "project_id": st.secrets["firestore"]["project_id"],
        "private_key_id": st.secrets["firestore"]["private_key_id"],
        "private_key": st.secrets["firestore"]["private_key"],
        "client_email": st.secrets["firestore"]["client_email"],
        "client_id": st.secrets["firestore"]["client_id"],
        "auth_uri": st.secrets["firestore"]["auth_uri"],
        "token_uri": st.secrets["firestore"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["firestore"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["firestore"]["client_x509_cert_url"],
        "universe_domain": st.secrets["firestore"]["universe_domain"],
    })
    firebase_admin.initialize_app(cred)

db = firestore.Client(project=st.secrets["firestore"]["project_id"])

# --- Session State ---
if "user" not in st.session_state:
    st.session_state["user"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "topic" not in st.session_state:
    st.session_state["topic"] = None

# --- Login UI ---
if st.session_state["user"] is None:
    st.title("ログイン（Admin SDK）")

    email = st.text_input("メールアドレス")
    if st.button("ログイン"):
        try:
            user = auth.get_user_by_email(email)
            st.session_state["user"] = user

            # Firestoreからログ履歴を取得
            doc = db.collection("conversations").document(user.uid).get()
            if doc.exists:
                st.session_state["messages"] = doc.to_dict().get("messages", [])
                st.session_state["topic"] = doc.to_dict().get("topic", None)

            st.success("ログイン成功！")
        except Exception as e:
            st.error("ログイン失敗: " + str(e))

else:
    st.title("AI議論パートナー")
    st.write("User UID:", st.session_state["user"].uid)

    HF_TOKEN = st.secrets["HF_TOKEN"]
    client = InferenceClient(api_key=HF_TOKEN)

    for msg in st.session_state["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    prompt = st.chat_input("主張を入力してください…")

    if prompt:
        # 初回テーマ設定
        if st.session_state["topic"] is None:
            st.session_state["topic"] = prompt
            system_prompt = f"""
            あなたは論理的な議論AIです。
            テーマ：{st.session_state['topic']}
            """
            st.session_state["messages"].append({"role": "system", "content": system_prompt})

        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        with st.spinner("反論を生成中..."):
            completion = client.chat.completions.create(
                model="meta-llama/Llama-3.1-8B-Instruct",
                messages=st.session_state["messages"],
                max_tokens=200,
                temperature=0.7,
            )
            answer = completion.choices[0].message.content

        st.session_state["messages"].append({"role": "assistant", "content": answer})
        st.chat_message("assistant").write(answer)

        # Firestore 保存
        db.collection("conversations").document(st.session_state["user"].uid).set({
            "messages": st.session_state["messages"],
            "topic": st.session_state["topic"],
        })

    if st.sidebar.button("ログアウト"):
        st.session_state.clear()

    if st.sidebar.button("会話リセット"):
        st.session_state["messages"] = []
        st.session_state["topic"] = None
        db.collection("conversations").document(st.session_state["user"].uid).set({})
        st.success("リセットしました。")
