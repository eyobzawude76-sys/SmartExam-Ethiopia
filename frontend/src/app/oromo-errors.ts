/**
 * Convert API and network failures into clear, actionable Afaan Oromoo.
 * Keep technical details and server exceptions out of user-facing messages.
 */
export function oromoErrorMessage(
  error: unknown,
  fallback = "Hojii kana raawwachuun hin danda'amne. Maaloo irra deebi'ii yaali.",
): string {
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === "string" || typeof error === "number"
        ? String(error)
        : "";
  const message = raw.toLowerCase();

  if (/failed to fetch|networkerror|network request failed|load failed|fetch failed|internet/.test(message)) {
    return "Intarneetiin hin jiru ykn serveriin hin deebisne. Walqunnamtii intarneetii kee mirkaneeffadhuutii irra deebi'ii yaali.";
  }
  if (/not an admin account|not a teacher account|not a student account|kun .* account miti/.test(message)) {
    return "Herregni kun gahee (role) fuula kanaaf hin taane. Maaloo fuula gahee sirrii fayyadami.";
  }
  if (/401|unauthorized|incorrect username|incorrect password|invalid credentials|login failed|session expired|token.*expired/.test(message)) {
    return "Maqaan fayyadamaa ykn password sirrii miti, ykn yeroo seensaa kee xumurameera. Odeeffannoo kee mirkaneeffadhuutii irra deebi'ii seeni.";
  }
  if (/403|forbidden|permission|not allowed|access denied/.test(message)) {
    return "Hojii kana raawwachuuf hayyama hin qabdu. Gahee kee ykn ramaddii kee mirkaneeffadhu; yoo barbaachise Admin qunnami.";
  }
  if (/404|not found|does not exist/.test(message)) {
    return "Odeeffannoon barbaadde hin argamne ykn duraan haqameera. Fuula haaromsiitii irra deebi'ii yaali.";
  }
  if (/409|already exists|duplicate|conflict/.test(message)) {
    return "Odeeffannoo kanaan duraan galmee jira. Maaloo odeeffannoo adda ta'e galchi ykn galmee duraan jiru ilaali.";
  }
  if (/422|validation|invalid|is required|required field|must be/.test(message)) {
    return "Odeeffannoon galchite sirrii miti ykn dirreen barbaachisu hin guutamne. Maaloo odeeffannoo kee sirreessi.";
  }
  if (/400|bad request/.test(message)) {
    return "Gaaffiin ergame sirrii miti. Odeeffannoo galchite mirkaneeffadhuutii irra deebi'ii yaali.";
  }
  if (/429|too many requests|rate limit/.test(message)) {
    return "Yaalii baay'ee goote. Xiqqoo eegiitii irra deebi'ii yaali.";
  }
  if (/timeout|timed out/.test(message)) {
    return "Serveriin yeroo isaa keessatti hin deebisne. Intarneetii kee mirkaneeffadhuutii irra deebi'ii yaali.";
  }
  if (/500|502|503|504|internal server|server error|service unavailable/.test(message)) {
    return "Serveriin yeroo ammaa rakkoo qaba. Booda irra deebi'ii yaali; yoo itti fufe Admin qunnami.";
  }
  return fallback;
}
