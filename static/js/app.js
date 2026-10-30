// Enterprise IT Support Agentic RAG Copilot - Frontend Application
// Features: Keycloak RBAC Client, Presidio PII Indicators, NeMo Guardrails Telemetry

const chat = document.getElementById('chat');
const form = document.getElementById('chatForm');
const question = document.getElementById('question');
const sendBtn = document.getElementById('sendBtn');
const trace = document.getElementById('trace');
const traceLatency = document.getElementById('traceLatency');
const sourceUsed = document.getElementById('sourceUsed');
const retrievalMode = document.getElementById('retrievalMode');
const piiStatus = document.getElementById('piiStatus');
const guardrailStatus = document.getElementById('guardrailStatus');

const roleSelector = document.getElementById('roleSelector');
const userPill = document.getElementById('userPill');
const rolePill = document.getElementById('rolePill');

// Current Keycloak Session / JWT State
let currentToken = '';
let currentRole = 'employee';
let currentUsername = 'employee.demo';

// Initialize session with demo JWT for default role
async function updateSession(role) {
  currentRole = role;
  if (role === 'admin') {
    currentUsername = 'admin.nova';
  } else if (role === 'it_support') {
    currentUsername = 'tech.support';
  } else {
    currentUsername = 'employee.demo';
  }

  userPill.textContent = currentUsername;
  rolePill.textContent = `ROLE_${role.toUpperCase()}`;

  try {
    const res = await fetch('/api/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: currentUsername,
        role: role,
        department: role === 'admin' ? 'Security Operations' : (role === 'it_support' ? 'IT Helpdesk' : 'Retail Operations')
      })
    });
    if (res.ok) {
      const data = await res.json();
      currentToken = data.access_token;
      console.log(`[Keycloak RBAC] Session token minted for ${currentUsername} (${role})`);
    }
  } catch (err) {
    console.warn('Could not acquire mock token:', err);
  }
}

roleSelector.addEventListener('change', (e) => {
  updateSession(e.target.value);
});

// Helper functions for safe rendering
function escapeHtml(s = '') {
  return String(s).replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

function formatText(s = '') {
  return escapeHtml(s).replace(/\n/g, '<br>');
}

function addMessage(role, text, source = '', citations = [], piiRedacted = false, detectedPii = []) {
  const wrap = document.createElement('div');
  wrap.className = `message ${role}`;

  let piiBadge = '';
  if (piiRedacted && detectedPii && detectedPii.length) {
    const types = [...new Set(detectedPii.map(p => p.entity_type))].join(', ');
    piiBadge = `<div class="pii-redacted-badge">🛡️ Presidio Shield: Redacted ${escapeHtml(types)}</div>`;
  }

  let citeHtml = '';
  if (citations && citations.length) {
    const pills = citations.map(c => {
      if (c.url) {
        return `<a class="citation-pill" href="${escapeHtml(c.url)}" target="_blank" rel="noopener">🌐 ${escapeHtml(c.title)}</a>`;
      }
      return `<span class="citation-pill">📄 ${escapeHtml(c.title)}</span>`;
    }).join(' ');
    citeHtml = `<div class="citations"><strong>Knowledge Citations:</strong><br>${pills}</div>`;
  }

  const sourceBadge = source ? `<div class="answer-source">Verified Source: ${escapeHtml(source)}</div>` : '';
  const avatar = role === 'user' ? '' : '<div class="avatar">AI</div>';

  wrap.innerHTML = `
    ${avatar}
    <div class="bubble">
      ${piiBadge}
      <div>${formatText(text)}</div>
      ${sourceBadge}
      ${citeHtml}
    </div>
  `;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

function renderTrace(items = []) {
  if (!items || !items.length) {
    trace.innerHTML = '<div class="empty">No trace available.</div>';
    return;
  }
  trace.innerHTML = items.map(x => {
    let extraClass = '';
    if (x.includes('Presidio') || x.includes('NeMo Guardrails')) {
      extraClass = x.includes('BLOCKED') ? 'trace-blocked' : 'trace-guard';
    }
    return `<div class="trace-item ${extraClass}">${escapeHtml(x)}</div>`;
  }).join('');
  trace.scrollTop = trace.scrollHeight;
}

async function askAgent(q) {
  addMessage('user', q);
  question.value = '';
  renderTrace(['[1] Presidio PII Scan initializing...', '[2] NeMo Guardrails evaluation pending...']);
  
  sourceUsed.textContent = 'Processing...';
  retrievalMode.textContent = 'Hybrid RAG';
  piiStatus.textContent = 'Analyzing...';
  guardrailStatus.textContent = 'Evaluating...';
  traceLatency.textContent = '...';

  sendBtn.disabled = true;

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (currentToken) {
      headers['Authorization'] = `Bearer ${currentToken}`;
    }

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ question: q })
    });

    const data = await res.json();
    if (!res.ok) {
      const errDetail = typeof data.detail === 'object' ? JSON.stringify(data.detail) : (data.detail || 'Request failed');
      throw new Error(errDetail);
    }

    // Update Telemetry
    traceLatency.textContent = `${data.latency_ms || 0} ms`;
    sourceUsed.textContent = data.source_used || 'completed';
    retrievalMode.textContent = data.retrieval_mode || 'Hybrid';
    piiStatus.textContent = data.pii_redacted ? `Redacted (${data.detected_pii.length})` : 'Clean (0)';
    guardrailStatus.textContent = data.guardrails_blocked ? 'BLOCKED' : 'Passed';

    renderTrace(data.trace || []);
    addMessage(
      'assistant',
      data.answer,
      data.source_used,
      data.citations || [],
      data.pii_redacted,
      data.detected_pii || []
    );

  } catch (err) {
    addMessage('assistant', `⚠️ **Error**: ${err.message}`);
    renderTrace(['Workflow execution terminated due to error.']);
    sourceUsed.textContent = 'Error';
    guardrailStatus.textContent = 'Error';
  } finally {
    sendBtn.disabled = false;
  }
}

