
# app.py — Streamlit Prototype: Student/Teacher Q&A Checker (with editable questions)
import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

DB_PATH = "answers.db"

# ---------- Safety: ensure run via streamlit ----------
if not st.runtime.exists():
    print("\n[!] Please run with:  streamlit run app.py\n")
    raise SystemExit

# ---------- DB Utilities ----------
def get_con():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = get_con()
    cur = con.cursor()
    # answers table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date_week TEXT NOT NULL,
            question_no INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            checked INTEGER DEFAULT 0
        );
        """
    )
    # question set table (editable by teacher)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_week TEXT NOT NULL,
            question_no INTEGER NOT NULL,
            question TEXT NOT NULL,
            UNIQUE(date_week, question_no) ON CONFLICT REPLACE
        );
        """
    )
    con.commit()
    con.close()

def save_answers(student_id, date_week, qa_list):
    con = get_con()
    cur = con.cursor()
    # remove previous answers for same student/date to avoid duplicates on resubmit
    cur.execute("DELETE FROM answers WHERE student_id=? AND date_week=?", (student_id, date_week))
    for qno, qtext, ans in qa_list:
        cur.execute(
            "INSERT INTO answers (student_id, date_week, question_no, question, answer, checked) VALUES (?,?,?,?,?,0)",
            (student_id, date_week, qno, qtext, ans)
        )
    con.commit()
    con.close()

def load_answers(date_week=None, student_search=""):
    con = get_con()
    where = []
    params = []
    if date_week:
        where.append("date_week = ?")
        params.append(date_week)
    if student_search:
        where.append("student_id LIKE ?")
        params.append(f"%{student_search}%")
    wh = (" WHERE " + " AND ".join(where)) if where else ""
    df = pd.read_sql_query(
        f"SELECT id, student_id, date_week, question_no, question, answer, checked FROM answers{wh} ORDER BY student_id, question_no",
        con,
        params=params
    )
    con.close()
    return df

def update_checked(ids, checked=True):
    if not ids:
        return
    con = get_con()
    cur = con.cursor()
    cur.execute(
        f"UPDATE answers SET checked = ? WHERE id IN ({','.join(['?']*len(ids))})",
        [1 if checked else 0, *ids]
    )
    con.commit()
    con.close()

# ---------- Questions helpers ----------
DEFAULT_QUESTIONS = [
    "Explain one key concept you learned today.",
    "Give an example related to the concept.",
    "What is one question you still have?"
]

def load_questions(date_week:str|None):
    """Load question set by date/week; fallback to defaults if not found or not provided"""
    if not date_week:
        return DEFAULT_QUESTIONS
    con = get_con()
    df = pd.read_sql_query(
        "SELECT question_no, question FROM questions WHERE date_week=? ORDER BY question_no",
        con, params=[date_week]
    )
    con.close()
    if df.empty:
        return DEFAULT_QUESTIONS
    return df.sort_values("question_no")["question"].tolist()

def save_question_set(date_week:str, questions:list[str]):
    con = get_con()
    cur = con.cursor()
    # delete all for date then insert, or use UPSERT per unique constraint
    cur.execute("DELETE FROM questions WHERE date_week=?", (date_week,))
    for idx, q in enumerate(questions, start=1):
        cur.execute("INSERT INTO questions (date_week, question_no, question) VALUES (?,?,?)",
                    (date_week, idx, q.strip()))
    con.commit()
    con.close()

def list_question_dates():
    con = get_con()
    df = pd.read_sql_query("SELECT DISTINCT date_week FROM questions ORDER BY date_week DESC", con)
    con.close()
    return df["date_week"].tolist()

# ---------- App State ----------
init_db()
st.set_page_config(page_title="Q&A Checker", page_icon="✅", layout="centered")

# safer session init
st.session_state.setdefault("started", False)
st.session_state.setdefault("q_index", 0)
st.session_state.setdefault("answers", [""] * len(DEFAULT_QUESTIONS))
st.session_state.setdefault("show_preview", False)
st.session_state.setdefault("teacher_loaded", False)

st.title("📚 Simple Student/Teacher Q&A Checker")

tab_student, tab_teacher = st.tabs(["👩‍🎓 Student", "👨‍🏫 Teacher"])

# ------------- Student Tab -------------
with tab_student:
    st.subheader("Start")
    col1, col2 = st.columns(2)
    with col1:
        student_id = st.text_input("Student ID", placeholder="e.g., S001")
    with col2:
        date_week = st.text_input("Date / Week", value=str(date.today()), help="Used to select which question set to load.")
    start = st.button("✅ START", use_container_width=True)
    
    if start:
        if not student_id.strip():
            st.warning("Please enter Student ID.")
        else:
            # load questions for this date/week (or default)
            st.session_state.current_questions = load_questions(date_week.strip())
            st.session_state.answers = [""] * len(st.session_state.current_questions)
            st.session_state.q_index = 0
            st.session_state.started = True
            st.session_state.show_preview = False

    if st.session_state.started:
        st.divider()
        questions = st.session_state.get("current_questions", DEFAULT_QUESTIONS)
        total = len(questions)
        q_idx = st.session_state.q_index
        st.progress((q_idx+1)/total, text=f"Question {q_idx+1} of {total}")
        
        st.text_input("Question", value=questions[q_idx], key=f"q_{q_idx}", disabled=True)
        st.session_state.answers[q_idx] = st.text_area("Your Answer", value=st.session_state.answers[q_idx], height=120, key=f"a_{q_idx}")
        
        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            if st.button("⬅️ Back", disabled=q_idx==0, use_container_width=True):
                st.session_state.q_index -= 1
        with c2:
            if st.button("👁️ Preview", use_container_width=True):
                st.session_state.show_preview = True
        with c3:
            if st.button("➡️ Next", disabled=q_idx==total-1, use_container_width=True):
                st.session_state.q_index += 1
        
        if st.session_state.get("show_preview"):
            st.subheader("Preview & Submit")
            df_prev = pd.DataFrame({
                "Question No.": list(range(1,total+1)),
                "Question": questions,
                "Answer": st.session_state.answers
            })
            st.dataframe(df_prev, use_container_width=True, hide_index=True)
            colp1, colp2 = st.columns([2,1])
            with colp2:
                if st.button("🟦 SUBMIT", use_container_width=True):
                    qa = [(i+1, questions[i], st.session_state.answers[i]) for i in range(total)]
                    save_answers(student_id.strip(), date_week.strip(), qa)
                    st.success("Your answers have been submitted successfully!")
                    # reset basic state for new submission
                    st.session_state.started = False
                    st.session_state.q_index = 0
                    st.session_state.answers = [""] * len(DEFAULT_QUESTIONS)
                    st.session_state.show_preview = False

