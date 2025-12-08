import streamlit as st
import pyrebase
import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore
from huggingface_hub import InferenceClient

# --- Pyrebase Auth 用 Firebase Config ---
firebaseConfig = {
    "apiKey": st.secrets["firebase"]["apiKey"],
    "authDomain": st.secrets["firebase"]["authDomain"],
    "projectId": st.secrets["firebase"]["projectId"],
    "databaseURL": st.secrets["firebase"]["databaseURL"],
    "storageBucket": st.secrets["firebase"]["storageBucket"],
}

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()

# --- Firebase Admin SDK (Firestore用) ---
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

if "db" not in st.session_state:
    st.session_state["db"] = firestore.Client(project=st.secrets["firestore"]["project_id"])
db = st.session_state["db"]

# --- Session State ---
if "user" not in st.session_state:
    st.session_state["user"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "topic" not in st.session_state:
    st.session_state["topic"] = None

# --- UI ---
if st.session_state["user"] is None:
    choice = st.sidebar.selectbox("メニューを選択", ["ログイン", "新規登録"])

    if choice == "ログイン":
        st.title("ログイン")
        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")

        if st.button("ログイン"):
            try:
                user = auth.sign_in_with_email_and_password(email, password)
                st.session_state["user"] = user
                st.success("ログイン成功！")

                # Firestoreからログ取得
                uid = user["localId"]
                doc = db.collection("conversations").document(uid).get()
                if doc.exists:
                    st.session_state["messages"] = doc.to_dict().get("messages", [])
                    st.session_state["topic"] = doc.to_dict().get("topic", None)

            except Exception as e:
                st.error("ログインに失敗しました: " + str(e))

    else:
        st.title("新規登録")
        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")

        if st.button("アカウント作成"):
            try:
                auth.create_user_with_email_and_password(email, password)
                st.success("登録成功！")

                user = auth.sign_in_with_email_and_password(email, password)
                st.session_state["user"] = user
            except:
                st.error("アカウント作成に失敗しました")

else:
    st.title("AI議論パートナー")
    st.write("User UID:", st.session_state["user"]["localId"])

    HF_TOKEN = st.secrets["HF_TOKEN"]
    client = InferenceClient(api_key=HF_TOKEN)

    for msg in st.session_state["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    prompt = st.chat_input("主張を入力してください…")

    if prompt:
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
        uid = st.session_state["user"]["localId"]
        db.collection("conversations").document(uid).set({
            "messages": st.session_state["messages"],
            "topic": st.session_state["topic"],
        })

    if st.sidebar.button("ログアウト"):
        st.session_state.clear()

    if st.sidebar.button("会話リセット"):
        uid = st.session_state["user"]["localId"]
        st.session_state["messages"] = []
        st.session_state["topic"] = None
        db.collection("conversations").document(uid).set({})
        st.success("リセットしました。")
