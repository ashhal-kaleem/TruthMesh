"""
main_agent.py — TruthMesh (2-call architecture)
────────────────────────────────────────────────
LangGraph pipeline:

  START → plan_node → evidence_node → verdict_node → END

LLM calls per claim:
  1. plan_node    — decompose claim + generate queries        (1 call)
  2. verdict_node — all evidence → label + explanation        (1 call)

evidence_node makes ZERO LLM calls (deterministic Python + Serper).

Total successful LLM calls per /check_claim request: exactly 2.

Groq fallback policy
────────────────────
Primary LLM: Gemini.
Fallback LLM: Groq (llama-3.3-70b-versatile) — activated per-call only when
  Gemini raises a quota / rate-limit / provider-unavailable error.

Rules:
  • Fallback fires for one failed call only — never restarts the pipeline.
  • Total successful calls remain exactly 2 regardless of which provider
    serves each call.
  • Image-bearing plan_node calls: Groq has no vision API, so the fallback
    is suppressed and the original Gemini error is re-raised.
  • GROQ_API_KEY absent → fallback disabled; original Gemini error re-raised.
  • Non-quota application errors (bad schema, bad key, network timeout, etc.)
    are NOT caught — they propagate immediately.
"""

import os
import json
import logging
import base64
from typing import List, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

from src.prompts.input_ingestion import Plan, plan_prompt
from src.prompts.evidence_seeking import (
    EvidenceSeeking,
    SubclaimWithQueryEvidence,
    QueryWithEvidence,
)
from src.prompts.verdict_prediction import VerdictPrediction, verdict_prediction_prompt
from src.tools.retrieve import search_retrieve_news
from src.vector_store import create_vector_store

load_dotenv()


# ── Groq fallback utilities ───────────────────────────────────────────────────

# Error substrings that indicate a provider quota / rate / availability failure.
# Deliberately narrow: only genuine provider-side transient errors.
_QUOTA_KEYWORDS = (
    "quota",
    "rate limit",
    "rate_limit",
    "resource exhausted",
    "resourceexhausted",
    "too many requests",
    "service unavailable",
    "serviceunavailable",
    "overloaded",
    "429",
    "503",
)


def _is_quota_error(exc: Exception) -> bool:
    """
    Return True only for genuine provider quota / rate-limit / unavailability
    errors.  Authentication failures, bad requests, schema errors, and network
    timeouts are intentionally excluded so they surface immediately.
    """
    msg = str(exc).lower()
    return any(kw in msg for kw in _QUOTA_KEYWORDS)


