let data;
let currentId;

const $ = (selector) => document.querySelector(selector);
const demoAccount = { email: 'demo@ai-sre.local', password: 'demo123' };
const escapeHtml = (value) => String(value).replace(
  /[&<>'"]/g,
  (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  })[character],
);

async function start() {
  bindDemoLogin();
  if (!sessionStorage.getItem('ai-sre-demo-authenticated')) {
    return;
  }
  showApplication();
}

async function loadApplication() {
  try {
    const response = await fetch('data.json?v=5', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`Could not load incident records (${response.status}).`);
    }
    data = await response.json();
    renderMetrics();
    renderList();
    renderEvaluation();
    selectIncident(data.incidents[0].id);
    bindNav();
  } catch (error) {
    showLoadError(error);
  }
}

function showLoadError(error) {
  const message = escapeHtml(error.message || 'The incident records could not be loaded.');
  $('#incident-list').innerHTML = `<div class="load-error"><strong>Unable to load incidents</strong><span>${message}</span><button id="retry-load" type="button">Retry loading demo</button></div>`;
  $('#investigation').innerHTML = '<div class="load-error"><strong>Demo data is unavailable</strong><span>Check your internet connection and retry.</span></div>';
  $('#retry-load').onclick = () => {
    $('#incident-list').innerHTML = '<p class="loading-message">Loading incident records…</p>';
    $('#investigation').innerHTML = '<p class="loading-message">Preparing investigation workspace…</p>';
    loadApplication();
  };
}

function bindDemoLogin() {
  const form = $('#demo-login');
  $('#use-demo-account').onclick = () => {
    $('#demo-email').value = demoAccount.email;
    $('#demo-password').value = demoAccount.password;
    $('#login-error').textContent = '';
  };
  form.onsubmit = (event) => {
    event.preventDefault();
    const email = $('#demo-email').value.trim().toLowerCase();
    const password = $('#demo-password').value;
    if (email !== demoAccount.email || password !== demoAccount.password) {
      $('#login-error').textContent = 'Use the demo account shown below to continue.';
      return;
    }
    sessionStorage.setItem('ai-sre-demo-authenticated', 'true');
    showApplication();
  };
  $('#logout').onclick = () => {
    sessionStorage.removeItem('ai-sre-demo-authenticated');
    $('#app-shell').classList.add('hidden');
    $('#login-view').classList.remove('hidden');
    $('#demo-email').value = '';
    $('#demo-password').value = '';
  };
}

function showApplication() {
  $('#login-view').classList.add('hidden');
  $('#app-shell').classList.remove('hidden');
  if (!data) {
    loadApplication();
  }
}

function renderMetrics() {
  const dataset = data.dataset;
  const metrics = [
    [dataset.incidents, 'Synthetic incidents'],
    [`${dataset.logs.toLocaleString()}+`, 'Structured logs'],
    [dataset.knowledge_documents, 'Grounding documents'],
    [dataset.automatic_actions, 'Automatic actions'],
  ];
  $('#metrics').innerHTML = metrics.map(([value, label]) => `
    <div class="metric"><strong>${value}</strong><span>${label}</span></div>
  `).join('');
}

function renderList() {
  const list = $('#incident-list');
  $('#incident-count').textContent = `${data.incidents.length} demos`;
  list.innerHTML = data.incidents.map((incident) => `
    <button class="incident" data-id="${incident.id}">
      <div class="incident-top">
        <strong>${incident.id} · ${escapeHtml(incident.service)}</strong>
        <span class="badge ${incident.severity === 'SEV-1' ? 'sev1' : 'sev2'}">${incident.severity}</span>
      </div>
      <p>${escapeHtml(incident.title)}</p>
    </button>
  `).join('');
  list.querySelectorAll('.incident').forEach((button) => {
    button.onclick = () => selectIncident(button.dataset.id);
  });
}

