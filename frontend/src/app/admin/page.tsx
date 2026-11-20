"use client";

import { FormEvent, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

type Item = { _id: string; id?: string; name: string; code?: string; class_id?: string };
type User = { _id: string; username: string; full_name: string; role: string; is_active: boolean; class_id?: string | null; section_id?: string | null };
type Assignment = { subject_id: string; class_id: string; section_id: string };

export default function AdminPage() {
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [subjects, setSubjects] = useState<Item[]>([]);
  const [classes, setClasses] = useState<Item[]>([]);
  const [sections, setSections] = useState<Item[]>([]);
  const [teachers, setTeachers] = useState<User[]>([]);
  const [teacherAssignments, setTeacherAssignments] = useState<Record<string, Assignment[]>>({});
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
    const assignmentEntries = await Promise.all(t.filter((teacher: User) => teacher.is_active).map(async (teacher: User) => [teacher._id, await request(`/admin/teachers/${teacher._id}/assignments`)] as const));
    setCounts(dashboard.counts); setSubjects(s); setClasses(c); setSections(sec); setTeachers(t); setStudents(st);
    setTeacherAssignments(Object.fromEntries(assignmentEntries));
  }

  useEffect(() => {
    const saved = window.sessionStorage.getItem("smartExamAdminToken");
    const passwordChangeRequired = window.sessionStorage.getItem("smartExamAdminMustChangePassword") === "true";
    if (saved) {
      // This effect restores authentication state from sessionStorage after client hydration.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMustChangePassword(passwordChangeRequired);
      setToken(saved);
    }
  }, []);

  useEffect(() => {
    // Authentication changes trigger the protected dashboard refresh; clear invalid sessions on failure.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (token && !mustChangePassword) refresh().catch((error) => { setMessage(error.message); setToken(""); window.sessionStorage.removeItem("smartExamAdminToken"); window.sessionStorage.removeItem("smartExamAdminMustChangePassword"); });
    // Refresh only when authentication changes or the required password change is completed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, mustChangePassword]);

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const data = await request("/auth/login", "POST", { username, password });
      if (data.user.role !== "ADMIN") throw new Error("This account is not an Admin account.");
      window.sessionStorage.setItem("smartExamAdminToken", data.access_token);
      window.sessionStorage.setItem("smartExamAdminMustChangePassword", String(Boolean(data.user.must_change_password)));
      setMustChangePassword(Boolean(data.user.must_change_password));
      setToken(data.access_token); setPassword("");
      setMessage(data.user.must_change_password ? "Jalqaba password jijjiiri." : "Admin seente.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Login failed"); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent, path: string, body: unknown, success: string, reset?: () => void) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      const result = await request(path, "POST", body);
      reset?.();
      const successMessage = result.temporary_password_once
        ? `${success} Username: ${result.teacher?.username ?? result.student?.username}. Temporary password (save it now): ${result.temporary_password_once}`
        : success;
      // Show one-time credentials immediately; a later dashboard refresh must not hide them.
      setMessage(successMessage);
      try {
        await refresh();
      } catch (refreshError) {
        const detail = refreshError instanceof Error ? refreshError.message : "Unknown refresh error";
        setMessage(`${successMessage} Dashboard refresh failed: ${detail}. The account creation request succeeded.`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Request failed");
    }
    finally { setBusy(false); }
  }

  async function toggleUserStatus(user: User) {
    setBusy(true); setMessage("");
    try {
      await request(`/admin/users/${user._id}/status`, "PATCH", { is_active: !user.is_active });
      const successMessage = `${user.full_name}: account ${user.is_active ? "deactivated" : "activated"}.`;
      setMessage(successMessage);
      try {
        await refresh();
      } catch (refreshError) {
        const detail = refreshError instanceof Error ? refreshError.message : "Unknown refresh error";
        setMessage(`${successMessage} Dashboard refresh failed: ${detail}. The status update succeeded.`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Status update failed");
    } finally {
      setBusy(false);
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setMessage("New password fi confirmation wal hin siman.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const changed = await request("/auth/change-password", "POST", { current_password: currentPassword, new_password: newPassword });
      window.sessionStorage.setItem("smartExamAdminToken", changed.access_token);
      setToken(changed.access_token);
      window.sessionStorage.setItem("smartExamAdminMustChangePassword", "false");
      setMustChangePassword(false);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMessage("Password jijjiirameera. Admin dashboard banamaa jira.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Password change failed");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    window.sessionStorage.removeItem("smartExamAdminToken");
    window.sessionStorage.removeItem("smartExamAdminMustChangePassword");
    setMustChangePassword(false); setToken(""); setCounts({}); setMessage("Baate.");
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

  if (mustChangePassword) return (
    <main className="admin-shell"><section className="admin-panel login-panel">
      <p className="eyebrow">SMARTEXAM ETHIOPIA</p><h1>Password Change Required</h1>
      <p className="muted">Admin hojii itti fufuuf password yeroo jalqabaa kenname jijjiiruu qaba.</p>
      <form onSubmit={changePassword} className="stack">
        <label>Current temporary password<input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} autoComplete="current-password" minLength={8} required /></label>
        <label>New password (12+ characters)<input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} autoComplete="new-password" minLength={12} required /></label>
        <label>Confirm new password<input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} autoComplete="new-password" minLength={12} required /></label>
        <button disabled={busy}>{busy ? "Jijjiiraa jira..." : "Change password"}</button>
      </form>
      <button type="button" className="secondary" onClick={logout}>Logout</button>
      {message && <p className="feedback">{message}</p>}
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
        <article className="admin-panel"><h2>Create Teacher</h2><form className="stack" onSubmit={e=>submit(e,"/admin/teachers",{full_name:teacherName,username:teacherUsername,temporary_password:teacherPassword,assignments:[{subject_id:teacherSubject,class_id:teacherClass,section_id:teacherSection}]},"Teacher account created.",()=>{setTeacherName("");setTeacherUsername("");setTeacherPassword("");})}><label>Full name<input value={teacherName} onChange={e=>setTeacherName(e.target.value)} required /></label><label>Username<input value={teacherUsername} onChange={e=>setTeacherUsername(e.target.value)} required /></label><label>Temporary password (12+ characters)<input type="password" minLength={12} value={teacherPassword} onChange={e=>setTeacherPassword(e.target.value)} required /></label><label>Subject<select value={teacherSubject} onChange={e=>setTeacherSubject(e.target.value)} required><option value="">Select subject</option>{subjects.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Class<select value={teacherClass} onChange={e=>{setTeacherClass(e.target.value);setTeacherSection("");}} required><option value="">Select class</option>{classes.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Section<select value={teacherSection} onChange={e=>setTeacherSection(e.target.value)} required><option value="">Select section</option>{sections.filter(x=>x.class_id===teacherClass).map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><button disabled={busy}>Create teacher</button></form><ul>{teachers.map(x=><li key={x._id}><span>{x.full_name} <small>@{x.username} · {x.is_active ? "Active" : "Inactive"}</small>{x.is_active && <small className="assignment-summary">{(teacherAssignments[x._id] ?? []).map(a=>{const subject=subjects.find(s=>s._id===a.subject_id)?.name ?? "Subject";const cls=classes.find(c=>c._id===a.class_id)?.name ?? "Class";const section=sections.find(s=>s._id===a.section_id)?.name ?? "Section";return `${subject} — ${cls} / ${section}`;}).join(" · ") || "No assignments"}</small>}</span><button type="button" className="secondary" disabled={busy} onClick={()=>toggleUserStatus(x)}>{x.is_active ? "Deactivate" : "Activate"}</button></li>)}</ul></article>
        <article className="admin-panel"><h2>Add Teacher Assignment</h2><p className="muted">Barsiisaa duraan jiruuf subject, class fi section dabalataa ramadi.</p><form className="stack" onSubmit={e=>submit(e,`/admin/teachers/${assignmentTeacher}/assignments`,{subject_id:assignmentSubject,class_id:assignmentClass,section_id:assignmentSection},"Teacher assignment added.",()=>{setAssignmentSubject("");setAssignmentSection("");})}><label>Teacher<select value={assignmentTeacher} onChange={e=>setAssignmentTeacher(e.target.value)} required><option value="">Select teacher</option>{teachers.filter(x=>x.is_active).map(x=><option key={x._id} value={x._id}>{x.full_name} (@{x.username})</option>)}</select></label><label>Subject<select value={assignmentSubject} onChange={e=>setAssignmentSubject(e.target.value)} required><option value="">Select subject</option>{subjects.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Class<select value={assignmentClass} onChange={e=>{setAssignmentClass(e.target.value);setAssignmentSection("");}} required><option value="">Select class</option>{classes.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Section<select value={assignmentSection} onChange={e=>setAssignmentSection(e.target.value)} required><option value="">Select section</option>{sections.filter(x=>x.class_id===assignmentClass).map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><button disabled={busy || !assignmentTeacher}>Add assignment</button></form></article>
        <article className="admin-panel"><h2>Create Student</h2><form className="stack" onSubmit={e=>submit(e,"/admin/students",{full_name:studentName,username:studentUsername,temporary_password:studentPassword,class_id:studentClass,section_id:studentSection},"Student account created.",()=>{setStudentName("");setStudentUsername("");setStudentPassword("");})}><label>Full name<input value={studentName} onChange={e=>setStudentName(e.target.value)} required /></label><label>Username<input value={studentUsername} onChange={e=>setStudentUsername(e.target.value)} required /></label><label>Temporary password (12+ characters)<input type="password" minLength={12} value={studentPassword} onChange={e=>setStudentPassword(e.target.value)} required /></label><label>Class<select value={studentClass} onChange={e=>{setStudentClass(e.target.value);setStudentSection("");}} required><option value="">Select class</option>{classes.map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><label>Section<select value={studentSection} onChange={e=>setStudentSection(e.target.value)} required><option value="">Select section</option>{sections.filter(x=>x.class_id===studentClass).map(x=><option key={x._id} value={x._id}>{x.name}</option>)}</select></label><button disabled={busy}>Create student</button></form><ul>{students.map(x=><li key={x._id}><span>{x.full_name} <small>@{x.username} · {x.is_active ? "Active" : "Inactive"}</small><small>{classes.find(c=>c._id===x.class_id)?.name ?? "No class"} / {sections.find(s=>s._id===x.section_id)?.name ?? "No section"}</small></span><button type="button" className="secondary" disabled={busy} onClick={()=>toggleUserStatus(x)}>{x.is_active ? "Deactivate" : "Activate"}</button></li>)}</ul></article>
      </section>
    </main>
  );
}
