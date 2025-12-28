
import streamlit as st
from huggingface_hub import InferenceClient
import os

HF_TOKEN = st.secrets["HF_TOKEN"]
client = InferenceClient(api_key=HF_TOKEN)

st.title("AI議論パートナー")

# --- 会話履歴の初期化 ---
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "system",
            "content": "あなたは論理的で冷静な議論AIです。ユーザーの主張に対して、事実や根拠をもとに短い文章で反論してください。"
        }
    ]

st.write("下に過去の会話が表示されます：")
for msg in st.session_state["messages"]:
    if msg["role"] != "system":
        st.chat_message(msg["role"]).write(msg["content"])

# --- ユーザー入力 ---
prompt = st.chat_input("あなたの主張を入力してください…")

if prompt:
    # ユーザー発言を履歴に追加
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

    # AI の反論を履歴に追加
    st.session_state["messages"].append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)

# --- 履歴リセットボタン ---
if st.button("会話をリセット"):
    st.session_state["messages"] = [
        {
            "role": "system",
            "content": "あなたは論理的で冷静な議論AIです。ユーザーの主張に短文でに反論します。"
        }
    ]
    st.success("会話履歴をリセットしました。")
