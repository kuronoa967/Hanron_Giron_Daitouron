import streamlit as st
import pyrebase
import firebase_admin
from firebase_admin import credentials
# 変更点：google.auth をインポート
from google.oauth2.service_account import Credentials
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
    # サービスアカウント情報をディクショナリとして準備
    service_account_info = {
        "type": st.secrets["firestore"]["type"],
        "project_id": st.secrets["firestore"]["project_id"],
        "private_key_id": st.secrets["firestore"]["private_key_id"],
        "private_key": st.secrets["firestore"]["private_key"].replace('\\n', '\n'), # 改行コードの修正
        "client_email": st.secrets["firestore"]["client_email"],
        "client_id": st.secrets["firestore"]["client_id"],
        "auth_uri": st.secrets["firestore"]["auth_uri"],
        "token_uri": st.secrets["firestore"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["firestore"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["firestore"]["client_x509_cert_url"],
        "universe_domain": st.secrets["firestore"]["universe_domain"],
    }
    
    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)

if "db" not in st.session_state:
    # ★★★ 修正箇所：google-cloud-firestore 用の Credentials を直接生成 ★★★
    
    # 1. サービスアカウント情報から google.oauth2.service_account.Credentials を生成
    # 注: service_account_info は上記の firebase_admin 初期化時に使用したものと同じ
    firestore_creds = Credentials.from_service_account_info(service_account_info)
    
    # 2. firestore.Client に Credentials オブジェクトを明示的に渡す
    st.session_state["db"] = firestore.Client(
        project=st.secrets["firestore"]["project_id"],
        credentials=firestore_creds
    )
    # ★★★ 修正箇所 終了 ★★★


# ★★★ 修正・追加箇所 1: コレクション削除関数を定義 ★★★
def delete_collection(coll_ref, batch_size=50):
    """
    指定されたコレクションのドキュメントをバッチで削除します。
    """
    docs = coll_ref.limit(batch_size).stream()
    deleted = 0
    
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    
    # バッチサイズ分削除できた場合、まだ残っている可能性があるため再帰的に呼び出す
    if deleted >= batch_size:
        delete_collection(coll_ref, batch_size)
# ★★★ 修正・追加箇所 1 終了 ★★★


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

                uid = user["localId"]

                st.rerun()

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
            あなたは論理的な議論AIです。ユーザーの主張に対して、事実や根拠をもとに短い文章で反論してください。
            議論は次のテーマに限定してください：{st.session_state['topic']}
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
        db.collection("conversations").document(uid).collection("messages").add({
            "role": "assistant",
            "content": answer,
        })

    if st.sidebar.button("ログアウト"):
        st.session_state.clear()

    # ★★★ 修正・追加箇所 2: 会話リセット処理の修正 ★★★
    if st.sidebar.button("会話リセット"):
        uid = st.session_state["user"]["localId"]
        
        # 1. サブコレクションのドキュメントを全て削除
        messages_collection_ref = db.collection("conversations").document(uid).collection("messages")
        delete_collection(messages_collection_ref)
        
        # 2. 親ドキュメントを削除
        db.collection("conversations").document(uid).delete()
        
        st.session_state["messages"] = []
        st.session_state["topic"] = None
        st.success("リセットしました。")
    # ★★★ 修正・追加箇所 2 終了 ★★★
