import { authHeaders, setSession, clearSession } from './auth';

// ─── Internal data model ───────────────────────────────────────────────────────
// All consumers (Analysis, History, SourceCard) work against this shape:
//
//   {
//     claim:    string,
//     verdict:  'SUPPORTS' | 'REFUTES' | 'NOT ENOUGH INFO',   ← unified
//     confidence: number,   // 0.0 – 1.0
//     reasoning: string,
//     evidence_citations: [
//       { title, url, domain, excerpt, stance, reliability_score, bias_label }
//     ]
//   }
//
// normaliseResponse() maps BOTH the real API shape and the mock shape onto this.

// ─── Verdict normalisation ─────────────────────────────────────────────────────
// Real API emits: SUPPORT | REFUTE | UNCERTAIN
// Mock emits:     SUPPORTS | REFUTES (legacy)
// History sample: SUPPORTS | REFUTES | NOT ENOUGH INFO
// Canonical output: SUPPORTS | REFUTES | NOT ENOUGH INFO
export function normaliseVerdict(raw) {
  switch ((raw || '').toUpperCase().trim()) {
    case 'SUPPORT':
    case 'SUPPORTS':
      return 'SUPPORTS';
    case 'REFUTE':
    case 'REFUTES':
      return 'REFUTES';
    default:
      return 'NOT ENOUGH INFO';
  }
}

// ─── credibility_score string → reliability_score float ───────────────────────
const CREDIBILITY_MAP = { high: 0.9, medium: 0.6, low: 0.25, unknown: 0.4 };

function credibilityToFloat(raw) {
  if (typeof raw === 'number') return raw;
  return CREDIBILITY_MAP[(raw || '').toLowerCase()] ?? 0.4;
}

// ─── Normalise a raw API/mock response → internal model ───────────────────────
function normaliseResponse(raw, claimText) {
  // Detect real-API shape by key presence
  const isRealApi = 'verdict' in raw || 'reasoning' in raw || 'evidence_citations' in raw;

  if (isRealApi) {
    // Real API: { verdict, confidence, reasoning, evidence_citations, claim, ... }
    const citations = (raw.evidence_citations || []).map(c => ({
      title:             c.title   || '',
      url:               c.url     || '',
      domain:            (() => { try { return new URL(c.url).hostname.replace(/^www\./, ''); } catch { return ''; } })(),
      excerpt:           c.excerpt || '',
      stance:            normaliseVerdict(c.bias_label) === 'NOT ENOUGH INFO' ? 'NEUTRAL' : normaliseVerdict(c.bias_label),
      reliability_score: credibilityToFloat(c.credibility_score),
      bias_label:        c.bias_label || 'Unknown',
    }));
    return {
      claim:              raw.claim || claimText || '',
      verdict:            normaliseVerdict(raw.verdict),
      confidence:         typeof raw.confidence === 'number' ? raw.confidence : 0.5,
      reasoning:          raw.reasoning || '',
      evidence_citations: citations,
      past_context_used:  raw.past_context_used  || false,
      image_analyzed:     raw.image_analyzed     || false,
    };
  }

  // Mock shape: { label, explanation, evidence: [...], claim }
  const citations = (raw.evidence || []).map(e => ({
    title:             e.title   || '',
    url:               e.url     || '',
    domain:            e.domain  || '',
    excerpt:           e.snippet || '',
    stance:            normaliseVerdict(e.stance) === 'NOT ENOUGH INFO' ? 'NEUTRAL' : normaliseVerdict(e.stance),
    reliability_score: credibilityToFloat(e.reliability_score),
    bias_label:        'Unknown',
  }));
  return {
    claim:              raw.claim || claimText || '',
    verdict:            normaliseVerdict(raw.label),
    confidence:         typeof raw.confidence === 'number' ? raw.confidence : 0.78,
    reasoning:          raw.explanation || '',
    evidence_citations: citations,
    past_context_used:  false,
    image_analyzed:     false,
  };
}

// ─── Mock response (mirrors real API evidence structure) ───────────────────────
const MOCK_RAW = {
  label: 'REFUTES',
  confidence: 0.91,
  explanation: 'Based on the analysis of 8 evidence sources, the claim contains significant factual inaccuracies. Peer-reviewed studies from Nature Energy (2023) and the DOE Battery Research report found that while recent advancements in sodium-ion and lithium-sulfur chemistries show promise, no current technology achieves more than a 3–5× capacity improvement. Claims of \'1000×\' are not supported by any reproducible experimental data. The single primary source cited is a press release from an early-stage startup with no peer review.',
  evidence: [
    {
      title: 'DOE Battery Technology Report 2023',
      url: 'https://www.energy.gov/oe/battery-technology-2023',
      domain: 'energy.gov',
      snippet: 'Current state-of-the-art lithium-ion cells achieve 250–400 Wh/kg. No lab-scale demonstration has exceeded 5× improvement over baseline.',
      stance: 'REFUTES',
      reliability_score: 0.97,
    },
    {
      title: 'Nature Energy: Advances in Energy Storage',
      url: 'https://www.nature.com/articles/natnenergy2023',
      domain: 'nature.com',
      snippet: 'Sodium-ion chemistries show potential for cost reduction but not for dramatic energy density leaps claimed in popular media.',
      stance: 'REFUTES',
      reliability_score: 0.95,
    },
    {
      title: 'MIT Technology Review – Battery Breakthroughs',
      url: 'https://www.technologyreview.com/battery-breakthroughs',
      domain: 'technologyreview.com',
      snippet: 'Extraordinary claims require extraordinary evidence. This particular claim lacks reproducibility data.',
      stance: 'REFUTES',
      reliability_score: 0.91,
    },
    {
      title: 'ArXiv Preprint: Solid-State Batteries',
      url: 'https://arxiv.org/abs/2301.12345',
      domain: 'arxiv.org',
      snippet: 'Solid-state batteries offer safety improvements. Energy density improvements remain in the 20–40% range in lab conditions.',
      stance: 'NEUTRAL',
      reliability_score: 0.82,
    },
  ],
};

