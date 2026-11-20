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
  const [selectedExamAssignment, setSelectedExamAssignment] = useState("");
  const [selectedQuestionSource, setSelectedQuestionSource] = useState("");
  const [distributedExamIds, setDistributedExamIds] = useState<string[]>([]);
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
    if (dashboard.assignments.length) {
      const first = dashboard.assignments[0];
      const firstKey = [first.subject_id, first.class_id, first.section_id].join("|");
      setSelectedAssignment(current => current || firstKey);
      setSelectedExamAssignment(current => current || firstKey);
      setSelectedQuestionSource(current => current || firstKey);
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

  const assignmentParts = selectedExamAssignment.split("|");
  const examTargets = selectedExamAssignment === "__ALL__"
    ? assignments
    : assignments.filter(a => [a.subject_id, a.class_id, a.section_id].join("|") === selectedExamAssignment);
  const questionTargets = selectedAssignment === "__ALL__"
    ? assignments
    : assignments.filter(a => [a.subject_id, a.class_id, a.section_id].join("|") === selectedAssignment);

  async function createQuestion(event: FormEvent) {
    event.preventDefault(); if (!questionTargets.length) return;
    setBusy(true); setMessage("");
    let created = 0;
    try {
      for (const target of questionTargets) {
        await request("/teacher/questions", "POST", {
          subject_id: target.subject_id, class_id: target.class_id,
          section_id: target.section_id, question_text: questionText,
          options, correct_option: Number(correctOption), points: Number(points),
        });
        created += 1;
      }
      setQuestionText(""); setOptions(["", "", "", ""]); setCorrectOption("0"); setPoints("1");
      await refresh(); setMessage(`Gaaffiin assignment ${created} irratti galmaa'eera.`);
    } catch (error) {
      if (created) await refresh().catch(() => undefined);
      const detail = error instanceof Error ? error.message : "Question create failed";
      setMessage(created ? `${detail}. Gaaffiin assignment ${created} irratti galmaa'eera; hafan hin milkoofne.` : detail);
    }
    finally { setBusy(false); }
  }

  async function uploadCsv(event: FormEvent) {
    event.preventDefault(); if (!questionTargets.length || !csvFile) return;
    setBusy(true); setMessage("");
    let imported = 0;
    let completedTargets = 0;
    try {
      for (const target of questionTargets) {
        const form = new FormData(); form.append("file", csvFile);
        const query = new URLSearchParams({
          subject_id: target.subject_id, class_id: target.class_id,
          section_id: target.section_id,
        });
        const response = await fetch(API + "/teacher/questions/upload-csv?" + query.toString(), {
          method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail ?? `CSV upload failed after ${completedTargets} assignments`);
        imported += Number(data.created_count ?? 0);
        completedTargets += 1;
      }
      setCsvFile(null); await refresh(); setMessage(`${imported} gaaffii assignment ${completedTargets} irratti galmaa'e.`);
    } catch (error) {
      if (completedTargets) await refresh().catch(() => undefined);
      const detail = error instanceof Error ? error.message : "CSV upload failed";
      setMessage(completedTargets ? `${detail}. Gaaffii ${imported} assignment ${completedTargets} irratti galmaa'eera; hafan hin milkoofne.` : detail);
    }
    finally { setBusy(false); }
  }

  async function createExam(event: FormEvent) {
    event.preventDefault(); if (!examTargets.length) return;
    setBusy(true); setMessage("");
    const createdIds: string[] = [];
    try {
      if (selectedExamAssignment === "__ALL__") {
        const source = assignments.find(a => [a.subject_id, a.class_id, a.section_id].join("|") === selectedQuestionSource);
        if (!source) throw new Error("Question source assignment filadhu.");
        const result = await request("/teacher/exams/distribute", "POST", {
          title: examTitle,
          source_assignment: { subject_id: source.subject_id, class_id: source.class_id, section_id: source.section_id },
          target_assignments: examTargets.map(a => ({ subject_id: a.subject_id, class_id: a.class_id, section_id: a.section_id })),
          question_ids: examQuestions, duration_minutes: Number(duration), allow_retakes: allowRetakes,
        });
        createdIds.push(...result.created_exam_ids);
      } else {
        const target = examTargets[0];
        const created = await request("/teacher/exams", "POST", {
          title: examTitle, subject_id: target.subject_id, class_id: target.class_id,
          section_id: target.section_id, question_ids: examQuestions,
          duration_minutes: Number(duration), allow_retakes: allowRetakes,
        });
        createdIds.push(created._id);
      }
      setDistributedExamIds(createdIds);
      setExamTitle(""); setExamQuestions([]); await refresh();
      setMessage(`Exam draft ${createdIds.length} assignment irratti uumameera. Amma hundaa waliin publish gochuu dandeessa.`);
    } catch (error) {
      setDistributedExamIds(createdIds);
      if (createdIds.length) await refresh().catch(() => undefined);
      const detail = error instanceof Error ? error.message : "Exam create failed";
      setMessage(createdIds.length ? `${detail}. Exam draft ${createdIds.length} assignment irratti uumameera; hafan hin milkoofne.` : detail);
    }
    finally { setBusy(false); }
  }

  async function publishDistributedExams() {
    if (!distributedExamIds.length) return;
    setBusy(true); setMessage("");
    try {
      const result = await request("/teacher/exams/publish-batch", "POST", { exam_ids: distributedExamIds });
      setDistributedExamIds([]);
      await refresh();
      setMessage(`Exam ${result.published_count} assignment irratti publish ta'eera.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Bulk publish failed"); }
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
        <h2>Question Destination — Assignment</h2>
        <select value={selectedAssignment} onChange={e=>setSelectedAssignment(e.target.value)}>
          <option value="__ALL__">All My Assignments</option>
          {assignments.map(a=><option key={[a.subject_id,a.class_id,a.section_id].join("|")} value={[a.subject_id,a.class_id,a.section_id].join("|")}>{a.subject_name} — {a.class_name} / {a.section_name}</option>)}
        </select>
        <p className="muted">{selectedAssignment === "__ALL__" ? `Gaaffiin assignment ${assignments.length} hundaaf galmaa'a.` : "Gaaffiin assignment filatame qofaaf galmaa'a."}</p>
        <h2>Exam Destination — One Assignment</h2>
        <select value={selectedExamAssignment} onChange={e=>{setSelectedExamAssignment(e.target.value);setExamQuestions([]);setSelectedExam(null);setSubmissions([]);}}>
          <option value="__ALL__">All My Assignments</option>
          {assignments.map(a=><option key={[a.subject_id,a.class_id,a.section_id].join("|")} value={[a.subject_id,a.class_id,a.section_id].join("|")}>{a.subject_name} — {a.class_name} / {a.section_name}</option>)}
        </select>
        <p className="muted">{selectedExamAssignment === "__ALL__" ? "Qormaata kana assignment hundaaf clone gochuun uuma." : "Qormaata kana assignment filatame qofaaf uuma."}</p>
        {!assignments.length && <p className="muted">Admin assignment hin kennamne. Admin qunnamii.</p>}
      </section>
      <section className="admin-grid">
        <article className="admin-panel"><h2>Create MCQ Question</h2>
          <form className="stack" onSubmit={createQuestion}>
            <label>Question<input value={questionText} onChange={e=>setQuestionText(e.target.value)} minLength={5} required /></label>
            {options.map((option,index)=><label key={index}>Option {String.fromCharCode(65+index)}<input value={option} onChange={e=>setOptions(old=>old.map((v,i)=>i===index?e.target.value:v))} required /></label>)}
            <label>Correct option<select value={correctOption} onChange={e=>setCorrectOption(e.target.value)}>{options.map((_,i)=><option key={i} value={i}>{String.fromCharCode(65+i)}</option>)}</select></label>
            <label>Points<input type="number" min="0.1" max="100" step="0.1" value={points} onChange={e=>setPoints(e.target.value)} required /></label>
            <button disabled={busy || !questionTargets.length}>Save question</button>
          </form>
          <h3>CSV Upload</h3><p className="muted">Headers: question_text, option_a, option_b, option_c, option_d, correct_option, points</p>
          <form className="stack" onSubmit={uploadCsv}><input type="file" accept=".csv,text/csv" onChange={e=>setCsvFile(e.target.files?.[0] ?? null)} required /><button disabled={busy || !csvFile || !questionTargets.length}>Upload CSV</button></form>
        </article>
        <article className="admin-panel"><h2>Create Exam</h2>
          <form className="stack" onSubmit={createExam}>
            <label>Exam title<input value={examTitle} onChange={e=>setExamTitle(e.target.value)} minLength={3} required /></label>
            <label>Duration (minutes)<input type="number" min="1" max="300" value={duration} onChange={e=>setDuration(e.target.value)} required /></label>
            <label className="inline-check"><input type="checkbox" checked={allowRetakes} onChange={e=>setAllowRetakes(e.target.checked)} /> Allow retakes</label>
            {selectedExamAssignment === "__ALL__" && <label>Question Source Assignment<select value={selectedQuestionSource} onChange={e=>{setSelectedQuestionSource(e.target.value);setExamQuestions([]);}}>{assignments.map(a=><option key={[a.subject_id,a.class_id,a.section_id].join("|")} value={[a.subject_id,a.class_id,a.section_id].join("|")}>{a.subject_name} — {a.class_name} / {a.section_name}</option>)}</select></label>}
            <p className="muted">Gaaffilee assignment source filatame keessaa filadhu. Sirni isaanii qormaata Assignment hundaaf adda addaan uuma.</p>
            {questions.filter(q=>q.subject_id===(selectedExamAssignment==="__ALL__"?selectedQuestionSource.split("|")[0]:assignmentParts[0]) && q.class_id===(selectedExamAssignment==="__ALL__"?selectedQuestionSource.split("|")[1]:assignmentParts[1]) && q.section_id===(selectedExamAssignment==="__ALL__"?selectedQuestionSource.split("|")[2]:assignmentParts[2])).map(q=><label className="inline-check" key={q._id}><input type="checkbox" checked={examQuestions.includes(q._id)} onChange={e=>setExamQuestions(old=>e.target.checked?[...old,q._id]:old.filter(id=>id!==q._id))} />{q.question_text} ({q.points} pt)</label>)}
            <button disabled={busy || !examTargets.length || !examQuestions.length}>Create exam draft</button>
            {selectedExamAssignment === "__ALL__" && <p className="muted">Hubadhu: gaaffileen source assignment irraa filataman assignment hundaaf copy ta'u.</p>}
          </form>
        </article>
      </section>
      <section className="admin-panel"><h2>My Questions ({questions.length})</h2><ul>{questions.map(q=><li key={q._id}>{q.question_text} <small>({q.points} pt)</small></li>)}</ul></section>
      <section className="admin-panel"><h2>My Exams</h2>{distributedExamIds.length > 0 && <button disabled={busy} onClick={publishDistributedExams}>Publish all distributed exams ({distributedExamIds.length})</button>}<ul>{exams.map(exam=><li key={exam._id} className="teacher-list-item"><span><strong>{exam.title}</strong><small>{exam.status} · {exam.duration_minutes} min · {exam.question_ids.length} questions</small></span><span className="teacher-actions">{exam.status==="draft" && <button disabled={busy} onClick={()=>publishExam(exam)}>Publish exam</button>}<button className="secondary" disabled={busy} onClick={()=>openSubmissions(exam)}>Submissions</button></span></li>)}</ul></section>
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
