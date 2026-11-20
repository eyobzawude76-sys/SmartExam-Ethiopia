"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Assignment = { subject_id: string; class_id: string; section_id: string; subject_name: string; class_name: string; section_name: string };
type Question = { _id: string; subject_id: string; class_id: string; section_id: string; question_text: string; options: string[]; points: number };
type Exam = { _id: string; title: string; subject_id: string; class_id: string; section_id: string; question_ids: string[]; questions_snapshot?: { question_id: string; question_text: string; options: string[]; correct_option: number; points: number }[]; duration_minutes: number; allow_retakes: boolean; status: string };
type Submission = { _id: string; student_id: string; student?: { full_name: string; username: string }; answers: { question_id: string; selected_option?: number }[]; status: string; score?: number; total_points?: number; result_published?: boolean };

export default function TeacherPage() {
  const [token, setToken] = useState("");
  const [mustChange, setMustChange] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [teacherName, setTeacherName] = useState("");
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [exams, setExams] = useState<Exam[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [selectedExam, setSelectedExam] = useState<Exam | null>(null);
  const [selectedAssignment, setSelectedAssignment] = useState("");
  const [questionText, setQuestionText] = useState("");
  const [options, setOptions] = useState(["", "", "", ""]);
  const [correctOption, setCorrectOption] = useState("0");
  const [points, setPoints] = useState("1");
  const [examTitle, setExamTitle] = useState("");
  const [examQuestions, setExamQuestions] = useState<string[]>([]);
  const [duration, setDuration] = useState("30");
  const [allowRetakes, setAllowRetakes] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [grading, setGrading] = useState<Record<string, Record<string, boolean>>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function request(path: string, method = "GET", body?: unknown) {
    const response = await fetch(API + path, {
      method,
      headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail ?? "Request failed");
    return data;
  }

  async function refresh() {
    const [dashboard, a, q, e] = await Promise.all([
      request("/teacher/dashboard"), request("/teacher/assignments"),
      request("/teacher/questions"), request("/teacher/exams"),
    ]);
    setTeacherName(dashboard.teacher.full_name);
    setAssignments(a);
    setQuestions(q);
    setExams(e);
    if (!selectedAssignment && dashboard.assignments.length) {
      const a = dashboard.assignments[0];
      setSelectedAssignment([a.subject_id, a.class_id, a.section_id].join("|"));
    }
  }

  useEffect(() => {
    const saved = window.sessionStorage.getItem("smartExamTeacherToken");
    const changeRequired = window.sessionStorage.getItem("smartExamTeacherMustChangePassword") === "true";
    if (saved) {
      // Restore the authenticated teacher session after hydration.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMustChange(changeRequired);
      setToken(saved);
    }
  }, []);

  useEffect(() => {
    // Authenticated state starts the teacher dashboard data load.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (token && !mustChange) refresh().catch(error => {
      setMessage(error instanceof Error ? error.message : "Session expired");
      setToken("");
      window.sessionStorage.removeItem("smartExamTeacherToken");
      window.sessionStorage.removeItem("smartExamTeacherMustChangePassword");
    });
    // Refresh only when the authenticated session becomes available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, mustChange]);

  function logout() {
    window.sessionStorage.removeItem("smartExamTeacherToken");
    window.sessionStorage.removeItem("smartExamTeacherMustChangePassword");
    setToken(""); setMustChange(false); setAssignments([]); setQuestions([]); setExams([]);
    setSubmissions([]); setSelectedExam(null); setTeacherName(""); setMessage("Baate.");
  }

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const response = await fetch(API + "/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail ?? "Login failed");
      if (data.user.role !== "TEACHER") throw new Error("Kun Teacher account miti.");
      window.sessionStorage.setItem("smartExamTeacherToken", data.access_token);
      window.sessionStorage.setItem("smartExamTeacherMustChangePassword", String(Boolean(data.user.must_change_password)));
      setMustChange(Boolean(data.user.must_change_password)); setToken(data.access_token); setPassword("");
      setMessage("Teacher seenteera.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Login failed"); }
    finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmPassword) { setMessage("Password haaraan wal hin siman."); return; }
    setBusy(true);
    try {
      await request("/auth/change-password", "POST", { current_password: currentPassword, new_password: newPassword });
      window.sessionStorage.setItem("smartExamTeacherMustChangePassword", "false");
      setMustChange(false); setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setMessage("Password jijjiirameera.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Password change failed"); }
    finally { setBusy(false); }
  }

  const assignmentParts = selectedAssignment.split("|");
  const currentAssignment = assignments.find(a => [a.subject_id, a.class_id, a.section_id].join("|") === selectedAssignment);

  async function createQuestion(event: FormEvent) {
    event.preventDefault(); if (!currentAssignment) return;
    setBusy(true); setMessage("");
    try {
      await request("/teacher/questions", "POST", {
        subject_id: currentAssignment.subject_id, class_id: currentAssignment.class_id,
        section_id: currentAssignment.section_id, question_text: questionText,
        options, correct_option: Number(correctOption), points: Number(points),
      });
      setQuestionText(""); setOptions(["", "", "", ""]); setCorrectOption("0"); setPoints("1");
      await refresh(); setMessage("Gaaffiin uumameera.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Question create failed"); }
    finally { setBusy(false); }
  }

  async function uploadCsv(event: FormEvent) {
    event.preventDefault(); if (!currentAssignment || !csvFile) return;
    setBusy(true); setMessage("");
    try {
      const form = new FormData(); form.append("file", csvFile);
      const query = new URLSearchParams({
        subject_id: currentAssignment.subject_id, class_id: currentAssignment.class_id,
        section_id: currentAssignment.section_id,
      });
      const response = await fetch(API + "/teacher/questions/upload-csv?" + query.toString(), {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail ?? "CSV upload failed");
      setCsvFile(null); await refresh(); setMessage(`Gaaffii ${data.created_count} olkaa'ame.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "CSV upload failed"); }
    finally { setBusy(false); }
  }

  async function createExam(event: FormEvent) {
    event.preventDefault(); if (!currentAssignment) return;
    setBusy(true); setMessage("");
    try {
      await request("/teacher/exams", "POST", {
        title: examTitle, subject_id: currentAssignment.subject_id, class_id: currentAssignment.class_id,
        section_id: currentAssignment.section_id, question_ids: examQuestions,
        duration_minutes: Number(duration), allow_retakes: allowRetakes,
      });
      setExamTitle(""); setExamQuestions([]); await refresh(); setMessage("Exam draft uumameera.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Exam create failed"); }
    finally { setBusy(false); }
  }

  async function publishExam(exam: Exam) {
    setBusy(true);
    try { await request(`/teacher/exams/${exam._id}/publish`, "POST"); await refresh(); setMessage("Exam publish ta'eera."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Publish failed"); }
    finally { setBusy(false); }
  }

  async function openSubmissions(exam: Exam) {
    setBusy(true); setSelectedExam(exam);
    try { setSubmissions(await request(`/teacher/exams/${exam._id}/submissions`)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Submissions load failed"); }
    finally { setBusy(false); }
  }

  async function gradeStudent(submission: Submission) {
    if (!selectedExam?.questions_snapshot) return;
    const selected = grading[submission._id] ?? {};
    if (selectedExam.questions_snapshot.some(q => selected[q.question_id] === undefined)) {
      setMessage("Deebii gaaffii hundaaf ✓ ykn X filadhu.");
      return;
    }
    const grades = selectedExam.questions_snapshot.map(q => ({
      question_id: q.question_id, is_correct: selected[q.question_id],
    }));
    setBusy(true);
    try {
      await request(`/teacher/submissions/${submission._id}/grade`, "PATCH", { grades });
      setMessage("Mark galmaa'eera. Bu'aa barataa kana amma maxxansuu dandeessa.");
      await openSubmissions(selectedExam);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Grading failed"); }
    finally { setBusy(false); }
  }

  async function publishResult(submission: Submission) {
    setBusy(true);
    try {
      await request(`/teacher/submissions/${submission._id}/publish-result`, "POST");
      if (selectedExam) await openSubmissions(selectedExam);
      setMessage("Bu'aan barataa kanaaf publish ta'eera.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Result publish failed"); }
    finally { setBusy(false); }
  }

  if (!token) return (
    <main className="admin-shell"><section className="admin-panel login-panel">
      <p className="eyebrow">SMARTEXAM ETHIOPIA</p><h1>Teacher Login</h1>
      <form className="stack" onSubmit={login}>
        <label>Username<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" required /></label>
        <label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" required /></label>
        <button disabled={busy}>{busy ? "Seenaa jira..." : "Login"}</button>
      </form>{message && <p className="feedback">{message}</p>}
    </section></main>
  );

  if (mustChange) return (
    <main className="admin-shell"><section className="admin-panel login-panel">
      <h1>Password Change Required</h1><p className="muted">Hojii jalqabuu dura password yeroo jalqabaa jijjiiri.</p>
      <form className="stack" onSubmit={changePassword}>
        <label>Temporary password<input type="password" value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} minLength={8} required /></label>
        <label>New password (12+)<input type="password" value={newPassword} onChange={e=>setNewPassword(e.target.value)} minLength={12} required /></label>
        <label>Confirm password<input type="password" value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} minLength={12} required /></label>
        <button disabled={busy}>Change password</button>
      </form><button className="secondary" type="button" onClick={logout}>Logout</button>
      {message && <p className="feedback">{message}</p>}
    </section></main>
  );

  return (
    <main className="admin-shell">
      <header className="admin-header"><div><p className="eyebrow">SMARTEXAM ETHIOPIA / V1</p><h1>Teacher Dashboard</h1><p className="muted">Baga nagaan dhuftan, {teacherName}.</p></div><button className="secondary" onClick={logout}>Logout</button></header>
      {message && <p className="feedback">{message}</p>}
      <section className="admin-panel stack">
        <h2>My Assigned Class / Section / Subject</h2>
        <select value={selectedAssignment} onChange={e=>{setSelectedAssignment(e.target.value);setExamQuestions([]);setSelectedExam(null);setSubmissions([]);}}>
          {assignments.map(a=><option key={[a.subject_id,a.class_id,a.section_id].join("|")} value={[a.subject_id,a.class_id,a.section_id].join("|")}>{a.subject_name} — {a.class_name} / {a.section_name}</option>)}
        </select>
        {!assignments.length && <p className="muted">Admin assignment hin kennamne. Admin qunnamii.</p>}
      </section>
      <section className="admin-grid">
        <article className="admin-panel"><h2>Create MCQ Question</h2>
          <form className="stack" onSubmit={createQuestion}>
            <label>Question<input value={questionText} onChange={e=>setQuestionText(e.target.value)} minLength={5} required /></label>
            {options.map((option,index)=><label key={index}>Option {String.fromCharCode(65+index)}<input value={option} onChange={e=>setOptions(old=>old.map((v,i)=>i===index?e.target.value:v))} required /></label>)}
            <label>Correct option<select value={correctOption} onChange={e=>setCorrectOption(e.target.value)}>{options.map((_,i)=><option key={i} value={i}>{String.fromCharCode(65+i)}</option>)}</select></label>
            <label>Points<input type="number" min="0.1" max="100" step="0.1" value={points} onChange={e=>setPoints(e.target.value)} required /></label>
            <button disabled={busy || !currentAssignment}>Save question</button>
          </form>
          <h3>CSV Upload</h3><p className="muted">Headers: question_text, option_a, option_b, option_c, option_d, correct_option, points</p>
          <form className="stack" onSubmit={uploadCsv}><input type="file" accept=".csv,text/csv" onChange={e=>setCsvFile(e.target.files?.[0] ?? null)} required /><button disabled={busy || !csvFile || !currentAssignment}>Upload CSV</button></form>
        </article>
        <article className="admin-panel"><h2>Create Exam</h2>
          <form className="stack" onSubmit={createExam}>
            <label>Exam title<input value={examTitle} onChange={e=>setExamTitle(e.target.value)} minLength={3} required /></label>
            <label>Duration (minutes)<input type="number" min="1" max="300" value={duration} onChange={e=>setDuration(e.target.value)} required /></label>
            <label className="inline-check"><input type="checkbox" checked={allowRetakes} onChange={e=>setAllowRetakes(e.target.checked)} /> Allow retakes</label>
            <p className="muted">Choose questions for this exam:</p>
            {questions.filter(q=>q.subject_id===assignmentParts[0] && q.class_id===assignmentParts[1] && q.section_id===assignmentParts[2]).map(q=><label className="inline-check" key={q._id}><input type="checkbox" checked={examQuestions.includes(q._id)} onChange={e=>setExamQuestions(old=>e.target.checked?[...old,q._id]:old.filter(id=>id!==q._id))} />{q.question_text} ({q.points} pt)</label>)}
            <button disabled={busy || !currentAssignment || !examQuestions.length}>Create exam draft</button>
          </form>
        </article>
      </section>
      <section className="admin-panel"><h2>My Questions ({questions.length})</h2><ul>{questions.map(q=><li key={q._id}>{q.question_text} <small>({q.points} pt)</small></li>)}</ul></section>
      <section className="admin-panel"><h2>My Exams</h2><ul>{exams.map(exam=><li key={exam._id} className="teacher-list-item"><span><strong>{exam.title}</strong><small>{exam.status} · {exam.duration_minutes} min · {exam.question_ids.length} questions</small></span><span className="teacher-actions">{exam.status==="draft" && <button disabled={busy} onClick={()=>publishExam(exam)}>Publish exam</button>}<button className="secondary" disabled={busy} onClick={()=>openSubmissions(exam)}>Submissions</button></span></li>)}</ul></section>
      {selectedExam && <section className="admin-panel"><h2>Submissions — {selectedExam.title}</h2>
        {!submissions.length && <p className="muted">Ammaaf submissions hin jiru.</p>}
        {submissions.map(sub=><article className="submission-card" key={sub._id}>
          <h3>{sub.student?.full_name ?? "Student"} (@{sub.student?.username ?? ""})</h3>
          <p className="muted">Status: {sub.status} · {sub.score ?? "—"} / {sub.total_points ?? "—"} · Result {sub.result_published ? "Published" : "Not published"}</p>
          {selectedExam.questions_snapshot?.map(q=>{
            const answer = sub.answers?.find(item=>item.question_id===q.question_id);
            const answerLabel = answer && typeof answer.selected_option === "number" ? q.options[answer.selected_option] ?? "Invalid option" : "No answer recorded";
            return <div className="grade-row" key={q.question_id}>
            <span>{q.question_text}<small>Correct answer: {q.options[q.correct_option] ?? "Unavailable"} · Student answer: {answerLabel} · {q.points} points</small></span>
            <select value={grading[sub._id]?.[q.question_id] === undefined ? "" : String(grading[sub._id][q.question_id])} onChange={e=>setGrading(old=>({...old,[sub._id]:{...(old[sub._id]??{}),[q.question_id]:e.target.value==="true"}}))}>
              <option value="">Choose ✓ / X</option><option value="false">X — Incorrect</option><option value="true">✓ — Correct</option>
            </select>
          </div>})}
          {sub.status!=="graded" && <button disabled={busy} onClick={()=>gradeStudent(sub)}>Save marks</button>}
          {sub.status==="graded" && !sub.result_published && <button disabled={busy} onClick={()=>publishResult(sub)}>Publish this student&apos;s result</button>}
        </article>)}
      </section>}
    </main>
  );
}