// ─── Config ────────────────────────────────────────────────────────────────────
const API_BASE    = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const IS_MOCK_MODE = import.meta.env.VITE_MOCK_MODE === 'true';

// Allow up to 120 s for the LLM pipeline to complete (cold model loads can be slow).
const REQUEST_TIMEOUT_MS = 120_000;

const mockDelay = (ms = 2200) => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Wraps fetch with an AbortController timeout.
 * Rejects with a typed ApiError on timeout so callers can show a targeted message.
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ApiError(
        'Request timed out — the analysis pipeline is taking longer than expected. Please try again in a moment.',
        408,
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Public API ────────────────────────────────────────────────────────────────
/**
 * Submit a claim for verification.
 * Returns a normalised internal-model object regardless of source.
 * Never silently falls back to mock data on real API errors.
 */
export async function checkClaim(claim, image = null) {
  if (IS_MOCK_MODE) {
    await mockDelay();
    return normaliseResponse({
      ...MOCK_RAW,
      claim,
      image_analyzed: !!image,
    }, claim);
  }

  const formData = new FormData();
  formData.append('claim', claim);
  if (image instanceof File) formData.append('image', image);

  const response = await fetchWithTimeout(`${API_BASE}/check_claim`, {
    method: 'POST',
    headers: { ...authHeaders() },   // Authorization only; browser sets multipart boundary
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new ApiError(
      `Server responded with ${response.status}: ${errorText}`,
      response.status
    );
  }

  const raw = await response.json();
  return normaliseResponse(raw, claim);
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name   = 'ApiError';
    this.status = status;
  }
}

// ─── Auth endpoints ────────────────────────────────────────────────────────────
/** POST /auth/login  (JSON body) → saves session, returns { access_token, username } */
export async function authLogin(username, password) {
  if (IS_MOCK_MODE) {
    await mockDelay(400);
    // Mock: accept any credentials, return a fake token
    const fakeToken = 'mock.' + btoa(JSON.stringify({ sub: '1', username })) + '.sig';
    setSession(fakeToken, { username });
    return { access_token: fakeToken, username };
  }
  const res = await fetchWithTimeout(`${API_BASE}/auth/login`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ username, password }),
  }, 15_000);
  if (!res.ok) {
    const msg = await res.text().catch(() => 'Login failed');
    throw new ApiError(msg, res.status);
  }
  const { access_token } = await res.json();
  setSession(access_token, { username });
  return { access_token, username };
}

/** POST /auth/register (JSON) → returns token directly (no second login call) */
export async function authRegister(username, email, password) {
  if (IS_MOCK_MODE) {
    await mockDelay(400);
    const fakeToken = 'mock.' + btoa(JSON.stringify({ sub: '1', username })) + '.sig';
    setSession(fakeToken, { username });
    return { access_token: fakeToken, username };
  }
  const res = await fetchWithTimeout(`${API_BASE}/auth/register`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ username, email, password }),
  }, 15_000);
  if (!res.ok) {
    const msg = await res.text().catch(() => 'Registration failed');
    throw new ApiError(msg, res.status);
  }
  const { access_token } = await res.json();
  setSession(access_token, { username });
  return { access_token, username };
}

// ─── History endpoint ──────────────────────────────────────────────────────────
/**
 * GET /me/history?page&page_size  (requires auth)
 * Returns raw ClaimHistoryItem[] from the server.
 * Throws ApiError(401) if token missing or expired — caller should logout.
 */
export async function fetchHistory(page = 1, page_size = 20) {
  if (IS_MOCK_MODE) {
    await mockDelay(400);
    return [];  // History page falls back to SAMPLE_HISTORY in mock mode
  }
  const res = await fetchWithTimeout(
    `${API_BASE}/me/history?page=${page}&page_size=${page_size}`,
    { headers: { ...authHeaders() } },
    15_000,
  );
  if (res.status === 401) {
    clearSession();
    throw new ApiError('Session expired. Please log in again.', 401);
  }
  if (!res.ok) throw new ApiError(`History fetch failed: ${res.status}`, res.status);
  return res.json();
}

// ─── Health check ──────────────────────────────────────────────────────────────
/**
 * GET /  — lightweight ping to check if the API is warm.
 * Returns { ok: true, latencyMs } on success, throws ApiError on failure.
 */
export async function pingApi() {
  if (IS_MOCK_MODE) {
    await mockDelay(300);
    return { ok: true, latencyMs: 312 };
  }
  const start = Date.now();
  const res = await fetchWithTimeout(`${API_BASE}/`, {}, 15_000);
  const latencyMs = Date.now() - start;
  if (!res.ok) throw new ApiError(`API responded with ${res.status}`, res.status);
  return { ok: true, latencyMs };
}
