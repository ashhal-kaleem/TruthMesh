# FactAgent — Pipeline Analysis & API-Reduction Proposal

> **Goal:** reduce Gemini calls from ~24 per claim → **3 per claim**  
> **Constraint:** no code changes yet; design only.

---

## 1. Current Call Inventory (per single claim)

Every row is one Gemini HTTP request.

| # | Location | Method | Purpose | Necessary? |
|---|----------|--------|---------|-----------|
| 1 | `_build_main_graph` → `orchestrator` | `llm.with_structured_output(Router)` | Supervisor decides → `input_ingestor` | **No** – always the same first step |
| 2 | `_build_input_ingestion_graph` → `input_ingestion_node` | `llm.with_structured_output(Router)` | Sub-supervisor decides → `claim_decomposition` | **No** – fixed order |
| 3 | `claim_decomposition_node` | `_llm_structured(claim_decomposition, …)` | Break claim into predicates | ✅ Keep (merge) |
| 4 | `input_ingestion_node` again | `llm.with_structured_output(Router)` | Sub-supervisor decides → `claim_classification` | **No** – fixed order |
| 5 | `claim_classification_node` | `_llm_structured(claim_classification, …)` | Label each subclaim verifiable/non-verifiable | ✅ Keep (merge) |
| 6 | `input_ingestion_node` again | `llm.with_structured_output(Router)` | Sub-supervisor decides → `claim_splitter` | **No** – fixed order |
| 7 | `claim_splitter_node` | `_llm_structured(claim_splitting, …)` | Filter to verifiable subclaims only | ✅ Keep (merge) |
| 8 | `input_ingestion_node` again | `llm.with_structured_output(Router)` | Sub-supervisor decides → FINISH | **No** – fixed order |
| 9 | `orchestrator` | `llm.with_structured_output(Router)` | Main supervisor decides → `query_generator` | **No** – always next step |
| 10 | `query_generation_node` | `_llm_structured(query_generation, …)` | Generate search questions per subclaim | ✅ Keep (merge) |
| 11 | `orchestrator` | `llm.with_structured_output(Router)` | Main supervisor decides → `evidence_seeker` | **No** – always next step |
| 12–N | `evidence_seeking_agent` (ReAct) | `create_react_agent` think steps | Decide which tool to invoke, per query | ✅ Keep (bounded) |
| 13–N | `retrieve._process_content` | `genai.GenerativeModel.generate_content` | Extract relevant sentences from webpage | **No** – pure extraction, rule-based |
| N+1 | `evidence_seeking_node` tail | `llm.with_structured_output(evidence_seeking)` | Re-format ReAct output as structured schema | **No** – duplicate of ReAct output |
| N+2 | `orchestrator` | `llm.with_structured_output(Router)` | Main supervisor decides → `verdict_predictor` | **No** – always next step |
| N+3 | `verdict_prediction_node` | `_llm_structured(verdict_prediction, …)` | Final label + explanation | ✅ Keep |
| N+4 | `orchestrator` | `llm.with_structured_output(Router)` | Main supervisor decides → FINISH | **No** – always last step |

### Concrete count for a typical claim (2 subclaims, 4 search queries)

```
7  calls  — ingestion subgraph (4 supervisor + 3 workers)
5  calls  — main supervisor (decide ingestor / queries / evidence / verdict / FINISH)
1  call   — query_generation
5  calls  — ReAct think steps (1 init + 1 per tool call + 1 final)
4  calls  — _process_content inside retrieve.py (1 per retrieved article)
1  call   — evidence structured-output tail
1  call   — verdict_prediction
─────────
24 calls  total  ← measured from a single run of test_real_claim.py
```

For 4 subclaims × 3 queries the count reaches **40+**.  
The free-tier ceiling is 15 RPM / 1500 RPD, so quota exhausts after
~60 claims/day (daily) or mid-pipeline on a complex claim (rate).

---

## 2. Root Causes

### 2a. Supervisor nodes calling Gemini for a deterministic sequence

Both supervisor nodes (`orchestrator` and `input_ingestion_node`) use an LLM
`Router` to decide the next worker.  The decision is **never actually variable**:

```
input_ingestion always goes:
  claim_decomposition → claim_classification → claim_splitter → FINISH

main graph always goes:
  input_ingestor → query_generator → evidence_seeker → verdict_predictor → FINISH
```

That is **9 wasted supervisor LLM calls** on every claim (4 inner + 5 outer).
There is no conditional branch, no early-exit based on claim type, and no
re-ordering — the LLM just rubber-stamps the same route every time.

### 2b. `_process_content` using a raw Gemini model per retrieved article

