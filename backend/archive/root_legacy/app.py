import streamlit as st
from ai_engine import CAPTPEngine
from PIL import Image
import pandas as pd
import datetime

# --- 配置初始化 ---
st.set_page_config(page_title="智警实战综合训练平台 (CAPTP)", layout="wide", page_icon="🚔")
engine = CAPTPEngine()

# --- 侧边栏布局 ---
with st.sidebar:
    st.image("https://img.icons8.com/color/512/police-badge.png", width=100)
    st.title("🛡️ 系统控台")
    st.divider()
    page = st.radio(
        "选择实战模块",
        ["平台概览", "🎯 射击训练评估", "🥋 擒拿格斗评分", "🧠 执法决策推演", "📊 训练成绩档案"],
        index=0
    )
    st.divider()
    st.info("💡 提示：本系统已成功挂载 NVIDIA API。所有上传画面将通过加密链路进行分析。")

# --- 模块 1: 概览 ---
if page == "平台概览":
    st.title("🚔 智警实战综合训练平台 (CAPTP)")
    st.markdown("### 覆盖全实战场景的 AI 评估系统")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("今日在线教警", "42", "+4")
    col2.metric("累计评估次数", "1,208", "+12%")
    col3.metric("AI 评估偏差率", "1.5%", "-0.2%")
    
    st.image("https://img.freepik.com/free-photo/police-man-suit-with-gun_23-2148122612.jpg", use_container_width=True)

# --- 模块 2: 射击训练 ---
elif page == "🎯 射击训练评估":
    st.header("🎯 射击姿态及靶纸评分")
    st.markdown("#### 功能支持：持枪姿态纠编、弹孔检测、命中热力图分析")
    
    upload = st.file_uploader("上传您的射击图片...", type=['jpg', 'jpeg', 'png'])
    if upload:
        st.image(upload, width=500)
        mode = st.radio("评估模式", ["持枪姿态分析", "靶纸精度识别"])
        
        if st.button("🚀 启动 NVIDIA AI 深度评估", type="primary"):
            with st.spinner("视觉大模型正在提取关键特征点..."):
                prompt = f"你是一名专业的警察射击教官，请针对‘{mode}’模式，详细评估图中内容，按规范说明不足并给出建议。"
                feedback = engine.analyze_frame(upload.getvalue(), prompt)
                st.subheader("📋 评估报告")
                st.markdown(feedback)

# --- 模块 3: 格斗评分 ---
elif page == "🥋 擒拿格斗评分":
    st.header("🥋 擒拿格斗技术分析")
    st.markdown("#### 功能支持：动作 AQA 质量评分、控制角度分析、发力点检测")
    
    capture = st.camera_input("使用实时摄像头抓录训练帧")
    if capture:
        if st.button("分析动作规范性", type="secondary"):
            with st.spinner("解析人体骨架并进行力学分析..."):
                prompt = "请作为武警武力训练专家，分析截图中人物的擒拿/格斗动作。重点指出：力心偏转、防御漏洞及是否符合 1-5 分动作质量标准。"
                feedback = engine.analyze_frame(capture.getvalue(), prompt)
                st.subheader("🏋️ 动作解构报告")
                st.write(feedback)

# --- 模块 4: 决策推演 ---
elif page == "🧠 执法决策推演":
    st.header("🧠 执法情景模拟推理")
    st.markdown("#### 功能支持：基于 LLM 的多轮对抗博弈、人设模拟、法律合规回溯")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
        st.session_state.chat_history.append({"role": "system", "content": "你是一名教官。现在开始执法情景模拟。你将扮演一名被拦下的嫌疑人，请展示出一定的对抗性或心理博弈。受训警员需要通过对话来化解危机，你需要给出即时的反馈。"})

    # 渲染历史
    for msg in st.session_state.chat_history:
        if msg["role"] != "system":
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # 用户输入
    if user_cmd := st.chat_input("输入你的执法指令（例如：‘请配合出示证件，并熄火离车。’）"):
        st.session_state.chat_history.append({"role": "user", "content": user_cmd})
        with st.chat_message("user"):
            st.markdown(user_cmd)
            
        with st.chat_message("assistant"):
            with st.spinner("嫌疑人正在进行心理博弈..."):
                response = engine.simulate_decision(st.session_state.chat_history)
                st.markdown(response)
                st.session_state.chat_history.append({"role": "assistant", "content": response})

# --- 模块 5: 档案报表 ---
elif page == "📊 训练成绩档案":
    st.header("📊 实战训练大数据看板")
    df = pd.DataFrame({
        '日期': ['2026-04-01', '2026-04-02', '2026-04-03', '2026-04-04', '2026-04-05'],
        '射击平均': [8.5, 8.8, 9.1, 9.0, 9.3],
        '格斗评分': [82, 85, 84, 88, 90]
    })
    st.line_chart(df.set_index('日期'))
    st.table(df)
