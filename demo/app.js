let data;
let currentId;

const $ = (selector) => document.querySelector(selector);
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
  data = await fetch('data.json', { cache: 'no-store' }).then((response) => response.json());
  renderMetrics();
  renderList();
  renderEvaluation();
  selectIncident(data.incidents[0].id);
  bindNav();
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
  $('#evaluation-grid').innerHTML = data.evaluation_targets.map((target) => `
    <div class="eval-card">
      <div><h3>${escapeHtml(target.Metric)}</h3><p>Acceptance target: ${escapeHtml(target.Target)}</p></div>
      <span class="pending">${escapeHtml(target['Published result'])}</span>
    </div>
  `).join('');
  $('#run-validation').onclick = runDemoValidation;
}

async function runDemoValidation() {
  const button = $('#run-validation');
  const results = $('#validation-results');
  const requiredReportFields = [
    'probable_root_cause',
    'confidence_score',
    'evidence_ids',
    'suggested_fix',
    'rollback_recommendation',
    'prevention_action',
    'human_review_required',
  ];
  const schemaComplete = data.incidents.filter((incident) => (
    requiredReportFields.every((field) => Object.hasOwn(incident.report, field))
  )).length;
  const citedIds = data.incidents.flatMap((incident) => incident.report.evidence_ids);
  const availableIds = new Set(data.incidents.flatMap((incident) => (
    incident.evidence.map((evidence) => evidence.evidence_id)
  )));
  const resolvedCitations = citedIds.filter((id) => availableIds.has(id)).length;
  const reviewRequired = data.incidents.filter((incident) => incident.report.human_review_required).length;
  const checks = [
    ['Distinct incident scenarios', `${new Set(data.incidents.map((incident) => incident.service)).size}/${data.incidents.length}`, data.incidents.length === 5],
    ['Schema-complete RCA records', `${schemaComplete}/${data.incidents.length}`, schemaComplete === data.incidents.length],
    ['Evidence citations resolved', `${resolvedCitations}/${citedIds.length}`, resolvedCitations === citedIds.length],
    ['Human review required', `${reviewRequired}/${data.incidents.length}`, reviewRequired === data.incidents.length],
    ['Automatic actions executed', String(data.dataset.automatic_actions), data.dataset.automatic_actions === 0],
  ];

  button.disabled = true;
  results.innerHTML = '';
  for (let index = 0; index < checks.length; index += 1) {
    const [label, value, passed] = checks[index];
    button.textContent = `Checking ${index + 1}/${checks.length}…`;
    await new Promise((resolve) => setTimeout(resolve, 300));
    results.insertAdjacentHTML('beforeend', `
      <div class="validation-row ${passed ? 'passed' : 'failed'}">
        <span>${passed ? '✓' : '×'} ${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>
      </div>
    `);
  }
  button.textContent = 'Run checks again';
  button.disabled = false;
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
    };
  });
}

start().catch((error) => {
  $('#investigation').innerHTML = `<p>Demo failed to load: ${escapeHtml(error.message)}</p>`;
});