def _get_groq_llm(temperature: float = 0.2):
    """
    Build a Groq ChatGroq instance if GROQ_API_KEY is set, otherwise None.
    Raises ImportError if langchain-groq is not installed.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return None
    from langchain_groq import ChatGroq  # lazy import — not required at startup
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=groq_key,
        temperature=temperature,
    )


def _invoke_with_fallback(primary_llm, schema, messages, *, has_image: bool, temperature: float = 0.2):
    """
    Call primary_llm.with_structured_output(schema).invoke(messages).

    On a quota/rate/availability error:
      - If has_image is True  → re-raise (Groq has no vision support).
      - If GROQ_API_KEY unset → re-raise.
      - Otherwise             → attempt Groq once and return its result.

    Any other exception propagates immediately without touching Groq.

    Args:
        primary_llm:  The Gemini ChatGoogleGenerativeAI instance.
        schema:       Pydantic model class for structured output.
        messages:     List of LangChain messages to send.
        has_image:    True when the message contains image content.
        temperature:  Forwarded to Groq if fallback is used.

    Returns:
        Parsed Pydantic model instance from whichever provider succeeded.
    """
    try:
        return primary_llm.with_structured_output(schema).invoke(messages)
    except Exception as gemini_exc:
        # Only intercept genuine provider quota/rate/availability failures.
        if not _is_quota_error(gemini_exc):
            raise

        if has_image:
            logging.warning(
                "[fallback] Gemini quota error on image-bearing call — "
                "Groq has no vision support; re-raising. Error: %s", gemini_exc
            )
            raise

        groq_llm = _get_groq_llm(temperature=temperature)
        if groq_llm is None:
            logging.warning(
                "[fallback] Gemini quota error but GROQ_API_KEY not set — "
                "re-raising. Error: %s", gemini_exc
            )
            raise

        logging.warning(
            "[fallback] Gemini quota error — retrying this call on Groq. "
            "Gemini error: %s", gemini_exc
        )
        # Groq call: any failure here propagates normally (no double-fallback).
        return groq_llm.with_structured_output(schema).invoke(messages)


# ── Shared state ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """Flat state dict threaded through the three pipeline nodes."""
    claim:       str               # original user claim (set at START)
    image:       str               # optional base64 data URI or file path
    past_claims: list              # optional past relevant claims from RAG
    plan:        dict              # output of plan_node
    evidence:    dict              # output of evidence_node
    verdict:     dict              # output of verdict_node
    messages:    List[BaseMessage] # kept for graph state compatibility


# ── TruthMesh ─────────────────────────────────────────────────────────────────

class TruthMesh:
    def __init__(
        self,
        dataset: str,
        model_name: str = "gemini-3.6-flash",
        temperature: float = 0.2,
    ):
        """
        Initialise TruthMesh.

        Args:
            dataset:     Controls article date limits in retrieval
                         (feverous | hover | scifact).
            model_name:  Gemini model string (default: gemini-3.6-flash).
            temperature: Sampling temperature (default: 0.2).
        """
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.dataset = dataset
        self.temperature = temperature
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=google_api_key,
            temperature=temperature,
        )

        self.vector_store = create_vector_store()
        self._build_graph()

    # ── Node 1: plan ──────────────────────────────────────────────────────────

    def _plan_node(self, state: AgentState) -> AgentState:
        """
        LLM CALL #1  (Gemini primary; Groq fallback for text-only claims)

        Decomposes the claim into verifiable subclaims and generates 2-3
        search queries per subclaim.  Image content is included when provided,
        but image-bearing calls never fall back to Groq.

        Output: Plan {subclaims_with_queries: [{subclaim, queries}, ...]}
        """
        claim       = state["claim"]
        image       = state.get("image")
        past_claims = state.get("past_claims", [])

        # Build the text portion of the user message
        if past_claims:
            past_text = (
                "\n\nSimilar past claims and their verdicts:\n"
                + json.dumps(past_claims, indent=2)
            )
            base_claim_text = f"Claim to fact-check:\n{claim}{past_text}"
        else:
            base_claim_text = f"Claim to fact-check:\n{claim}"

        has_image = bool(image)

        if has_image:
            # Resolve file path → base64 data URI if needed
            if os.path.exists(image):
                with open(image, "rb") as fh:
                    encoded = base64.b64encode(fh.read()).decode("utf-8")
                ext  = image.lower().rsplit(".", 1)[-1]
                mime = f"image/{ext}" if ext in ("png", "jpeg", "jpg", "webp") else "image/jpeg"
                image_url = f"data:{mime};base64,{encoded}"
            else:
                image_url = image  # already a data URI

            human_content = [
                {"type": "text",      "text": base_claim_text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        else:
            human_content = base_claim_text

        messages = [
            SystemMessage(content=plan_prompt),
            HumanMessage(content=human_content),
        ]

        plan_obj: Plan = _invoke_with_fallback(
            self.llm, Plan, messages,
            has_image=has_image, temperature=self.temperature,
        )
        plan_dict = plan_obj.model_dump()

        logging.info(
            "[plan_node] %d verifiable subclaim(s) extracted",
            len(plan_dict.get("subclaims_with_queries", [])),
        )
        return {**state, "plan": plan_dict}

    # ── Node 2: evidence (deterministic — ZERO LLM calls) ────────────────────

    def _evidence_node(self, state: AgentState) -> AgentState:
        """
        NO LLM CALLS.

        Iterates over every (subclaim, query) pair and calls
        search_retrieve_news() directly — a pure Python + Serper function
        that returns a structured JSON string with no LLM involvement.
        """
        subclaims_with_queries = state["plan"].get("subclaims_with_queries", [])

        # Non-verifiable early-exit
        if not subclaims_with_queries or (
            len(subclaims_with_queries) == 1
            and subclaims_with_queries[0].get("subclaim") == "NON_VERIFIABLE"
        ):
            logging.info("[evidence_node] Claim is non-verifiable — skipping retrieval")
            return {**state, "evidence": {"subclaims_with_query_evidence": []}}

        result_subclaims = []

        for sq in subclaims_with_queries:
            subclaim              = sq.get("subclaim", "")
            queries               = sq.get("queries", [])
            queries_with_evidence = []

            for query in queries:
                raw = search_retrieve_news.invoke(
                    {"query": query, "dataset": self.dataset}
                )
                evidence_items = []
                if raw:
                    try:
                        item = json.loads(raw)
                        evidence_items = [item] if isinstance(item, dict) else []
                    except (json.JSONDecodeError, TypeError):
                        evidence_items = [{
                            "url": "",
                            "title": "",
                            "excerpt": str(raw),
                            "credibility_score": "Unknown",
                            "bias_label": "Unknown",
                        }]

                queries_with_evidence.append({
                    "query":    query,
                    "evidence": evidence_items,
                })
                logging.debug(
                    "[evidence_node] subclaim=%r query=%r items=%d",
                    subclaim[:60], query[:60], len(evidence_items),
                )

            result_subclaims.append({
                "subclaim":              subclaim,
                "queries_with_evidence": queries_with_evidence,
            })

        evidence_dict = {"subclaims_with_query_evidence": result_subclaims}
        total_items = sum(
            len(qe["evidence"])
            for sc in result_subclaims
            for qe in sc["queries_with_evidence"]
        )
        logging.info(
            "[evidence_node] %d subclaim(s), %d evidence item(s) collected (0 LLM calls)",
            len(result_subclaims), total_items,
        )
        return {**state, "evidence": evidence_dict}

    # ── Node 3: verdict ───────────────────────────────────────────────────────

    def _verdict_node(self, state: AgentState) -> AgentState:
        """
        LLM CALL #2  (Gemini primary; Groq fallback — text-only, no image)

        Given the original claim and all gathered evidence, produces a final
        verdict: label (SUPPORT | REFUTE | UNCERTAIN) + explanation.
        Verdict is always text-only so fallback to Groq is always eligible.
        """
        claim    = state["claim"]
        evidence = state["evidence"]

        messages = [
            SystemMessage(content=verdict_prediction_prompt),
            HumanMessage(
                content=(
                    f"Claim: {claim}\n\n"
                    f"Evidence collected:\n"
                    f"{json.dumps(evidence, indent=2)}"
                )
            ),
        ]

        verdict_obj: VerdictPrediction = _invoke_with_fallback(
            self.llm, VerdictPrediction, messages,
            has_image=False, temperature=self.temperature,
        )
        verdict_dict = verdict_obj.model_dump()

        logging.info(
            "[verdict_node] Verdict: %s",
            verdict_dict.get("result", {}).get("label", "unknown"),
        )
        return {**state, "verdict": verdict_dict}

    # ── Graph construction ────────────────────────────────────────────────────

    def _build_graph(self):
        """
        Compile the linear 3-node LangGraph.
        START → plan → evidence → verdict → END
        No supervisor nodes, no sub-graphs, no LLM routing.
        """
        builder = StateGraph(AgentState)
        builder.add_node("plan",     self._plan_node)
        builder.add_node("evidence", self._evidence_node)
        builder.add_node("verdict",  self._verdict_node)
        builder.add_edge(START,       "plan")
        builder.add_edge("plan",      "evidence")
        builder.add_edge("evidence",  "verdict")
        builder.add_edge("verdict",   END)
        self.graph = builder.compile()

    # ── Public API ────────────────────────────────────────────────────────────

    def process_claim(
        self,
        claim:           str,
        image:           str  = None,
        recursion_limit: int  = 50,
        verbose:         bool = False,
    ) -> dict:
        """
        Run the full fact-checking pipeline on a single claim.

        Returns dict with keys:
            claim, label, explanation, plan, evidence, past_claims, image_analyzed
        """
        past_claims = []
        try:
            docs = self.vector_store.similarity_search(claim, k=2)
            for doc in docs:
                past_claims.append({
                    "claim":       doc.page_content,
                    "verdict":     doc.metadata.get("verdict"),
                    "explanation": doc.metadata.get("explanation"),
                })
        except Exception:
            pass

        initial_state: AgentState = {
            "claim":       claim,
            "image":       image,
            "past_claims": past_claims,
            "plan":        {},
            "evidence":    {},
            "verdict":     {},
            "messages":    [],
        }

        steps = []
        for step in self.graph.stream(
            initial_state,
            config={"recursion_limit": recursion_limit},
        ):
            if verbose:
                node_name  = list(step.keys())[0]
                node_state = step[node_name]
                print(f"\n{'-'*50}\n[{node_name}]")
                if node_name == "plan":
                    print(json.dumps(node_state.get("plan", {}), indent=2))
                elif node_name == "evidence":
                    n = len(
                        node_state.get("evidence", {})
                        .get("subclaims_with_query_evidence", [])
                    )
                    print(f"  Evidence blocks: {n}")
                elif node_name == "verdict":
                    print(json.dumps(node_state.get("verdict", {}), indent=2))
            steps.append(step)

        # Extract final state from the verdict step
        final: dict = {}
        for step in reversed(steps):
            if "verdict" in step:
                final = step["verdict"]
                break

        label       = final.get("verdict", {}).get("result", {}).get("label",       "unknown")
        explanation = final.get("verdict", {}).get("result", {}).get("explanation", "")

        # Write result back to RAG so future similar claims get context
        if label != "unknown":
            doc = Document(
                page_content=claim,
                metadata={"verdict": label, "explanation": explanation},
            )
            try:
                self.vector_store.add_documents([doc])
            except Exception as e:
                logging.warning("[process_claim] RAG write-back failed (non-fatal): %s", e)

        return {
            "claim":          claim,
            "label":          label,
            "explanation":    explanation,
            "plan":           steps[0].get("plan", {}).get("plan", {}) if steps else {},
            "evidence":       (
                steps[1].get("evidence", {}).get("evidence", {})
                if len(steps) > 1 else {}
            ),
            "past_claims":    past_claims,
            "image_analyzed": image is not None,
        }

    def process_multiple_claims(
        self,
        claims:          List[str],
        image:           str  = None,
        recursion_limit: int  = 50,
        verbose:         bool = False,
    ) -> List[dict]:
        """Process a list of claims sequentially."""
        results = []
        for i, claim in enumerate(claims):
            if verbose:
                print(f"\n{'='*55}\nClaim {i+1}/{len(claims)}: {claim}\n{'='*55}")
            results.append(
                self.process_claim(
                    claim, image=image,
                    recursion_limit=recursion_limit,
                    verbose=verbose,
                )
            )
        return results
