import streamlit as st
from huggingface_hub import InferenceClient
import pyrebase

if "user" not in st.session_state:
    st.session_state["user"] = None
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "topic" not in st.session_state:
    st.session_state["topic"] = None

if st.session_state["user"] is None:
    firebaseConfig = {
        "apiKey": st.secrets["firebase"]["apiKey"],
        "authDomain": st.secrets["firebase"]["authDomain"],
        "projectId": st.secrets["firebase"]["projectId"],
        "databaseURL": st.secrets["firebase"]["databaseURL"],
        "storageBucket": st.secrets["firebase"]["storageBucket"],
    }
    firebase = pyrebase.initialize_app(firebaseConfig)
    auth = firebase.auth()
    
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
            except:
                st.error("ログインに失敗しました")

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

    # --- チャット履歴表示 ---
    for msg in st.session_state["messages"]:
        st.chat_message(msg["role"]).write(msg["content"])

    # --- ユーザー入力 ---
    prompt = st.chat_input("あなたの主張を入力してください…")

    if prompt:
        # 最初の発言を議論テーマとして設定
        if st.session_state["topic"] is None:
            st.session_state["topic"] = prompt

            system_prompt = f"""
            あなたは論理的で冷静な議論AIです。
            ユーザーの主張に対して、事実や根拠をもとに短い文章で反論してください。
            議論は次のテーマに限定してください: 「{st.session_state['topic']}」
            雑談や議論テーマ以外の質問には反論せず、「ほかの議論がしたい場合は履歴をリセットしてください」というような文章を出力してください。
            """
            st.session_state["messages"].append({"role": "system", "content": system_prompt})

        # ユーザー発言を追加
        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # AIへ送信
        with st.spinner("AIが反論を考えています…"):
            completion = client.chat.completions.create(
                model="meta-llama/Llama-3.1-8B-Instruct",
                messages=st.session_state["messages"],
                temperature=0.7,
                max_tokens=200,
            )
            answer = completion.choices[0].message.content

        # AIの返答表示
        st.session_state["messages"].append({"role": "assistant", "content": answer})
        st.chat_message("assistant").write(answer)

    # --- 履歴リセット ---
    if st.sidebar.button("会話をリセット"):
        st.session_state["messages"] = []
        st.session_state["topic"] = None
        st.success("会話履歴をリセットしました。")

    if st.sidebar.button("ログアウト"):
        st.session_state.clear()