form.addEventListener('submit', e => {
  e.preventDefault();
  const q = question.value.trim();
  if (q) askAgent(q);
});

// Clickable demo example chips
document.querySelectorAll('.example').forEach(b => {
  b.addEventListener('click', () => askAgent(b.textContent.trim()));
});

// ==========================================
// MODAL 1: DOCUMENT INGESTION (ADMIN)
// ==========================================
const uploadModal = document.getElementById('uploadModal');
document.getElementById('openUpload').onclick = () => {
  uploadModal.classList.remove('hidden');
};
document.getElementById('closeUpload').onclick = () => {
  uploadModal.classList.add('hidden');
};

document.getElementById('uploadBtn').onclick = async () => {
  const file = document.getElementById('fileInput').files[0];
  const key = document.getElementById('adminKey').value;
  const statusEl = document.getElementById('uploadStatus');

  if (!file) {
    statusEl.textContent = 'Please choose a file (.pdf, .txt, .md, .docx).';
    return;
  }

  statusEl.textContent = 'Indexing document into Dense & Sparse BM25 stores...';
  const fd = new FormData();
  fd.append('file', file);

  const headers = {};
  if (currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
  }
  if (key) {
    headers['X-Admin-Key'] = key;
  }

  try {
    const r = await fetch('/api/ingest', {
      method: 'POST',
      headers: headers,
      body: fd
    });
    const d = await r.json();
    if (!r.ok) {
      const msg = typeof d.detail === 'object' ? JSON.stringify(d.detail) : (d.detail || 'Upload failed');
      throw new Error(msg);
    }
    statusEl.innerHTML = `✅ <strong>Indexed</strong>: ${escapeHtml(d.file)} (${d.chunks} chunks). Dense + BM25 updated!`;
  } catch (e) {
    statusEl.innerHTML = `❌ <strong>Error</strong>: ${escapeHtml(e.message)}`;
  }
};

// ==========================================
// MODAL 2: AUDIT & COMPLIANCE LOGS (IT SUPPORT / ADMIN)
// ==========================================
const auditModal = document.getElementById('auditModal');
const auditTableBody = document.getElementById('auditTableBody');

async function loadAuditLogs() {
  auditTableBody.innerHTML = '<tr><td colspan="7" class="text-center">Loading audit records...</td></tr>';
  const headers = {};
  if (currentToken) {
    headers['Authorization'] = `Bearer ${currentToken}`;
  }

  try {
    const res = await fetch('/api/audit?limit=25', { headers });
    const data = await res.json();

    if (!res.ok) {
      const err = typeof data.detail === 'object' ? JSON.stringify(data.detail) : (data.detail || 'Access denied');
      auditTableBody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:#ef4444;">🔒 ${escapeHtml(err)}</td></tr>`;
      return;
    }

    if (!data.audits || !data.audits.length) {
      auditTableBody.innerHTML = '<tr><td colspan="7" class="text-center">No audit records found.</td></tr>';
      return;
    }

    auditTableBody.innerHTML = data.audits.map(a => {
      const timeStr = a.created_at ? a.created_at.substring(11, 19) : '--';
      let statusBadge = '<span class="status-badge status-passed">PASSED</span>';
      if (a.guardrail_status && a.guardrail_status.includes('BLOCKED')) {
        statusBadge = `<span class="status-badge status-blocked">${escapeHtml(a.guardrail_status)}</span>`;
      } else if (a.guardrail_status && a.guardrail_status.includes('REDACTED')) {
        statusBadge = '<span class="status-badge status-redacted">PII REDACTED</span>';
      }

      return `
        <tr>
          <td>${escapeHtml(timeStr)}</td>
          <td><code>${escapeHtml(a.username || a.user_id)}</code></td>
          <td>${escapeHtml((a.roles || []).join(', '))}</td>
          <td title="${escapeHtml(a.question)}">${escapeHtml(a.question.substring(0, 45))}${a.question.length > 45 ? '...' : ''}</td>
          <td>${statusBadge}</td>
          <td><code>${escapeHtml(a.source_used)}</code></td>
          <td>${escapeHtml(a.latency_ms)} ms</td>
        </tr>
      `;
    }).join('');

  } catch (err) {
    auditTableBody.innerHTML = `<tr><td colspan="7" class="text-center" style="color:#ef4444;">Error: ${escapeHtml(err.message)}</td></tr>`;
  }
}

document.getElementById('openAudit').onclick = () => {
  auditModal.classList.remove('hidden');
  loadAuditLogs();
};

document.getElementById('closeAudit').onclick = () => {
  auditModal.classList.add('hidden');
};

document.getElementById('refreshAuditBtn').onclick = () => {
  loadAuditLogs();
};

// Initialize with default Employee role
updateSession('employee');
