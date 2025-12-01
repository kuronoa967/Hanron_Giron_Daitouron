import streamlit as st
import pyrebase

firebaseConfig = {
    "apiKey": st.secrets["firebase"]["apiKey"],
    "authDomain": st.secrets["firebase"]["authDomain"],
    "projectId": st.secrets["firebase"]["projectId"],
}

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()

def login_page():
    st.title("ログイン / 新規登録")

    choice = st.sidebar.selectbox("メニューを選択", ["ログイン", "新規登録"])

    email = st.text_input("メールアドレス")
    password = st.text_input("パスワード", type="password")

    if choice == "ログイン":
        if st.button("ログイン"):
            try:
                user = auth.sign_in_with_email_and_password(email, password)
                st.session_state["user"] = user
                st.success("ログイン成功！")
                st.switch_page("HanronApp.py")
            except:
                st.error("ログインに失敗しました")

    else:
        if st.button("アカウント作成"):
            try:
                auth.create_user_with_email_and_password(email, password)
                st.success("登録成功！")
                user = auth.sign_in_with_email_and_password(email, password)
                st.session_state["user"] = user
                st.switch_page("HanronApp.py")
            except:
                st.error("アカウント作成に失敗しました")