`retrieve.py` instantiates a second Gemini model (`GEMINI_MODEL`) and calls
`generate_content` for **every webpage** scraped to "extract relevant sentences."
This is purely extractive work: given query keywords and article text, keep
sentences that overlap.  An LLM is dramatically over-powered for this, and adds
`N_subclaims × N_queries` extra calls.

### 2c. Duplicate structured-output call at end of `evidence_seeking_node`

After the ReAct agent runs (`self.evidence_seeking_agent.invoke(state)`), the
node pulls the final AI text from the agent's messages, then makes a **second
Gemini call** (`llm.with_structured_output(evidence_seeking).invoke(…)`) to
reformat the same content into the `EvidenceSeeking` Pydantic schema.
The ReAct agent's last message is already structured — this call re-packages
what was just produced.

---

## 3. Proposed Architecture: 3 Calls Per Claim

### 3.1 Target call map

| New node | Gemini calls | What it does |
|----------|-------------|--------------|
| `plan_node` | **1** | Single prompt: decompose → classify → filter → generate queries. Returns `{subclaims: [...], queries: {subclaim: [q1, q2, ...]}}` |
| `evidence_node` | **1** (ReAct, bounded) | For each query: run `search_retrieve_news` deterministically; extract evidence without Gemini; produce evidence dict directly from agent's final structured message |
| `verdict_node` | **1** | Verdict prediction (unchanged) |
| **Total** | **3** | |

### 3.2 Changes per component

#### Remove: Both supervisor nodes
`_make_supervisor_node` is deleted.  Neither the main graph nor the ingestion
subgraph needs an LLM router.  The graph becomes a straight line with Python
`add_edge` calls.

**LangGraph impact:**
```python
# Before — supervisor fans out, workers return Command(goto="supervisor")
super_builder.add_edge(START, "supervisor")
# supervisor dynamically routes → workers → supervisor → workers → ... → END

# After — linear, no supervisor
super_builder.add_edge(START, "plan")
super_builder.add_edge("plan", "evidence")
super_builder.add_edge("evidence", "verdict")
super_builder.add_edge("verdict", END)
```

#### Remove: Input ingestion subgraph (`_build_input_ingestion_graph`)
The subgraph exists only to give the inner supervisor something to orchestrate.
With a linear graph, all three steps (decompose, classify, split) merge into one
node.  The `ingestion_graph` attribute and `call_input_ingestion_team` wrapper
are deleted.

#### Merge: claim_decomposition + claim_classification + claim_splitter + query_generation → `plan_node` (1 call)

These four operations are purely analytical and have no side effects.
They transform `claim → (verifiable subclaims, search queries)`.
A single prompt with a combined Pydantic schema achieves the same result:

```python
class Plan(BaseModel):
    subclaims: List[str]          # verifiable predicates only
    queries: Dict[str, List[str]] # subclaim → [search question, ...]
```

The prompt instructs the model to:
1. Decompose the claim into predicate-form subclaims.
2. Drop non-verifiable ones (opinion, future, hypothetical).
3. Generate 2–3 search questions per surviving subclaim.

All the intermediate schemas (`ClaimDecomposition`, `ClaimClassification`,
`ClaimSplitting`, `QueryGeneration`) become internal to the prompt string;
only `Plan` is returned.

#### Remove: `_process_content` Gemini call in `retrieve.py`

Replace with deterministic sentence scoring:

```python
def _process_content(self, query: str, content: str) -> str:
    # Tokenise query into keywords (strip stop-words)
    keywords = {w.lower() for w in query.split() if len(w) > 3}
    sentences = self._split_into_sentences(content)
    # Keep sentences that share ≥ 2 keywords with the query
    relevant = [s for s in sentences
                if sum(1 for k in keywords if k in s.lower()) >= 2]
    return " ".join(relevant[:6])  # cap at 6 sentences
```

This removes `N_subclaims × N_queries` Gemini calls with zero loss in pipeline
quality for the kinds of snippets Serper returns — the snippets are short and
already pre-filtered by the search engine's own relevance ranking.
The `genai` / `GEMINI_MODEL` module-level objects in `retrieve.py` are deleted.

#### Remove: Duplicate structured-output call in `evidence_seeking_node`

The ReAct agent (`create_react_agent`) is prompted (via `evidence_seeking_prompt`)
to produce evidence in structured form in its final message.
The tail call:
```python
structured = self.llm.with_structured_output(evidence_seeking).invoke([
    SystemMessage(content=evidence_seeking_prompt),
    HumanMessage(content=f"Summarize … {final_ai_text}")
])
```
is eliminated.  Instead, `evidence_seeking_node` parses the agent's final
message directly, or the ReAct agent is given a JSON schema in its system
prompt so the last AI message already conforms.

