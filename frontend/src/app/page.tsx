export default function HomePage() {
  return (
    <main className="page-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">SMARTEXAM ETHIOPIA</p>
        <h1 id="page-title">A clear, secure way to manage school examinations.</h1>
        <p className="intro">
          A role-based examination platform connecting school administrators,
          teachers, and students.
        </p>
        <div className="role-grid" aria-label="System roles">
          <article className="role-card">
            <h2>Admin</h2>
            <p>Set up classes, sections, subjects, teacher assignments, and student accounts.</p>
          </article>
          <article className="role-card">
            <h2>Teacher</h2>
            <p>Create MCQ questions, schedule exams, grade submissions, and release results.</p>
          </article>
          <article className="role-card">
            <h2>Student</h2>
            <p>Take exams assigned to your class and section, then view released results.</p>
          </article>
        </div>
        <p className="notice">Admin: <a href="/admin">Open Admin Dashboard</a> · Teacher: <a href="/teacher">Open Teacher Dashboard</a> · Student: <a href="/student">Open Student Dashboard</a>.</p>
      </section>
    </main>
  );
}
