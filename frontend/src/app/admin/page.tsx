"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Item = { _id: string; id?: string; name: string; code?: string; class_id?: string };
type User = { _id: string; username: string; full_name: string; role: string; is_active: boolean };

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [subjects, setSubjects] = useState<Item[]>([]);
  const [classes, setClasses] = useState<Item[]>([]);
  const [sections, setSections] = useState<Item[]>([]);
  const [teachers, setTeachers] = useState<User[]>([]);
  const [students, setStudents] = useState<User[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [subjectName, setSubjectName] = useState("");
  const [subjectCode, setSubjectCode] = useState("");
  const [className, setClassName] = useState("");
  const [sectionClass, setSectionClass] = useState("");
  const [sectionName, setSectionName] = useState("");
  const [teacherName, setTeacherName] = useState("");
  const [teacherUsername, setTeacherUsername] = useState("");
  const [teacherPassword, setTeacherPassword] = useState("");
  const [teacherSubject, setTeacherSubject] = useState("");
  const [teacherClass, setTeacherClass] = useState("");
  const [teacherSection, setTeacherSection] = useState("");
  const [assignmentTeacher, setAssignmentTeacher] = useState("");
  const [assignmentSubject, setAssignmentSubject] = useState("");
  const [assignmentClass, setAssignmentClass] = useState("");
  const [assignmentSection, setAssignmentSection] = useState("");
  const [studentName, setStudentName] = useState("");
  const [studentUsername, setStudentUsername] = useState("");
  const [studentPassword, setStudentPassword] = useState("");
  const [studentClass, setStudentClass] = useState("");
  const [studentSection, setStudentSection] = useState("");

  async function request(path: string, method = "GET", body?: unknown) {
    const response = await fetch(API + path, {
      method,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail ?? "Request failed");
    return data;
  }

  async function refresh() {
    const [dashboard, s, c, sec, t, st] = await Promise.all([
      request("/admin/dashboard"), request("/admin/subjects"), request("/admin/classes"),
      request("/admin/sections"), request("/admin/teachers"), request("/admin/students"),
    ]);
    setCounts(dashboard.counts); setSubjects(s); setClasses(c); setSections(sec); setTeachers(t); setStudents(st);
  }

  useEffect(() => {
    const saved = window.sessionStorage.getItem("smartExamAdminToken");
    if (saved) setToken(saved);
  }, []);

  useEffect(() => {
    if (token) refresh().catch((error) => { setMessage(error.message); setToken(""); window.sessionStorage.removeItem("smartExamAdminToken"); });
    // Refresh only when authentication changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const data = await request("/auth/login", "POST", { username, password });
      if (data.user.role !== "ADMIN") throw new Error("This account is not an Admin account.");
      window.sessionStorage.setItem("smartExamAdminToken", data.access_token);
      setToken(data.access_token); setPassword(""); setMessage("Admin seente.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Login failed"); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent, path: string, body: unknown, success: string, reset?: () => void) {
    event.preventDefault(); setBusy(true); setMessage("");
    try { const result = await request(path, "POST", body); reset?.(); await refresh(); setMessage(result.temporary_password_once ? `${success} Username: ${result.teacher?.username ?? result.student?.username}. Temporary password (save it now): ${result.temporary_password_once}` : success); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Request failed"); }
    finally { setBusy(false); }
  }

  function logout() {
    window.sessionStorage.removeItem("smartExamAdminToken"); setToken(""); setCounts({}); setMessage("Baate.");
  }

  if (!token) return (
    <main className="admin-shell"><section className="admin-panel login-panel">
      <p className="eyebrow">SMARTEXAM ETHIOPIA</p><h1>Admin Login</h1>
      <p className="muted">Seensa Admin qofa. Teacher fi Student account hin fayyadamin.</p>
      <form onSubmit={login} className="stack">
        <label>Username<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required /></label>
        <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        <button disabled={busy}>{busy ? "Seenaa jira..." : "Login"}</button>
      </form>{message && <p className="feedback">{message}</p>}
    </section></main>
  );

  return (
    <main className="admin-shell">
      <header className="admin-header"><div><p className="eyebrow">SMARTEXAM ETHIOPIA / V1</p><h1>Admin Dashboard</h1><p className="muted">School setup fi user management qofa.</p></div><button className="secondary" onClick={logout}>Logout</button></header>
      {message && <p className="feedback">{message}</p>}
      <section className="stats-grid">{Object.entries(counts).map(([key,value]) => <article className="stat" key={key}><span>{key.replaceAll("_"," ")}</span><strong>{value}</strong></article>)}</section>
      <section className="admin-grid">
        <article className="admin-panel"><h2>Subjects</h2><form className="stack" onSubmit={e => submit(e,"/admin/subjects",{name:subjectName,code:subjectCode},"Subject created.",()=>{setSubjectName("");setSubjectCode("");})}><label>Subject name<input value={subjectName} onChange={e=>setSubjectName(e.target.value)} required /></label><label>Subject code<input value={subjectCode} onChange={e=>setSubjectCode(e.target.value)} required /></label><button disabled={busy}>Add subject</button></form><ul>{subjects.map(x=><li key={x._id}>{x.name} <small>{x.code}</small></li>)}</ul></article>
        <article className="admin-panel"><h2>Classes</h2><form className="stack" onSubmit={e => submit(e,"/admin/classes",{name:className},"Class created.",()=>setClassName(""))}><label>Class name<input placeholder="Grade 11" value={className} onChange={e=>setClassName(e.target.value)} required /></label><button disabled={busy}>Add class</button></form><ul>{classes.map(x=><li key={x._id}>{x.name}</li>)}</ul></article>
        <article className="admin-panel"><h2>Sections</h2><form className="stack" onSubmit={e => submit(e,"/admin/sections",{class_id:sectionClass,name:sectionName},"Section created.",()=>setSectionName(""))}><label>Class<select value={sectionClass} onChange={e=>setSectionClass(e.target.value)} required><option value="">Select class</option>{classes.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Section name<input placeholder="11-A" value={sectionName} onChange={e=>setSectionName(e.target.value)} required /></label><button disabled={busy || !sectionClass}>Add section</button></form><ul>{sections.map(x=><li key={x._id}>{classes.find(c=>c._id===x.class_id)?.name ?? "Class"} — {x.name}</li>)}</ul></article>
        <article className="admin-panel"><h2>Create Teacher</h2><form className="stack" onSubmit={e=>submit(e,"/admin/teachers",{full_name:teacherName,username:teacherUsername,temporary_password:teacherPassword,assignments:[{subject_id:teacherSubject,class_id:teacherClass,section_id:teacherSection}]},"Teacher account created.",()=>{setTeacherName("");setTeacherUsername("");setTeacherPassword("");})}><label>Full name<input value={teacherName} onChange={e=>setTeacherName(e.target.value)} required /></label><label>Username<input value={teacherUsername} onChange={e=>setTeacherUsername(e.target.value)} required /></label><label>Temporary password (12+ characters)<input type="password" minLength={12} value={teacherPassword} onChange={e=>setTeacherPassword(e.target.value)} required /></label><label>Subject<select value={teacherSubject} onChange={e=>setTeacherSubject(e.target.value)} required><option value="">Select subject</option>{subjects.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Class<select value={teacherClass} onChange={e=>{setTeacherClass(e.target.value);setTeacherSection("");}} required><option value="">Select class</option>{classes.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Section<select value={teacherSection} onChange={e=>setTeacherSection(e.target.value)} required><option value="">Select section</option>{sections.filter(x=>x.class_id===teacherClass).map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><button disabled={busy}>Create teacher</button></form><ul>{teachers.map(x=><li key={x._id}>{x.full_name} <small>@{x.username}</small></li>)}</ul></article>
        <article className="admin-panel"><h2>Add Teacher Assignment</h2><p className="muted">Barsiisaa duraan jiruuf subject, class fi section dabalataa ramadi.</p><form className="stack" onSubmit={e=>submit(e,`/admin/teachers/${assignmentTeacher}/assignments`,{subject_id:assignmentSubject,class_id:assignmentClass,section_id:assignmentSection},"Teacher assignment added.",()=>{setAssignmentSubject("");setAssignmentSection("");})}><label>Teacher<select value={assignmentTeacher} onChange={e=>setAssignmentTeacher(e.target.value)} required><option value="">Select teacher</option>{teachers.map(x=><option key={x._id} value={x._id}>{x.full_name} (@{x.username})</option>)}</select></label><label>Subject<select value={assignmentSubject} onChange={e=>setAssignmentSubject(e.target.value)} required><option value="">Select subject</option>{subjects.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Class<select value={assignmentClass} onChange={e=>{setAssignmentClass(e.target.value);setAssignmentSection("");}} required><option value="">Select class</option>{classes.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Section<select value={assignmentSection} onChange={e=>setAssignmentSection(e.target.value)} required><option value="">Select section</option>{sections.filter(x=>x.class_id===assignmentClass).map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><button disabled={busy || !assignmentTeacher}>Add assignment</button></form></article>
        <article className="admin-panel"><h2>Create Student</h2><form className="stack" onSubmit={e=>submit(e,"/admin/students",{full_name:studentName,username:studentUsername,temporary_password:studentPassword,class_id:studentClass,section_id:studentSection},"Student account created.",()=>{setStudentName("");setStudentUsername("");setStudentPassword("");})}><label>Full name<input value={studentName} onChange={e=>setStudentName(e.target.value)} required /></label><label>Username<input value={studentUsername} onChange={e=>setStudentUsername(e.target.value)} required /></label><label>Temporary password (12+ characters)<input type="password" minLength={12} value={studentPassword} onChange={e=>setStudentPassword(e.target.value)} required /></label><label>Class<select value={studentClass} onChange={e=>{setStudentClass(e.target.value);setStudentSection("");}} required><option value="">Select class</option>{classes.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Section<select value={studentSection} onChange={e=>setStudentSection(e.target.value)} required><option value="">Select section</option>{sections.filter(x=>x.class_id===studentClass).map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><button disabled={busy}>Create student</button></form><ul>{students.map(x=><li key={x._id}>{x.full_name} <small>@{x.username}</small></li>)}</ul></article>
      </section>
    </main>
  );
}
