"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Exam = { id: string; title: string; duration_minutes: number; question_count: number; total_points: number; subject_id: string };
type Question = { question_id: string; question_text: string; options: string[]; points: number };
type Result = { exam_id: string; exam_title: string; score: number; total_points: number; result_published_at?: string };

export default function StudentPage() {
  const [token, setToken] = useState("");
  const [mustChange, setMustChange] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [studentName, setStudentName] = useState("");
  const [exams, setExams] = useState<Exam[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [activeExam, setActiveExam] = useState<{ id: string; title: string; submissionId: string; deadline: string; questions: Question[] } | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [secondsLeft, setSecondsLeft] = useState(-1);
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
    const [dashboard, published] = await Promise.all([request("/student/dashboard"), request("/student/results")]);
    setStudentName(dashboard.student.full_name);
    setExams(dashboard.available_exams);
    setResults(published);
  }

  useEffect(() => {
    const saved = window.sessionStorage.getItem("smartExamStudentToken");
    const changeRequired = window.sessionStorage.getItem("smartExamStudentMustChangePassword") === "true";
    if (saved) {
      // Restore the authenticated student session after hydration.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMustChange(changeRequired);
      setToken(saved);
    }
  }, []);

  useEffect(() => {
    // Authenticated state starts the Student dashboard data load.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (token && !mustChange) refresh().catch(error => {
      setMessage(error instanceof Error ? error.message : "Session expired");
      setToken("");
      window.sessionStorage.removeItem("smartExamStudentToken");
      window.sessionStorage.removeItem("smartExamStudentMustChangePassword");
    });
    // Refresh only when the authenticated session becomes available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, mustChange]);

  useEffect(() => {
    if (!activeExam) return;
    const update = () => setSecondsLeft(Math.max(0, Math.ceil((new Date(activeExam.deadline).getTime() - Date.now()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [activeExam]);

  useEffect(() => {
    if (activeExam && secondsLeft === 0) {
      // Timer expiry submits the currently saved answers through the API.
      submitExam(true).catch(error => setMessage(error instanceof Error ? error.message : "Auto-submit failed"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [secondsLeft, activeExam]);

  function logout() {
    window.sessionStorage.removeItem("smartExamStudentToken");
    window.sessionStorage.removeItem("smartExamStudentMustChangePassword");
    setToken(""); setMustChange(false); setExams([]); setResults([]);
    setActiveExam(null); setAnswers({}); setStudentName(""); setMessage("Baate.");
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
      if (data.user.role !== "STUDENT") throw new Error("Kun Student account miti.");
      window.sessionStorage.setItem("smartExamStudentToken", data.access_token);
      window.sessionStorage.setItem("smartExamStudentMustChangePassword", String(Boolean(data.user.must_change_password)));
      setMustChange(Boolean(data.user.must_change_password)); setToken(data.access_token); setPassword("");
      setMessage("Student seenteera.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Login failed"); }
    finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmPassword) { setMessage("Password haaraan wal hin siman."); return; }
    setBusy(true);
    try {
      await request("/auth/change-password", "POST", { current_password: currentPassword, new_password: newPassword });
      window.sessionStorage.setItem("smartExamStudentMustChangePassword", "false");
      setMustChange(false); setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setMessage("Password jijjiirameera.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Password change failed"); }
    finally { setBusy(false); }
  }

  async function startExam(exam: Exam) {
    setBusy(true); setMessage("");
    try {
      const data = await request(`/student/exams/${exam.id}/start`, "POST");
      const initial: Record<string, number> = {};
      for (const answer of data.answers ?? []) initial[answer.question_id] = answer.selected_option;
      setAnswers(initial);
      setSecondsLeft(-1);
      setActiveExam({ id: exam.id, title: exam.title, submissionId: data.submission_id, deadline: data.deadline_at, questions: data.questions });
    } catch (error) { setMessage(error instanceof Error ? error.message : "Exam start failed"); await refresh(); }
    finally { setBusy(false); }
  }

  async function chooseAnswer(questionId: string, selectedOption: number) {
    if (!activeExam) return;
    const next = { ...answers, [questionId]: selectedOption };
    setAnswers(next);
    try {
      await request(`/student/submissions/${activeExam.submissionId}/answers`, "PATCH", {
        answers: Object.entries(next).map(([question_id, selected_option]) => ({ question_id, selected_option })),
      });
    } catch (error) { setMessage(error instanceof Error ? error.message : "Answer save failed"); }
  }

  async function submitExam(automatic = false) {
    if (!activeExam || busy) return;
    setBusy(true);
    try {
      await request(`/student/submissions/${activeExam.submissionId}/submit`, "POST");
      setActiveExam(null); setAnswers({});
      setMessage(automatic ? "Yeroon xumurameera. Deebiiwwan kee submit ta'aniiru." : "Qormaata xumurteetta.");
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Submit failed"); }
    finally { setBusy(false); }
  }

  const timeText = `${Math.floor(secondsLeft / 60).toString().padStart(2, "0")}:${(secondsLeft % 60).toString().padStart(2, "0")}`;

  if (!token) return (
    <main className="admin-shell"><section className="admin-panel login-panel">
      <p className="eyebrow">SMARTEXAM ETHIOPIA</p><h1>Student Login</h1>
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
      <header className="admin-header"><div><p className="eyebrow">SMARTEXAM ETHIOPIA / V1</p><h1>Student Dashboard</h1><p className="muted">Baga nagaan dhuftan, {studentName}.</p></div><button className="secondary" onClick={logout}>Logout</button></header>
      {message && <p className="feedback">{message}</p>}
      {activeExam ? <section className="admin-panel">
        <div className="admin-header"><div><h2>{activeExam.title}</h2><p className="muted">Deebii kee filadhu; yeroo dhumu ofumaan submit ta&apos;a.</p></div><strong className="exam-timer">{timeText}</strong></div>
        {activeExam.questions.map((question,index)=><article className="submission-card" key={question.question_id}>
          <h3>{index+1}. {question.question_text}</h3><p className="muted">{question.points} points</p>
          {question.options.map((option,optionIndex)=><label className="inline-check" key={optionIndex}>
            <input type="radio" name={question.question_id} checked={answers[question.question_id]===optionIndex} onChange={()=>chooseAnswer(question.question_id,optionIndex)} />
            {String.fromCharCode(65+optionIndex)}. {option}
          </label>)}
        </article>)}
        <button disabled={busy} onClick={()=>submitExam(false)}>Submit exam</button>
      </section> : <>
        <section className="admin-panel"><h2>Available Exams</h2>
          {!exams.length && <p className="muted">Ammaaf qormaanni siif hin jiru.</p>}
          <ul>{exams.map(exam=><li className="teacher-list-item" key={exam.id}>
            <span><strong>{exam.title}</strong><small>{exam.question_count} questions · {exam.duration_minutes} minutes · {exam.total_points} points</small></span>
            <button disabled={busy} onClick={()=>startExam(exam)}>Start exam</button>
          </li>)}</ul>
        </section>
        <section className="admin-panel"><h2>Published Results</h2>
          {!results.length && <p className="muted">Bu&apos;aan ammaaf hin maxxanfamne.</p>}
          <ul>{results.map((result,index)=><li key={result.exam_id+index}>
            <strong>{result.exam_title}</strong> — {result.score} / {result.total_points}
          </li>)}</ul>
        </section>
      </>}
    </main>
  );
}