Alternatively: `create_react_agent` can be replaced with a simple
`for query in queries: evidence = search_retrieve_news(query, dataset)`
deterministic loop, making `evidence_node` **0 LLM calls** and pushing the
full reasoning into `plan_node` and `verdict_node`.  This is the simplest path
to 2 calls total.

#### Bound: ReAct agent tool-call depth (if kept)

If the ReAct loop is retained for genuine adaptivity (e.g., issuing a follow-up
query when the first returns nothing), add a hard cap:

```python
self.evidence_seeking_agent = create_react_agent(
    self.llm,
    tools=[search_retrieve_news],
    prompt=evidence_seeking_prompt,
)
# At invoke time:
agent_result = self.evidence_seeking_agent.invoke(
    state,
    config={"recursion_limit": 2 * len(queries) + 1}  # ≤ 2 LLM steps per query
)
```

This guarantees the evidence node never exceeds 1 LLM call per claim (when
queries are pre-planned and the agent runs them without backtracking).

---

## 4. LangGraph Structural Diff

### Before

```
super_graph
│
├── START → supervisor (LLM router)
│                │
│      ┌─────────┼─────────────────────────┐
│      ↓         ↓                         ↓
│  input_ingestor  query_generator   …   verdict_predictor
│      │         (each returns            │
│      ↓          Command(goto=           ↓
│  ingestion_graph (subgraph)          supervisor))
│      ├── START → inner_supervisor (LLM router)
│      │                │
│      │   ┌────────────┼────────────┐
│      │   ↓            ↓           ↓
│      │  claim_decomp  claim_class  claim_split
│      │   (each → Command(goto=inner_supervisor))
│      └─────────────────────────────────────────
│
└── END
```

- 2 supervisor nodes, both LLM-based
- 1 nested subgraph
- Workers return `Command(goto="supervisor")` → supervisor re-invoked after every worker
- 9 supervisor LLM calls before any real work is done

### After

```
super_graph (no subgraph)
│
START → plan_node → evidence_node → verdict_node → END
```

- 0 supervisor nodes
- 0 nested subgraphs
- Plain `add_edge` — LangGraph only routes, never calls Gemini for routing
- Workers are plain functions; `Command` is replaced by normal state updates
- The `State` schema loses the `next: str` field (no longer needed)

---

## 5. Files Affected (no changes yet)

| File | Action | Reason |
|------|--------|--------|
| `src/main_agent.py` | Major refactor | Remove supervisors, subgraph, duplicate structured call; add `plan_node` |
| `src/prompts/input_ingestion.py` | Simplify | Keep schemas as reference; write combined `Plan` schema |
| `src/prompts/query_generation.py` | Merge into plan prompt | Standalone `QueryGeneration` class no longer called separately |
| `src/prompts/claim_decomposition.py` | Delete or keep as re-export only | All logic moves to plan prompt |
| `src/tools/retrieve.py` | Replace `_process_content` | Remove `genai` import; implement keyword-overlap extraction |
| `src/prompts/evidence_seeking.py` | Keep schema | `EvidenceSeeking` still used for output; prompt simplified |
| `src/prompts/verdict_prediction.py` | No change | Already optimal — 1 call, good schema |

---

## 6. Agentic Quality Preserved

Reducing calls does **not** make the system less agentic.  The three genuine
intelligence tasks remain:

1. **Claim understanding** (`plan_node`): The model must read the claim, decide
   which parts are checkable facts, and phrase queries that will surface
   evidence — this requires reasoning, not just extraction.

2. **Evidence retrieval** (`evidence_node`): Real tool use against the live web
   (Serper + Selenium scraping), respecting dataset date limits, source
   credibility scoring, and bot-detection avoidance.  Optional ReAct loop
   preserves adaptive follow-up queries.

3. **Verdict reasoning** (`verdict_node`): Multi-source evidence synthesis,
   voting logic, and natural-language justification.

The only things removed are **routing LLMs** (which never reason about the
claim) and a **keyword-extraction LLM** (which is trivially replaceable by a
string-overlap heuristic).

---

## 7. Implementation Order (when ready to code)

1. `retrieve.py` — replace `_process_content` first (isolated, easy to test)
2. `prompts/input_ingestion.py` — add combined `Plan` schema + merged prompt
3. `main_agent.py` — rewrite `_build_graphs` as linear graph; add `plan_node`; remove supervisors and subgraph; remove tail structured-output call
4. `prompts/claim_decomposition.py` + `prompts/query_generation.py` — update/merge
5. Run `test_init.py` (zero API calls) then `test_real_claim.py` to verify 3-call budget