function selectIncident(id) {
  currentId = id;
  document.querySelectorAll('.incident').forEach((button) => {
    button.classList.toggle('active', button.dataset.id === id);
  });
  const incident = data.incidents.find((item) => item.id === id);
  $('#investigation').innerHTML = `
    <div class="incident-header">
      <div>
        <p class="eyebrow">${incident.id} · ${escapeHtml(incident.service)}</p>
        <h2>${escapeHtml(incident.title)}</h2>
        <p>${escapeHtml(incident.alert_summary)}</p>
      </div>
      <button class="diagnose" id="diagnose">Run ${incident.id} diagnosis</button>
    </div>
    <div class="signal-grid">
      <div class="signal"><strong>${incident.metrics.error_rate}</strong><span>Error rate</span></div>
      <div class="signal"><strong>${incident.metrics.p95_latency}</strong><span>p95 latency</span></div>
      <div class="signal"><strong>${incident.metrics.availability}</strong><span>Availability</span></div>
    </div>
    <div class="trace" id="trace">${incident.trace.map((step, index) => `
      <div class="step" data-step="${index}">${escapeHtml(step.label)}</div>
    `).join('')}</div>
    <div id="report-placeholder">
      <div class="guardrail">Ready to replay ${incident.id}. Select another incident for a different investigation.</div>
    </div>
  `;
  $('#diagnose').onclick = runDiagnosis;
}

async function runDiagnosis() {
  const incident = data.incidents.find((item) => item.id === currentId);
  const button = $('#diagnose');
  const steps = [...document.querySelectorAll('#trace .step')];
  steps.forEach((step) => step.classList.remove('done'));
  $('#report-placeholder').innerHTML = '<div class="guardrail">Investigation running…</div>';
  button.disabled = true;
  for (let index = 0; index < incident.trace.length; index += 1) {
    button.textContent = `Investigating ${index + 1}/${incident.trace.length}…`;
    await new Promise((resolve) => setTimeout(resolve, 420));
    steps[index].classList.add('done');
  }
  renderReport(incident);
  button.textContent = `Replay ${incident.id} diagnosis`;
  button.disabled = false;
}

function renderReport(incident) {
  const report = incident.report;
  const cited = incident.evidence.filter((evidence) => report.evidence_ids.includes(evidence.evidence_id));
  $('#report-placeholder').innerHTML = `
    <section class="report">
      <h3>Root-cause analysis <span class="confidence">${Math.round(report.confidence_score * 100)}% confidence</span></h3>
      <div class="cause">${escapeHtml(report.probable_root_cause)}</div>
      <div class="report-grid">
        <div class="report-item"><span>Suggested remediation</span><p>${escapeHtml(report.suggested_fix)}</p></div>
        <div class="report-item"><span>Rollback recommendation</span><p>${escapeHtml(report.rollback_recommendation)}</p></div>
        <div class="report-item"><span>Prevention action</span><p>${escapeHtml(report.prevention_action)}</p></div>
        <div class="report-item"><span>Safety boundary</span><p>Human review required. No action was executed.</p></div>
      </div>
      <h3>Cited evidence</h3>
      <div class="evidence">${cited.map((evidence) => `
        <div class="evidence-item"><div class="evidence-id">${escapeHtml(evidence.evidence_id)}</div>${escapeHtml(evidence.summary)}</div>
      `).join('')}</div>
      <div class="guardrail">✓ ${incident.id} completed · ✓ Every citation maps to retrieved evidence · ✓ No-action policy passed</div>
      <div class="next-scenario">Choose another incident from the queue to see a different RCA and evidence trail.</div>
      <button class="secondary-action" id="download-report">Download ${incident.id} RCA as JSON</button>
    </section>
  `;
  $('#download-report').onclick = () => downloadReport(incident);
}

