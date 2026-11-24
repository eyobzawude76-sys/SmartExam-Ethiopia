"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { oromoErrorMessage } from "../oromo-errors";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Exam = { id: string; title: string; duration_minutes: number; question_count: number; total_points: number; subject_id: string };
type Question = { question_id: string; question_text: string; options: string[]; points: number };
type Result = { submission_id: string; exam_id: string; exam_title: string; score: number; total_points: number; result_published_at?: string };
type ResultDetail = { submission_id: string; exam_title: string; score: number; total_points: number; questions: Array<{ question_id: string; question_text: string; options: string[]; selected_option: number | null; is_correct: boolean | null; correct_option: number | null; points_awarded: number; points: number }> };

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
  const [selectedResult, setSelectedResult] = useState<ResultDetail | null>(null);
  const [activeExam, setActiveExam] = useState<{ id: string; title: string; submissionId: string; deadline: string; questions: Question[] } | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [secondsLeft, setSecondsLeft] = useState(-1);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const answerSaveQueue = useRef<Promise<void>>(Promise.resolve());

  async function request(path: string, method = "GET", body?: unknown) {
    let response: Response;
    try {
      response = await fetch(API + path, {
        method,
        headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    } catch (error) {
      throw new Error(oromoErrorMessage(error, "Serverii waliin wal qunnamuu hin dandeenye. Intarneetii kee mirkaneeffadhu."));
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(oromoErrorMessage(`${response.status} ${data.detail ?? data.error ?? ""}`, "Gaaffii kee raawwachuun hin danda'amne. Odeeffannoo galchite mirkaneeffadhu."));
    }
    return data;
  }

  async function refresh() {
    const [dashboard, published] = await Promise.all([request("/student/dashboard"), request("/student/results")]);
    setStudentName(dashboard.student.full_name);
    setExams(dashboard.available_exams);
    setResults(published);
  }

  async function submitExam(automatic = false) {
    if (!activeExam || busy) return;
    setBusy(true);
    try {
      // Wait for queued saves, but still call submit if a final save was rejected
      // because the deadline elapsed (the backend may already have auto-submitted).
      await answerSaveQueue.current.catch(() => undefined);
      const completedExamId = activeExam.id;
      await request(`/student/submissions/${activeExam.submissionId}/submit`, "POST");
      // Remove it immediately from this student's view after the server confirms submission.
      setExams(current => current.filter(exam => exam.id !== completedExamId));
      setActiveExam(null); setAnswers({});
      setMessage(automatic ? "Yeroon xumurameera. Deebiiwwan kee ergameera. Qormaanni kun tarree qormaata jiran keessaa haqameera." : "Qormaata xumurteetta. Qormaanni kun tarree qormaata jiran keessaa haqameera.");
      await refresh();
    } catch (error) { setMessage(oromoErrorMessage(error, "Qormaata erguu hin dandeenye. Intarneetii kee mirkaneeffadhuutii irra deebi'ii yaali.")); }
    finally { setBusy(false); }
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
      setMessage(oromoErrorMessage(error, "Yeroon seensaa kee xumurameera. Irra deebi'ii seeni."));
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
    if (!activeExam || secondsLeft !== 0) return;
    // Defer submission to the timer callback rather than setting state in the effect body.
    const timeout = window.setTimeout(() => {
      submitExam(true).catch(error => setMessage(oromoErrorMessage(error, "Qormaata yeroo isaa xumuruun ofumaan erguu hin dandeenye. Maaloo barsiisaa qunnami.")));
    }, 0);
    return () => window.clearTimeout(timeout);
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
      if (!response.ok) throw new Error(oromoErrorMessage(`${response.status} ${data.detail ?? data.error ?? ""}`, "Seenuun hin milkoofne. Username fi password kee mirkaneeffadhu."));
      if (data.user.role !== "STUDENT") throw new Error("Kun Student account miti.");
      window.sessionStorage.setItem("smartExamStudentToken", data.access_token);
      window.sessionStorage.setItem("smartExamStudentMustChangePassword", String(Boolean(data.user.must_change_password)));
      setMustChange(Boolean(data.user.must_change_password)); setToken(data.access_token); setPassword("");
      setMessage("Student seenteera.");
    } catch (error) { setMessage(oromoErrorMessage(error, "Seenuun hin milkoofne. Username fi password kee mirkaneeffadhu.")); }
    finally { setBusy(false); }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmPassword) { setMessage("Password haaraan wal hin siman."); return; }
    setBusy(true);
    try {
      const changed = await request("/auth/change-password", "POST", { current_password: currentPassword, new_password: newPassword });
      window.sessionStorage.setItem("smartExamStudentToken", changed.access_token);
      setToken(changed.access_token);
      window.sessionStorage.setItem("smartExamStudentMustChangePassword", "false");
      setMustChange(false); setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setMessage("Password jijjiirameera.");
    } catch (error) { setMessage(oromoErrorMessage(error, "Password jijjiiruu hin dandeenye. Password durii fi haaraa mirkaneeffadhu.")); }
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
    } catch (error) { setMessage(oromoErrorMessage(error, "Qormaata jalqabuu hin dandeenye. Yeroo qormaataa fi ramaddii kee mirkaneeffadhu.")); await refresh(); }
    finally { setBusy(false); }
  }

  async function chooseAnswer(questionId: string, selectedOption: number) {
    if (!activeExam) return;
    const next = { ...answers, [questionId]: selectedOption };
    setAnswers(next);
    // Serialize full-answer snapshots so a slower older request cannot overwrite a newer choice.
    answerSaveQueue.current = answerSaveQueue.current.catch(() => undefined).then(async () => {
      await request(`/student/submissions/${activeExam.submissionId}/answers`, "PATCH", {
        answers: Object.entries(next).map(([question_id, selected_option]) => ({ question_id, selected_option })),
      });
    });
    try {
      await answerSaveQueue.current;
    } catch (error) { setMessage(oromoErrorMessage(error, "Deebii kee olkaa'uu hin dandeenye. Intarneetii kee mirkaneeffadhuutii irra deebi'ii yaali.")); }
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
        <section className="admin-panel"><h2>Bu'aa Maxxanfame</h2>
          {!results.length && <p className="muted">Bu'aan ammaaf hin maxxanfamne.</p>}
          <ul>{results.map(result=><li className="teacher-list-item" key={result.submission_id}>
            <span><strong>{result.exam_title}</strong><small>{result.score} / {result.total_points} qabxii</small></span>
            <button className="secondary" disabled={busy} onClick={async()=>{
              setBusy(true); setMessage("");
              try { setSelectedResult(await request(`/student/results/${result.submission_id}/details`)); }
              catch(error) { setMessage(oromoErrorMessage(error, "Bal'ina deebii ilaaluun hin danda'amne.")); }
              finally { setBusy(false); }
            }}>Deebii bal'inaan ilaali</button>
          </li>)}</ul>
          {selectedResult && <article className="submission-card">
            <div className="admin-header"><div><h3>{selectedResult.exam_title}</h3><p className="muted">Bu'aa: {selectedResult.score} / {selectedResult.total_points}</p></div>
              <button className="secondary" onClick={()=>setSelectedResult(null)}>Cufi</button></div>
            {selectedResult.questions.map((question,index)=>{
              const selectedText = question.selected_option === null ? "Deebii hin kennine" : question.options[question.selected_option] ?? "Deebii hin argamne";
              const correctText = question.correct_option === null ? null : question.options[question.correct_option] ?? null;
              return <div className="submission-card" key={question.question_id}>
                <h4>{index+1}. {question.question_text}</h4>
                <p><strong>Deebii kee:</strong> {selectedText}</p>
                <p><strong>Haala deebii:</strong> {question.is_correct === true ? "✓ Sirrii" : question.is_correct === false ? "✗ Dogoggora" : "Barsiisaan hin mirkaneessine"}</p>
                {correctText !== null && <p><strong>Deebii sirrii:</strong> {correctText}</p>}
                <p className="muted">Qabxii: {question.points_awarded} / {question.points}</p>
              </div>;
            })}
          </article>}
        </section>
      </>}
    </main>
  );
}