# ------------- Teacher Tab -------------
with tab_teacher:
    st.subheader("Manage Questions & Check Answers")
    m1, m2 = st.columns([1,1])
    with m1:
        teacher_name = st.text_input("Teacher Name", placeholder="e.g., Ms. June")
    with m2:
        manage_date = st.text_input("Date / Week (for Question Set)", value=str(date.today()))
    
    # ---- Question Set Editor ----
    with st.expander("📝 Edit Question Set for this Date/Week", expanded=True):
        # existing sets dropdown
        existing_dates = list_question_dates()
        if existing_dates:
            st.caption("Load from saved sets:")
            load_select = st.selectbox("Saved dates", options=["(select)"] + existing_dates, index=0)
            if load_select != "(select)":
                manage_date = load_select
                st.session_state["tmp_questions"] = load_questions(manage_date)
        
        # temp state for editor
        if "tmp_questions" not in st.session_state:
            st.session_state["tmp_questions"] = load_questions(manage_date)
        
        # choose number of questions
        num = st.number_input("Number of questions", min_value=1, max_value=20, value=len(st.session_state["tmp_questions"]), step=1)
        # make sure list has correct size
        qlist = st.session_state["tmp_questions"]
        if len(qlist) < num:
            qlist = qlist + [""]*(num-len(qlist))
        elif len(qlist) > num:
            qlist = qlist[:num]
        # render inputs
        new_questions = []
        for i in range(num):
            new_questions.append(st.text_input(f"Q{i+1}", value=qlist[i], placeholder=f"Enter question {i+1}"))
        st.session_state["tmp_questions"] = new_questions
        
        cqs1, cqs2, cqs3 = st.columns([1,1,1])
        with cqs1:
            if st.button("💾 Save Question Set", use_container_width=True):
                save_question_set(manage_date.strip(), new_questions)
                st.success(f"Saved {len(new_questions)} questions for {manage_date}.")
        with cqs2:
            if st.button("🔄 Reset to Default", use_container_width=True):
                st.session_state["tmp_questions"] = DEFAULT_QUESTIONS.copy()
        with cqs3:
            if st.button("📥 Load Current Saved", use_container_width=True):
                st.session_state["tmp_questions"] = load_questions(manage_date.strip())
    
    st.divider()
    # ---- Checker ----
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        filter_date = st.text_input("Filter Date / Week", value=manage_date, placeholder="YYYY-MM-DD")
    with c2:
        student_search = st.text_input("Search Student ID", placeholder="e.g., S001")
    with c3:
        start_check = st.button("✅ START (Load)", use_container_width=True)
    
    if start_check:
        st.session_state.teacher_loaded = True
    
    if st.session_state.get("teacher_loaded"):
        df = load_answers(filter_date.strip() or None, student_search.strip())
        if df.empty:
            st.info("No data found. Try adjusting filters or ask students to submit.")
        else:
            st.write("Toggle ✅ to mark answers as checked.")
            edited = df.copy()
            edited["checked"] = edited["checked"].astype(bool)
            edited = st.data_editor(
                edited,
                column_config={
                    "checked": st.column_config.CheckboxColumn("check"),
                    "question_no": st.column_config.NumberColumn("question"),
                },
                disabled=["id", "student_id", "date_week", "question_no", "question", "answer"],
                hide_index=True,
                use_container_width=True,
                key="teacher_table"
            )
            # Determine which rows changed
            changed_to_true = edited[(edited["checked"] == True) & (df["checked"] == 0)]
            changed_to_false = edited[(edited["checked"] == False) & (df["checked"] == 1)]
            
            colu1, colu2, colu3 = st.columns([1,1,1])
            with colu1:
                if st.button("💾 Save Checks", use_container_width=True):
                    update_checked(changed_to_true["id"].tolist(), True)
                    update_checked(changed_to_false["id"].tolist(), False)
                    st.success("Saved check status.")
            with colu2:
                if st.button("☑️ Mark All as Checked", use_container_width=True):
                    update_checked(edited["id"].tolist(), True)
                    st.success("All rows marked as checked.")
            with colu3:
                csv = edited.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Export CSV", csv, file_name=f"answers_{filter_date or 'all'}.csv", mime="text/csv", use_container_width=True)

    st.caption("Tip: Manage questions by date/week. Students will load that set when they enter the same date/week.")