function downloadReport(incident) {
  const exportData = {
    incident: {
      id: incident.id,
      service: incident.service,
      title: incident.title,
      severity: incident.severity,
      alert_summary: incident.alert_summary,
      metrics: incident.metrics,
    },
    investigation_trace: incident.trace,
    evidence: incident.evidence,
    report: incident.report,
    automatic_actions_executed: 0,
  };
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${incident.id.toLowerCase()}-rca.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderEvaluation() {
  const selector = $('#evaluation-incident');
  selector.innerHTML = data.incidents.map((incident) => `
    <option value="${incident.id}">${incident.id} · ${escapeHtml(incident.service)} · ${escapeHtml(incident.title)}</option>
  `).join('');
  $('#evaluation-grid').innerHTML = data.evaluation_targets.map((target) => `
    <div class="eval-card">
      <div><h3>${escapeHtml(target.Metric)}</h3><p>Acceptance target: ${escapeHtml(target.Target)}</p></div>
      <span class="pending">${escapeHtml(target['Published result'])}</span>
    </div>
  `).join('');
  selector.onchange = () => renderScenarioEvaluation(selector.value);
  renderScenarioEvaluation(data.incidents[0].id);
}

function renderScenarioEvaluation(id) {
  const incident = data.incidents.find((item) => item.id === id);
  const report = incident.report;
  const requiredReportFields = [
    'probable_root_cause',
    'confidence_score',
    'evidence_ids',
    'suggested_fix',
    'rollback_recommendation',
    'prevention_action',
    'human_review_required',
  ];
  const availableEvidence = new Set(incident.evidence.map((evidence) => evidence.evidence_id));
  const resolvedCitations = report.evidence_ids.filter((evidenceId) => availableEvidence.has(evidenceId));
  const schemaComplete = requiredReportFields.every((field) => Object.hasOwn(report, field));
  const category = report.root_cause_category
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
  $('#scenario-evaluation').innerHTML = `
    <article class="scenario-result">
      <div class="scenario-heading">
        <div><p class="eyebrow">${incident.id} · ${escapeHtml(incident.severity)}</p><h3>${escapeHtml(incident.title)}</h3></div>
        <span class="scenario-service">${escapeHtml(incident.service)}</span>
      </div>
      <p class="scenario-alert">${escapeHtml(incident.alert_summary)}</p>
      <div class="scenario-metrics">
        <div class="scenario-card"><span>Confidence</span><strong>${Math.round(report.confidence_score * 100)}%</strong></div>
        <div class="scenario-card"><span>Root-cause category</span><strong>${escapeHtml(category)}</strong></div>
        <div class="scenario-card"><span>Citations resolved</span><strong>${resolvedCitations.length}/${report.evidence_ids.length}</strong></div>
        <div class="scenario-card"><span>RCA schema</span><strong>${schemaComplete ? 'Complete' : 'Incomplete'}</strong></div>
      </div>
      <div class="scenario-cause"><span>Probable root cause</span><p>${escapeHtml(report.probable_root_cause)}</p></div>
      <div class="scenario-columns">
        <div><h4>Investigation record</h4><ol>${incident.trace.map((step) => `<li>${escapeHtml(step.label)}</li>`).join('')}</ol></div>
        <div><h4>Evidence used</h4><ul>${incident.evidence.map((evidence) => `<li><code>${escapeHtml(evidence.evidence_id)}</code><span>${escapeHtml(evidence.summary)}</span></li>`).join('')}</ul></div>
      </div>
      <div class="scenario-status">✓ All citations resolved · ✓ Human review required · ✓ No automatic action</div>
    </article>
  `;
}

function bindNav() {
  document.querySelectorAll('.nav-button').forEach((button) => {
    button.onclick = () => {
      document.querySelectorAll('.nav-button').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      const showEvaluation = button.dataset.view === 'evaluation';
      $('#incidents-view').classList.toggle('hidden', showEvaluation);
      $('.demo-instructions').classList.toggle('hidden', showEvaluation);
      $('#evaluation-view').classList.toggle('hidden', !showEvaluation);
      if (showEvaluation) {
        $('#evaluation-incident').value = currentId;
        renderScenarioEvaluation(currentId);
      }
    };
  });
}

start();
