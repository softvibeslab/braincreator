import { marked } from 'marked';
import DOMPurify from 'dompurify';

const EMPTY_JOURNEY = { goal: '', minutes: 15, phase: 'explore', draft: null, plan: null };
const RESOURCE_LABELS = { skool: 'Lección en Skool', youtube: 'Vídeo en YouTube', template: 'Plantilla original', link: 'Recurso original' };

const element = (tag, className, text) => {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = String(text);
  return el;
};
const markdown = text => DOMPurify.sanitize(marked.parse(String(text || ''), { breaks: true, gfm: true }), {
  ALLOWED_TAGS: ['p', 'strong', 'em', 'ul', 'ol', 'li', 'h2', 'h3', 'h4', 'br', 'blockquote', 'code'], ALLOWED_ATTR: [],
});
const safeURL = value => {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; }
};

export function mountGuide({ navigate, currentNode, hasNode }) {
  const endpoint = document.querySelector('meta[name="guide-api"]')?.content?.replace(/\/$/, '');
  if (!endpoint) return;
  let busy = false, ready = false, loading = false, activeView = 'conversation', resourceSelection = null;
  let state = { history: [], journey: { ...EMPTY_JOURNEY }, saved_nodes: [] }, minutes = 15;
  const nodeCards = new Map(), resourceCache = new Map(), resourceRequests = new Map();
  const missionDrafts = new Map();
  const failedTitleLoads = new Set();
  let hydratingTitles = false, resourceEpoch = 0;

  const launch = element('button', 'guide-launch', '✦ Pregúntale al experto');
  launch.type = 'button'; launch.setAttribute('aria-expanded', 'false'); launch.setAttribute('aria-controls', 'skool-guide');
  const panel = element('section', 'guide-panel');
  panel.id = 'skool-guide'; panel.hidden = true; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Skool Guide');
  panel.innerHTML = `
    <header><div><strong>Skool Guide</strong><small>De una buena pregunta a tu siguiente paso</small></div><div class="guide-header-actions"><button type="button" class="guide-expand" aria-label="Ampliar guía" aria-pressed="false">↗</button><button type="button" class="guide-close" aria-label="Cerrar guía">×</button></div></header>
    <div class="guide-context"></div>
    <div class="guide-tabs" role="tablist" aria-label="Tu guía">
      <button type="button" role="tab" id="guide-tab-conversation" aria-controls="guide-view-conversation" aria-selected="true" data-view="conversation">Conversación</button>
      <button type="button" role="tab" id="guide-tab-journey" aria-controls="guide-view-journey" aria-selected="false" tabindex="-1" data-view="journey">Mi camino</button>
      <button type="button" role="tab" id="guide-tab-resources" aria-controls="guide-view-resources" aria-selected="false" tabindex="-1" data-view="resources">Recursos</button>
    </div>
    <div id="guide-view-conversation" class="guide-view guide-chat-view" role="tabpanel" aria-labelledby="guide-tab-conversation">
      <div class="guide-messages" role="log" aria-live="polite" aria-label="Conversación"></div>
      <form class="guide-compose"><label class="guide-sr" for="guide-input">Tu pregunta o respuesta</label><textarea id="guide-input" placeholder="¿Qué quieres conseguir con tu agencia?" maxlength="2000" rows="2" required></textarea><button type="submit" data-guard>Enviar</button></form>
    </div>
    <div id="guide-view-journey" class="guide-view guide-scroll-view" role="tabpanel" aria-labelledby="guide-tab-journey" hidden></div>
    <div id="guide-view-resources" class="guide-view guide-scroll-view" role="tabpanel" aria-labelledby="guide-tab-resources" hidden></div>
    <p class="guide-status" role="status"></p>
    <small class="guide-note">Tu progreso se guarda para este navegador. Sin sincronización entre dispositivos.</small>`;
  document.body.append(launch, panel);
  const log = panel.querySelector('.guide-messages'), input = panel.querySelector('#guide-input');
  const form = panel.querySelector('.guide-compose'), status = panel.querySelector('.guide-status');
  const context = panel.querySelector('.guide-context'), pathView = panel.querySelector('#guide-view-journey');
  const resourcesView = panel.querySelector('#guide-view-resources'), tabs = [...panel.querySelectorAll('[role="tab"]')];

  function button(label, handler, { primary = false, guarded = true, className = '' } = {}) {
    const b = element('button', `guide-action ${primary ? 'guide-primary' : ''} ${className}`, label);
    b.type = 'button';
    if (guarded) { b.dataset.guard = ''; b.disabled = busy || !ready; }
    b.onclick = handler; return b;
  }
  function setBusy(value) {
    busy = value;
    panel.querySelectorAll('[data-guard]').forEach(b => { b.disabled = busy || !ready; });
    input.disabled = busy || !ready;
    form.setAttribute('aria-busy', String(value));
  }
  function setStatus(message = '', error = false) { status.textContent = message; status.classList.toggle('guide-error', error); }
  function show(view, focus = false) {
    activeView = view;
    if (view === 'resources') { renderResourceList(); failedTitleLoads.clear(); hydrateSavedTitles(); }
    tabs.forEach(tab => { const selected = tab.dataset.view === view; tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1; });
    panel.querySelectorAll('.guide-view').forEach(el => { el.hidden = el.id !== `guide-view-${view}`; });
    if (focus) tabs.find(tab => tab.dataset.view === view)?.focus();
  }
  tabs.forEach((tab, index) => {
    tab.onclick = () => show(tab.dataset.view);
    tab.onkeydown = event => {
      const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
      if (next !== null) { event.preventDefault(); show(tabs[next].dataset.view, true); }
    };
  });
  function updateContext() {
    const n = currentNode();
    context.textContent = n ? `Estás explorando: ${n.title}` : 'Un propósito · un siguiente paso';
  }
  function open() {
    panel.hidden = false; launch.setAttribute('aria-expanded', 'true'); updateContext();
    if (!ready && !loading) loadState();
    if (activeView === 'conversation' && ready) input.focus(); else tabs.find(tab => tab.dataset.view === activeView)?.focus();
  }
  function close() { panel.hidden = true; launch.setAttribute('aria-expanded', 'false'); launch.focus(); }
  function goToNode(id) {
    if (!hasNode(id)) return;
    navigate(id); launch.textContent = '✦ Continuar con mi guía'; close();
  }
  launch.onclick = () => panel.hidden ? open() : close();
  panel.querySelector('.guide-close').onclick = close;
  panel.querySelector('.guide-expand').onclick = event => {
    const expanded = panel.classList.toggle('guide-expanded');
    event.currentTarget.setAttribute('aria-pressed', String(expanded));
    event.currentTarget.setAttribute('aria-label', expanded ? 'Reducir guía' : 'Ampliar guía');
    event.currentTarget.textContent = expanded ? '↙' : '↗';
  };
  panel.addEventListener('keydown', event => {
    // Keep graph shortcuts from acting while the user works in the guide.
    event.stopPropagation();
    if (event.key === 'Escape') { event.preventDefault(); close(); }
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
  });

  async function request(path, data) {
    const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 25000);
    try {
      const response = await fetch(endpoint + path, { credentials: 'include', signal: abort.signal, ...(data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : {}) });
      let payload = {}; try { payload = await response.json(); } catch { /* A proxy may return a non-JSON error. */ }
      if (!response.ok) throw Error(payload.error || payload.message || 'No se pudo guardar. Inténtalo de nuevo.');
      return payload;
    } finally { clearTimeout(timer); }
  }
  function savedIds() { return (state.saved_nodes || []).map(n => typeof n === 'string' ? n : n.node_id || n.id).filter(Boolean); }
  function applyState(data) {
    if (data.journey) state.journey = { ...EMPTY_JOURNEY, ...data.journey };
    if (Array.isArray(data.saved_nodes)) state.saved_nodes = data.saved_nodes;
    if (Array.isArray(data.resources)) data.resources.forEach(n => { if (n.node_id) { resourceCache.set(n.node_id, n); nodeCards.set(n.node_id, n); } });
    for (const n of state.saved_nodes) if (typeof n === 'object') nodeCards.set(n.node_id || n.id, n);
    const preferredMinutes = state.journey.draft?.minutes || state.journey.minutes;
    minutes = [5, 15, 30].includes(preferredMinutes) ? preferredMinutes : minutes;
    renderJourney(); renderResourceList();
  }
  async function loadState() {
    if (loading) return;
    loading = true; setBusy(true); setStatus('Recuperando tu conversación y tu camino…');
    try {
      const data = await request('/state');
      ready = true; state.history = Array.isArray(data.history) ? data.history : [];
      applyState(data); renderHistory(); hydrateSavedTitles(); setStatus('');
    } catch (error) {
      setStatus(error.name === 'AbortError' ? 'La conexión está tardando. Vuelve a intentarlo.' : 'No pudimos recuperar tu progreso. Vuelve a intentarlo.', true);
      log.replaceChildren(element('p', 'guide-empty', 'Tu conversación y tu plan estarán disponibles al reconectar.'));
      log.append(button('Volver a conectar', loadState, { guarded: false, primary: true }));
    } finally { loading = false; setBusy(false); }
  }

  function bubble(text, role = 'assistant') {
    const el = element('div', `guide-message ${role}`);
    if (role === 'assistant') el.innerHTML = markdown(text); else el.textContent = text;
    log.append(el); return el;
  }
  function deactivateQuestions() { log.querySelectorAll('.guide-options').forEach(el => el.remove()); }
  function questionCard(question) {
    if (!question?.text) return;
    const box = element('section', 'guide-question');
    box.append(element('p', '', question.text));
    const options = element('div', 'guide-options');
    for (const option of (question.options || []).slice(0, 4)) {
      const label = typeof option === 'string' ? option : option.label || option.text;
      if (!label) continue;
      options.append(button(label, () => sendMessage(label), { className: 'guide-option' }));
    }
    if (options.childNodes.length) box.append(options);
    log.append(box);
  }
  function nodeCard(card, { saved = false } = {}) {
    const id = card.node_id || card.id;
    if (!id || !hasNode(id)) return null;
    nodeCards.set(id, { ...nodeCards.get(id), ...card, node_id: id });
    const box = element('article', 'guide-card');
    box.append(element('small', 'guide-eyebrow', saved ? 'Guardado para tu propósito' : 'Esto puede ayudarte'));
    box.append(element('strong', '', card.title || 'Lección recomendada'));
    if (card.reason) box.append(element('p', '', card.reason));
    const times = [...new Set((card.evidence || []).map(x => x.timestamp).filter(Boolean))];
    if (times.length) box.append(element('small', '', `Fragmentos de la lección · ${times.slice(0, 3).join(' · ')}`));
    const actions = element('div', 'guide-card-actions');
    actions.append(button('Ir al nodo →', () => goToNode(id), { primary: true, guarded: false }));
    actions.append(button('Explorar recursos', () => openResources(id), { guarded: false }));
    box.append(actions); return box;
  }
  function renderAnswer(data, { interactive = true, scroll = true } = {}) {
    const answer = bubble(data.answer || 'Revisa tu camino para continuar.');
    if (interactive) questionCard(data.question);
    const cards = (data.recommendations || []).filter(n => hasNode(n.node_id)).slice(0, 3);
    if (cards.length) {
      log.append(element('h3', 'guide-recommendations-title', cards.length > 1 ? 'Empieza aquí · después puedes profundizar' : 'Una lección para tu siguiente paso'));
      cards.forEach(card => { const el = nodeCard(card); if (el) log.append(el); });
    }
    if (interactive) {
      if (data.journey?.draft) log.append(button('Revisar mi plan antes de confirmar', () => show('journey', true), { primary: true, guarded: false }));
      else if (cards.length && !state.journey.plan) log.append(button('Tengo más claridad · preparar mi plan', () => show('journey', true), { guarded: false }));
    }
    if (scroll) log.scrollTop += answer.getBoundingClientRect().top - log.getBoundingClientRect().top - 12;
  }
  function renderHistory() {
    log.replaceChildren();
    if (!state.history.length) {
      bubble('Vamos a convertir lo que aprendas en una acción pequeña. **¿Qué te gustaría mejorar hoy?**');
      const choices = element('div', 'guide-options');
      for (const label of ['Conseguir clientes', 'Mejorar mi oferta', 'Vender mejor']) choices.append(button(label, () => sendMessage(label), { className: 'guide-option' }));
      log.append(choices);
    } else {
      state.history.forEach((item, index) => {
        if (item.role === 'user') bubble(item.content || '', 'user');
        else if (item.role === 'assistant') renderAnswer(item.response && typeof item.response === 'object' ? { ...item.response, answer: item.response.answer || item.content } : { answer: item.content }, { interactive: index === state.history.length - 1, scroll: false });
      });
      log.scrollTop = log.scrollHeight;
    }
  }
  async function sendMessage(message, extra = {}) {
    if (!message.trim() || busy || !ready) return;
    show('conversation'); deactivateQuestions(); input.value = ''; setBusy(true);
    bubble(message, 'user'); state.history.push({ role: 'user', content: message }); log.scrollTop = log.scrollHeight;
    setStatus(extra.action === 'generate_plan' ? 'Preparando tres pasos para tu propósito…' : 'Buscando el siguiente paso contigo…');
    const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 200000);
    try {
      const response = await fetch(endpoint + '/chat', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, node_id: currentNode()?.id || null, ...extra }), signal: abort.signal });
      if (!response.ok) { let data = {}; try { data = await response.json(); } catch {} throw Error(data.error || 'El guía no está disponible. Inténtalo de nuevo.'); }
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '', completed = false;
      const processFrame = frame => {
        const lines = frame.split('\n');
        const kind = lines.find(x => x.startsWith('event:'))?.slice(6).trim();
        const raw = lines.filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n');
        if (!raw) return;
        const data = JSON.parse(raw);
        if (kind === 'status') setStatus(data.message || 'Preparando tu respuesta…');
        if (kind === 'error') throw Error(data.message || 'No pudimos completar la respuesta.');
        if (kind === 'result') {
          applyState(data); renderAnswer(data); state.history.push({ role: 'assistant', content: data.answer, response: data }); completed = true;
          if (extra.action === 'generate_plan' && state.journey.draft) show('journey', true);
        }
      };
      while (true) {
        const { value, done } = await reader.read(); buffer += decoder.decode(value || new Uint8Array(), { stream: !done }); buffer = buffer.replace(/\r\n/g, '\n');
        let pos; while ((pos = buffer.indexOf('\n\n')) >= 0) { processFrame(buffer.slice(0, pos)); buffer = buffer.slice(pos + 2); }
        if (done) { if (buffer.trim()) processFrame(buffer); break; }
      }
      if (!completed) throw Error('La conexión terminó antes de recibir la respuesta. Inténtalo de nuevo.');
      setStatus('');
    } catch (error) {
      setStatus(error.name === 'AbortError' ? 'La consulta tardó demasiado. Tu progreso sigue guardado; puedes intentarlo de nuevo.' : error.message, true);
      input.value = message;
    } finally { clearTimeout(timer); setBusy(false); }
  }
  form.onsubmit = event => { event.preventDefault(); sendMessage(input.value.trim()); };

  async function mutate(action, payload = {}) {
    if (busy || !ready) return false;
    setBusy(true); setStatus('Guardando tu progreso…');
    try {
      const data = await request('/journey', { action, ...payload });
      if (action === 'mission_update' && missionDrafts.get(payload.mission_id) === payload.artifact) missionDrafts.delete(payload.mission_id);
      if (action === 'reset') missionDrafts.clear();
      applyState(data);
      if (action === 'reset') { state.history = []; resourceSelection = null; resourceEpoch++; resourceCache.clear(); resourceRequests.clear(); failedTitleLoads.clear(); nodeCards.clear(); renderHistory(); renderResourceList(); show('conversation'); launch.textContent = '✦ Pregúntale al experto'; }
      hydrateSavedTitles();
      setStatus(action === 'mission_update' && payload.status === 'completed' ? 'Marcada como hecha por ti. Tu siguiente paso está listo.' : action === 'discard_draft' ? 'Borrador descartado. Tu camino guardado se conserva.' : 'Cambios guardados para este navegador.');
      return true;
    } catch (error) { setStatus(error.name === 'AbortError' ? 'No pudimos confirmar el guardado. Vuelve a intentarlo.' : error.message, true); return false; }
    finally { setBusy(false); }
  }
  function missionDetails(mission) {
    const content = element('div', 'guide-mission-details');
    content.append(element('p', 'guide-mission-action', mission.action || ''));
    if (mission.deliverable) { content.append(element('small', 'guide-field-label', 'Tu pequeño entregable')); content.append(element('p', '', mission.deliverable)); }
    if (mission.done_when) { content.append(element('small', 'guide-field-label', 'Terminas cuando')); content.append(element('p', '', mission.done_when)); }
    for (const id of (mission.node_ids || []).filter(hasNode).slice(0, 2)) content.append(button('Ver la lección que te ayuda', () => openResources(id), { guarded: false, className: 'guide-text-action' }));
    return content;
  }
  function minutesControl() {
    const field = element('fieldset', 'guide-time-choice'); field.append(element('legend', '', '¿Cuánto tiempo tienes por sesión?'));
    for (const value of [5, 15, 30]) {
      const b = button(`${value} min`, () => { minutes = value; field.querySelectorAll('button').forEach(el => el.setAttribute('aria-pressed', String(el === b))); });
      b.setAttribute('aria-pressed', String(minutes === value)); field.append(b);
    }
    return field;
  }
  function renderJourney() {
    pathView.replaceChildren();
    const journey = state.journey || EMPTY_JOURNEY, plan = journey.plan, draft = journey.draft;
    const top = element('div', 'guide-view-heading'); top.append(element('span', 'guide-eyebrow', 'Mi camino'));
    top.append(element('h2', '', draft?.goal || journey.goal || plan?.goal || 'Un propósito. Un paso pequeño.')); pathView.append(top);
    if (draft) {
      const preview = element('section', 'guide-plan-preview');
      preview.append(element('span', 'guide-badge', 'Propuesta · aún sin activar'));
      preview.append(element('p', '', plan ? 'Revisa estos pasos. Al confirmar, esta propuesta reemplazará tu plan actual.' : 'Revisa estos pasos. Tu plan empieza cuando lo confirmes.'));
      preview.append(element('small', 'guide-muted', 'Ejercicios creados por Skool Guide a partir de las lecciones.'));
      draft.missions.forEach((mission, index) => {
        const detail = element('details', 'guide-mission-outline');
        detail.open = index === 0;
        detail.append(element('summary', '', `${index + 1}. ${mission.title} · ${mission.minutes} min`)); detail.append(missionDetails(mission)); preview.append(detail);
      });
      preview.append(button('Confirmar y guardar mi plan', () => mutate('confirm_plan', { draft_id: draft.id }), { primary: true }));
      preview.append(button(plan ? 'Conservar mi plan actual' : 'Descartar borrador', () => mutate('discard_draft', { draft_id: draft.id }), { className: 'guide-text-action' }));
      preview.append(button('Quiero ajustar estos pasos', () => { show('conversation'); input.value = 'Quiero ajustar el plan: '; input.focus(); }, { guarded: false }));
      const revise = element('details', 'guide-mission-outline'); revise.append(element('summary', '', 'Actualizar propuesta con mis ajustes')); revise.append(minutesControl());
      revise.append(button('Preparar una nueva propuesta', () => sendMessage(`Actualiza el borrador según lo que aclaramos. Tengo ${minutes} minutos por sesión.`, { action: 'generate_plan', minutes }))); preview.append(revise);
      pathView.append(preview);
    } else if (plan) {
      const missions = plan.missions || [], done = missions.filter(m => m.status === 'completed').length;
      const progress = element('div', 'guide-progress');
      progress.append(element('strong', '', `${done} de ${missions.length} acciones completadas`));
      const meter = element('progress'); meter.max = missions.length || 1; meter.value = done; meter.setAttribute('aria-label', 'Acciones completadas'); progress.append(meter);
      progress.append(element('small', '', 'El progreso registra tus acciones, no resultados comerciales.')); pathView.append(progress);
      const active = missions.find(m => m.status === 'active' || m.status === 'blocked') || missions.find(m => m.status !== 'completed');
      if (journey.phase === 'paused') {
        const paused = element('section', 'guide-empty'); paused.append(element('h3', '', 'Tu camino está en pausa'));
        paused.append(element('p', '', 'Retómalo cuando tengas espacio. Tu avance sigue aquí.'));
        paused.append(button('Retomar mi camino', () => mutate('resume'), { primary: true })); pathView.append(paused);
      } else if (active) {
        const current = element('section', 'guide-active-mission');
        current.append(element('span', 'guide-eyebrow', `Tu siguiente misión · ${active.minutes} min`));
        current.append(element('h3', '', active.title)); current.append(missionDetails(active));
        if (active.status === 'blocked') {
          const blocked = element('div', 'guide-blocked'); blocked.append(element('strong', '', 'Hagamos este paso más pequeño'));
          blocked.append(element('p', '', '¿Qué te está frenando ahora?'));
          for (const option of ['No sé cómo empezar', 'Necesito un ejemplo', 'Tengo muy poco tiempo']) blocked.append(button(option, () => sendMessage(`En la misión «${active.title}»: ${option.toLowerCase()}. Ayúdame con un paso más pequeño.`, { mission_id: active.id })));
          current.append(blocked);
        }
        const label = element('label', 'guide-field-label', 'Tu resultado o una nota (opcional)'); label.htmlFor = 'guide-artifact';
        const artifact = element('textarea', 'guide-artifact'); artifact.id = 'guide-artifact'; artifact.rows = 3; artifact.maxLength = 3000;
        artifact.placeholder = 'Escribe aquí tu avance. Puedes guardarlo y seguir después.';
        artifact.value = missionDrafts.has(active.id) ? missionDrafts.get(active.id) : active.artifact || '';
        artifact.addEventListener('input', () => missionDrafts.set(active.id, artifact.value));
        current.append(label, artifact);
        const actions = element('div', 'guide-mission-actions');
        actions.append(button('Ya lo hice ✓', () => mutate('mission_update', { mission_id: active.id, status: 'completed', artifact: artifact.value }), { primary: true }));
        actions.append(button('Guardar avance', () => mutate('mission_update', { mission_id: active.id, status: active.status === 'blocked' ? 'blocked' : 'active', artifact: artifact.value })));
        actions.append(button(active.status === 'blocked' ? 'Ya puedo continuar' : 'Me atasqué', () => mutate('mission_update', { mission_id: active.id, status: active.status === 'blocked' ? 'active' : 'blocked', artifact: artifact.value })));
        current.append(actions, element('small', 'guide-muted', 'Al marcarla como hecha registramos tu confirmación; el entregable no se verifica automáticamente.'));
        pathView.append(current);
      } else {
        const completed = element('section', 'guide-empty'); completed.append(element('h3', '', 'Completaste tus mini misiones'));
        completed.append(element('p', '', 'Antes de seguir, revisemos qué cambió y qué te resultó útil.'));
        completed.append(button('Revisar lo que conseguí', () => sendMessage('Completé mis misiones. Ayúdame a revisar lo que conseguí y elegir mi siguiente paso.'), { primary: true })); pathView.append(completed);
      }
      const overview = element('details', 'guide-mission-outline'); overview.append(element('summary', '', 'Ver el recorrido completo'));
      missions.forEach((mission, index) => {
        const row = element('div', 'guide-plan-row'); row.append(element('strong', '', `${mission.status === 'completed' ? '✓' : index + 1 + '.'} ${mission.title}`));
        row.append(element('small', '', mission.status === 'completed' ? 'Marcada como hecha por ti' : `${mission.minutes} min · ${mission.status === 'blocked' ? 'Necesitas ayuda' : 'Pendiente'}`));
        if (mission.artifact) row.append(element('p', 'guide-artifact-preview', mission.artifact)); overview.append(row);
      }); pathView.append(overview);
      if (journey.phase !== 'paused' && active) pathView.append(button('Pausar mi camino', () => mutate('pause'), { className: 'guide-text-action' }));
      pathView.append(button('Cambió mi objetivo', () => { show('conversation'); input.value = 'Mi objetivo cambió. Ahora quiero '; input.focus(); }, { guarded: false, className: 'guide-text-action' }));
    } else {
      pathView.append(element('p', 'guide-lede', 'Primero aclaramos lo que necesitas. Después prepararemos tres mini misiones con un entregable y una forma clara de terminarlas.'));
      if (!state.history.some(item => item.role === 'user')) pathView.append(button('Aclarar mi propósito', () => { show('conversation'); input.focus(); }, { primary: true, guarded: false }));
      else {
        pathView.append(minutesControl());
        pathView.append(button('Tengo claridad · crear mi plan', () => sendMessage(`Quiero preparar un plan de tres mini misiones para mi propósito. Tengo ${minutes} minutos por sesión.`, { action: 'generate_plan', minutes }), { primary: true }));
        pathView.append(element('small', 'guide-muted', 'Podrás revisar y ajustar la propuesta antes de confirmarla.'));
      }
    }
    if (plan && !draft) {
      const revise = element('details', 'guide-mission-outline'); revise.append(element('summary', '', journey.phase === 'completed' ? 'Preparar mis siguientes tres pasos' : 'Ajustar mi plan o mi propósito'));
      revise.append(element('p', 'guide-replan-note', 'Cuéntame qué cambió en Conversación. Después puedes preparar una nueva propuesta y revisarla antes de confirmar.'));
      revise.append(minutesControl()); revise.append(button('Preparar una nueva propuesta', () => sendMessage(`Prepara tres nuevas mini misiones a partir de mi avance y lo que aclaramos. Tengo ${minutes} minutos por sesión.`, { action: 'generate_plan', minutes }))); pathView.append(revise);
    }
    const privacy = element('details', 'guide-data-controls'); privacy.append(element('summary', '', 'Sobre mi progreso guardado'));
    privacy.append(element('p', '', 'Tu conversación y tu plan se conservan durante 30 días desde tu última actividad. Están asociados a este navegador: borrar sus cookies o cambiar de dispositivo puede impedir que vuelvas a encontrarlos.'));
    const remove = button('Borrar conversación y progreso', () => {
      confirmation.hidden = false; remove.hidden = true;
    }, { className: 'guide-text-action' });
    const confirmation = element('div', 'guide-delete-confirm'); confirmation.hidden = true;
    confirmation.append(element('p', '', 'Se borrarán tu conversación, plan y recursos guardados. Esta acción no se puede deshacer.'));
    confirmation.append(button('Sí, borrar mi progreso', () => mutate('reset'), { className: 'guide-danger' }));
    confirmation.append(button('Conservarlo', () => { confirmation.hidden = true; remove.hidden = false; }, { guarded: false }));
    privacy.append(remove, confirmation); pathView.append(privacy);
  }

  function renderResourceList() {
    resourcesView.replaceChildren();
    if (resourceSelection) { renderResourceDetail(resourceSelection); return; }
    const heading = element('div', 'guide-view-heading'); heading.append(element('span', 'guide-eyebrow', 'Tu biblioteca útil'), element('h2', '', 'Recursos para tu propósito')); resourcesView.append(heading);
    const ids = savedIds().filter(hasNode);
    if (!ids.length) resourcesView.append(element('p', 'guide-lede', 'Guarda las lecciones que te sirvan. Aquí tendrás sus ideas clave y los enlaces originales disponibles.'));
    ids.forEach(id => { const card = nodeCard(nodeCards.get(id) || { node_id: id, title: 'Cargando lección guardada…', _placeholder: true }, { saved: true }); if (card) resourcesView.append(card); });
    const current = currentNode();
    if (current && !ids.includes(current.id)) {
      resourcesView.append(element('h3', 'guide-recommendations-title', 'El nodo que estás explorando'));
      const card = nodeCard({ node_id: current.id, title: current.title }); if (card) resourcesView.append(card);
    }
    const recent = [...nodeCards.values()].filter(n => !ids.includes(n.node_id) && n.node_id !== current?.id).slice(-3).reverse();
    if (recent.length) { resourcesView.append(element('h3', 'guide-recommendations-title', 'Descubiertos en esta conversación')); recent.forEach(n => { const card = nodeCard(n); if (card) resourcesView.append(card); }); }
  }
  async function fetchResource(id) {
    if (resourceCache.has(id)) return resourceCache.get(id);
    if (resourceRequests.has(id)) return resourceRequests.get(id);
    const epoch = resourceEpoch;
    const pending = request('/resources?node_id=' + encodeURIComponent(id)).then(data => {
      if (epoch === resourceEpoch) {
        resourceCache.set(id, data);
        nodeCards.set(id, { ...nodeCards.get(id), ...data, _placeholder: false });
      }
      return data;
    }).finally(() => { if (resourceRequests.get(id) === pending) resourceRequests.delete(id); });
    resourceRequests.set(id, pending);
    return pending;
  }
  async function hydrateSavedTitles() {
    if (!ready || hydratingTitles) return;
    const missing = savedIds().filter(id => hasNode(id) && !failedTitleLoads.has(id) && (!nodeCards.get(id)?.title || nodeCards.get(id)?._placeholder));
    if (!missing.length) return;
    hydratingTitles = true;
    const epoch = resourceEpoch;
    let next = 0;
    const worker = async () => {
      while (next < missing.length && epoch === resourceEpoch) {
        const id = missing[next++];
        try { await fetchResource(id); }
        catch {
          if (epoch === resourceEpoch) {
            failedTitleLoads.add(id);
            nodeCards.set(id, { ...nodeCards.get(id), node_id: id, title: 'Lección guardada · abrir recursos', _placeholder: true });
          }
        }
        if (epoch === resourceEpoch && !resourceSelection) renderResourceList();
      }
    };
    try { await Promise.all([worker(), worker()]); }
    finally { hydratingTitles = false; }
  }
  async function openResources(id) {
    if (!hasNode(id)) return;
    resourceSelection = id; show('resources'); renderResourceDetail(id);
    if (resourceCache.has(id)) return;
    try {
      await fetchResource(id);
      if (resourceSelection === id) renderResourceDetail(id);
    } catch {
      if (resourceSelection !== id) return;
      resourcesView.querySelector('.guide-resource-loading')?.remove();
      resourcesView.append(element('p', 'guide-empty', 'No pudimos cargar los recursos. Puedes abrir el nodo o intentarlo de nuevo.'));
      resourcesView.append(button('Reintentar', () => openResources(id), { guarded: false }));
    }
  }
  function renderResourceDetail(id) {
    resourcesView.replaceChildren();
    resourcesView.append(button('← Mis recursos', () => { resourceSelection = null; renderResourceList(); }, { guarded: false, className: 'guide-text-action' }));
    const data = resourceCache.get(id), card = data || nodeCards.get(id) || {};
    const heading = element('div', 'guide-view-heading'); heading.append(element('span', 'guide-eyebrow', 'Conocimiento para aplicar'), element('h2', '', card.title || 'Lección recomendada')); resourcesView.append(heading);
    const actions = element('div', 'guide-card-actions'); actions.append(button('Ver en el cerebro →', () => goToNode(id), { primary: true, guarded: false }));
    const saved = savedIds().includes(id); actions.append(button(saved ? 'Quitar de guardados' : 'Guardar recurso', () => mutate(saved ? 'remove_saved_node' : 'save_node', { node_id: id }))); resourcesView.append(actions);
    if (!data) { resourcesView.append(element('p', 'guide-resource-loading', 'Cargando ideas clave y fuentes originales…')); return; }
    if (data.highlights?.length) {
      resourcesView.append(element('h3', 'guide-section-title', 'Ideas clave'));
      const highlights = element('ul', 'guide-highlights'); data.highlights.slice(0, 3).forEach(item => highlights.append(element('li', '', typeof item === 'string' ? item : item.text || item.title || ''))); resourcesView.append(highlights);
    } else if (data.summary) {
      const summary = element('div', 'guide-resource-summary'); summary.innerHTML = markdown(data.summary); resourcesView.append(summary);
    }
    const links = (data.resources || []).filter(r => safeURL(r.url));
    if (links.length) {
      resourcesView.append(element('h3', 'guide-section-title', 'Material original disponible'));
      links.forEach(resource => {
        const a = element('a', 'guide-resource-link'); a.href = safeURL(resource.url); a.target = '_blank'; a.rel = 'noopener noreferrer';
        a.append(element('small', '', RESOURCE_LABELS[resource.type] || 'Recurso original'), element('strong', '', resource.title || RESOURCE_LABELS[resource.type] || 'Abrir recurso'));
        if (resource.timestamp) a.append(element('span', '', `Fragmento · ${resource.timestamp}`));
        if (resource.access_note) a.append(element('span', '', resource.access_note));
        a.append(element('span', 'guide-link-hint', 'Abrir en otra pestaña ↗')); resourcesView.append(a);
      });
    } else resourcesView.append(element('p', 'guide-empty', 'Esta ficha no tiene enlaces a materiales originales disponibles. Puedes consultar su contenido en el cerebro.'));
    if (data.notice) resourcesView.append(element('p', 'guide-resource-notice', data.notice));
    if (data.timestamps?.length) {
      const times = element('details', 'guide-mission-outline'); times.append(element('summary', '', 'Fragmentos para revisar'));
      data.timestamps.slice(0, 8).forEach(item => {
        const label = typeof item === 'string' ? item : `${item.timestamp || item.time || ''} ${item.text || item.label || ''}`;
        const url = typeof item === 'object' ? safeURL(item.url) : null;
        const point = element(url ? 'a' : 'p', 'guide-timestamp', label);
        if (url) { point.href = url; point.target = '_blank'; point.rel = 'noopener noreferrer'; }
        times.append(point);
      }); resourcesView.append(times);
    }
    resourcesView.append(element('small', 'guide-muted', 'Solo mostramos enlaces asociados a esta ficha. Los materiales creados contigo se distinguen de los recursos originales.'));
    resourcesView.append(button('Ayúdame a aplicar esta lección', () => sendMessage(`Ayúdame a aplicar la lección «${card.title || 'este nodo'}» a mi propósito. Hazme una pregunta clave para comenzar.`, { node_id: id })));
  }
  renderHistory(); renderJourney(); renderResourceList(); setBusy(false);
}
