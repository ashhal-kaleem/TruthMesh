"""
main_agent.py — TruthMesh (2-call architecture)
────────────────────────────────────────────────
LangGraph pipeline:

  START → plan_node → evidence_node → verdict_node → END

Gemini calls per claim:
  1. plan_node     — decompose claim + filter subclaims + generate queries (1 call)
  2. verdict_node  — all evidence → label + explanation                    (1 call)

evidence_node makes ZERO Gemini calls.  It is a deterministic Python loop
that calls search_retrieve_news() once per (subclaim, query) pair and
assembles the evidence dict directly.  No ReAct agent, no recursion budget,
no JSON-parsing fallback needed.

Sentence-level relevance extraction inside retrieve.py is also deterministic
(keyword-overlap scoring) — confirmed zero Gemini calls there.

Total Gemini generation calls per /check_claim request: exactly 2.
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


# ── Shared state ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """Flat state dict threaded through the three pipeline nodes."""
    claim: str              # original user claim (set at START)
    image: str              # optional base64 data URI or file path
    past_claims: list       # optional past relevant claims from RAG
    plan: dict              # output of plan_node  {subclaims_with_queries: [...]}
    evidence: dict          # output of evidence_node {subclaims_with_query_evidence: [...]}
    verdict: dict           # output of verdict_node  {result: {label, explanation}}
    messages: List[BaseMessage]  # kept for graph state compatibility


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
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        self.dataset = dataset
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=GOOGLE_API_KEY,
            temperature=temperature,
        )

        self.vector_store = create_vector_store()
        self._build_graph()

    # ── Node 1: plan ──────────────────────────────────────────────────────────

    def _plan_node(self, state: AgentState) -> AgentState:
        """
        GEMINI CALL #1
        Single structured-output call that decomposes the claim into verifiable
        subclaims and generates 2-3 search queries per subclaim.

        Input:  claim text + optional image + optional RAG past_claims context
        Output: Plan {subclaims_with_queries: [{subclaim, queries}, ...]}
        """
        claim = state["claim"]
        image = state.get("image")
        past_claims = state.get("past_claims", [])

        if past_claims:
            past_text = (
                "\n\nSimilar past claims and their verdicts:\n"
                + json.dumps(past_claims, indent=2)
            )
            base_claim_text = f"Claim to fact-check:\n{claim}{past_text}"
        else:
            base_claim_text = f"Claim to fact-check:\n{claim}"

        if image:
            # Accept either a file path or an existing data URI
            if os.path.exists(image):
                with open(image, "rb") as image_file:
                    encoded = base64.b64encode(image_file.read()).decode("utf-8")
                ext = image.lower().rsplit(".", 1)[-1]
                mime = f"image/{ext}" if ext in ("png", "jpeg", "jpg", "webp") else "image/jpeg"
                image_url = f"data:{mime};base64,{encoded}"
            else:
                image_url = image  # already a data URI

            human_content = [
                {"type": "text", "text": base_claim_text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
        else:
            human_content = base_claim_text

        messages = [
            SystemMessage(content=plan_prompt),
            HumanMessage(content=human_content),
        ]
        plan_obj: Plan = self.llm.with_structured_output(Plan).invoke(messages)
        plan_dict = plan_obj.model_dump()

        logging.info(
            "[plan_node] %d verifiable subclaim(s) extracted",
            len(plan_dict.get("subclaims_with_queries", [])),
        )
        return {**state, "plan": plan_dict}

    # ── Node 2: evidence (deterministic — ZERO Gemini calls) ──────────────────

    def _evidence_node(self, state: AgentState) -> AgentState:
        """
        NO GEMINI CALLS.

        Iterates over every (subclaim, query) pair produced by plan_node and
        calls search_retrieve_news() directly — a pure Python + Serper API
        function that returns a structured JSON string with no LLM involvement.

        The evidence dict is assembled in Python and stored in state for
        verdict_node.  No ReAct loop, no recursion budget, no JSON fallback.
        """
        subclaims_with_queries = state["plan"].get("subclaims_with_queries", [])

        # Non-verifiable early-exit: plan_node returns a single sentinel entry
        if not subclaims_with_queries or (
            len(subclaims_with_queries) == 1
            and subclaims_with_queries[0].get("subclaim") == "NON_VERIFIABLE"
        ):
            logging.info("[evidence_node] Claim is non-verifiable — skipping retrieval")
            return {**state, "evidence": {"subclaims_with_query_evidence": []}}

        result_subclaims = []

        for sq in subclaims_with_queries:
            subclaim = sq.get("subclaim", "")
            queries = sq.get("queries", [])
            queries_with_evidence = []

            for query in queries:
                # Direct tool call — no LLM involved
                raw = search_retrieve_news.invoke(
                    {"query": query, "dataset": self.dataset}
                )

                # raw is a JSON string (or "" on failure); parse it into a list
                evidence_items = []
                if raw:
                    try:
                        item = json.loads(raw)
                        # search_retrieve_news returns a single dict per query
                        evidence_items = [item] if isinstance(item, dict) else []
                    except (json.JSONDecodeError, TypeError):
                        # Treat unparseable raw text as a plain-text excerpt
                        evidence_items = [{
                            "url": "",
                            "title": "",
                            "excerpt": str(raw),
                            "credibility_score": "Unknown",
                            "bias_label": "Unknown",
                        }]

                queries_with_evidence.append({
                    "query": query,
                    "evidence": evidence_items,
                })
                logging.debug(
                    "[evidence_node] subclaim=%r query=%r items=%d",
                    subclaim[:60],
                    query[:60],
                    len(evidence_items),
                )

            result_subclaims.append({
                "subclaim": subclaim,
                "queries_with_evidence": queries_with_evidence,
            })

        evidence_dict = {"subclaims_with_query_evidence": result_subclaims}
        total_items = sum(
            len(qe["evidence"])
            for sc in result_subclaims
            for qe in sc["queries_with_evidence"]
        )
        logging.info(
            "[evidence_node] %d subclaim(s), %d evidence item(s) collected "
            "(0 Gemini calls)",
            len(result_subclaims),
            total_items,
        )
        return {**state, "evidence": evidence_dict}

    # ── Node 3: verdict ───────────────────────────────────────────────────────

    def _verdict_node(self, state: AgentState) -> AgentState:
        """
        GEMINI CALL #2
        Given the original claim and all gathered evidence, produce a final
        verdict: label (SUPPORT | REFUTE | UNCERTAIN) + natural-language
        explanation.
        """
        claim = state["claim"]
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
        verdict_obj: VerdictPrediction = (
            self.llm.with_structured_output(VerdictPrediction).invoke(messages)
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

        START → plan_node → evidence_node → verdict_node → END

        No supervisor nodes.  No sub-graphs.  No LLM routing.
        Each add_edge is a hard Python transition — no extra Gemini calls.
        """
        builder = StateGraph(AgentState)

        builder.add_node("plan", self._plan_node)
        builder.add_node("evidence", self._evidence_node)
        builder.add_node("verdict", self._verdict_node)

        builder.add_edge(START, "plan")
        builder.add_edge("plan", "evidence")
        builder.add_edge("evidence", "verdict")
        builder.add_edge("verdict", END)

        self.graph = builder.compile()

    # ── Public API ────────────────────────────────────────────────────────────

    def process_claim(
        self,
        claim: str,
        image: str = None,
        recursion_limit: int = 50,
        verbose: bool = False,
    ) -> dict:
        """
        Run the full fact-checking pipeline on a single claim.

        Args:
            claim:           The text claim to verify.
            image:           Optional base64 data URI or file path for an image.
            recursion_limit: Hard cap on LangGraph recursion (default 50).
            verbose:         Print each node's output while streaming.

        Returns:
            dict with keys: claim, label, explanation, plan, evidence,
                            past_claims, image_analyzed
        """
        past_claims = []
        try:
            docs = self.vector_store.similarity_search(claim, k=2)
            for doc in docs:
                past_claims.append({
                    "claim": doc.page_content,
                    "verdict": doc.metadata.get("verdict"),
                    "explanation": doc.metadata.get("explanation"),
                })
        except Exception:
            pass

        initial_state: AgentState = {
            "claim": claim,
            "image": image,
            "past_claims": past_claims,
            "plan": {},
            "evidence": {},
            "verdict": {},
            "messages": [],
        }

        steps = []
        for step in self.graph.stream(
            initial_state,
            config={"recursion_limit": recursion_limit},
        ):
            if verbose:
                node_name = list(step.keys())[0]
                print(f"\n{'-'*50}\n[{node_name}]")
                node_state = step[node_name]
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

        label = final.get("verdict", {}).get("result", {}).get("label", "unknown")
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
                logging.warning(
                    "[process_claim] RAG write-back failed (non-fatal): %s", e
                )

        return {
            "claim": claim,
            "label": label,
            "explanation": explanation,
            "plan": steps[0].get("plan", {}).get("plan", {}) if steps else {},
            "evidence": (
                steps[1].get("evidence", {}).get("evidence", {})
                if len(steps) > 1 else {}
            ),
            "past_claims": past_claims,
            "image_analyzed": image is not None,
        }

    def process_multiple_claims(
        self,
        claims: List[str],
        image: str = None,
        recursion_limit: int = 50,
        verbose: bool = False,
    ) -> List[dict]:
        """
        Process a list of claims sequentially.

        Returns:
            List of result dicts (same structure as process_claim).
        """
        results = []
        for i, claim in enumerate(claims):
            if verbose:
                print(f"\n{'='*55}\nClaim {i+1}/{len(claims)}: {claim}\n{'='*55}")
            results.append(
                self.process_claim(claim, image=image,
                                   recursion_limit=recursion_limit,
                                   verbose=verbose)
            )
        return results
