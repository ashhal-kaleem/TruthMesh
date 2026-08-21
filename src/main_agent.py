"""
main_agent.py — TruthMesh (3-call architecture)
────────────────────────────────────────────────
LangGraph pipeline:

  START → plan_node → evidence_node → verdict_node → END

Gemini calls per claim:
  1. plan_node      — decompose + filter + generate queries   (1 call)
  2. evidence_node  — bounded ReAct loop; tool = search_retrieve_news (1 call)
  3. verdict_node   — multi-source evidence → label + explanation (1 call)

All LLM-based supervisors, the ingestion subgraph, and the duplicate
structured-output call at the end of evidence_seeking have been removed.
Article relevance extraction inside retrieve.py is now deterministic
(keyword-overlap scoring) — zero extra Gemini calls there.
"""

import os
import json
import logging
import base64
from typing import List, TypedDict, Annotated

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import create_react_agent

from src.prompts.input_ingestion import Plan, plan_prompt
from src.prompts.evidence_seeking import (
    EvidenceSeeking,
    SubclaimWithQueryEvidence,
    QueryWithEvidence,
    evidence_seeking_prompt,
)
from src.prompts.verdict_prediction import VerdictPrediction, verdict_prediction_prompt
from src.tools.retrieve import search_retrieve_news
from src.vector_store import create_vector_store

load_dotenv()


# ── Shared state ──────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """Flat state dict threaded through the three pipeline nodes."""
    claim: str              # original user claim (set at START)
    image: str              # optional image path or base64 data
    past_claims: list       # optional past relevant claims from RAG
    plan: dict              # output of plan_node  {subclaims_with_queries: [...]}
    evidence: dict          # output of evidence_node {subclaims_with_query_evidence: [...]}
    verdict: dict           # output of verdict_node  {label, explanation}
    messages: List[BaseMessage]  # kept for compatibility with MessagesState helpers


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
            dataset:     Dataset name — governs article date limits in retrieval
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

        self.embeddings = None  # managed by vector_store module
        self.vector_store = create_vector_store()

        # The only ReAct agent — used inside evidence_node.
        # It is the sole agentic component: it decides when evidence is
        # sufficient and may issue follow-up queries adaptively.
        self.evidence_agent = create_react_agent(
            self.llm,
            tools=[search_retrieve_news],
            prompt=evidence_seeking_prompt,
        )

        self._build_graph()

    # ── Node 1: plan ──────────────────────────────────────────────────────────

    def _plan_node(self, state: AgentState) -> AgentState:
        """
        GEMINI CALL #1
        Single LLM call that replaces four old nodes:
          claim_decomposition + claim_classification +
          claim_splitter + query_generation

        Output: Plan {subclaims_with_queries: [{subclaim, queries}, ...]}
        """
        claim = state["claim"]
        image = state.get("image")
        past_claims = state.get("past_claims", [])
        
        if past_claims:
            past_text = "\n\nSimilar past claims and their verdicts:\n" + json.dumps(past_claims, indent=2)
            base_claim_text = f"Claim to fact-check:\n{claim}{past_text}"
        else:
            base_claim_text = f"Claim to fact-check:\n{claim}"
        
        if image:
            if os.path.exists(image):
                with open(image, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    # determine mime type simply based on extension for this mock
                    ext = image.lower().split('.')[-1]
                    mime_type = f"image/{ext}" if ext in ["png", "jpeg", "jpg", "webp"] else "image/jpeg"
                    image_url = f"data:{mime_type};base64,{encoded_string}"
            else:
                image_url = image

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

        # Serialise to plain dict for storage in state
        plan_dict = plan_obj.model_dump()

        logging.info(
            "[plan_node] %d verifiable subclaim(s) extracted",
            len(plan_dict.get("subclaims_with_queries", [])),
        )
        return {**state, "plan": plan_dict}

    # ── Node 2: evidence ──────────────────────────────────────────────────────

    def _evidence_node(self, state: AgentState) -> AgentState:
        """
        GEMINI CALL #2  (bounded ReAct loop)
        The evidence agent uses search_retrieve_news to gather web evidence.
        It is the only genuinely agentic step: it decides per-query whether
        the retrieved snippet is sufficient or whether a follow-up is needed.

        The recursion limit is set to  2 * N_queries + 3  so the agent
        cannot make unbounded calls regardless of how many subclaims exist.

        Evidence is assembled from the agent's final AIMessage and parsed
        directly — no second Gemini call for re-formatting.
        """
        plan = state["plan"]
        subclaims_with_queries = plan.get("subclaims_with_queries", [])

        if not subclaims_with_queries or (
            len(subclaims_with_queries) == 1 and
            subclaims_with_queries[0].get("subclaim") == "NON_VERIFIABLE"
        ):
            logging.info("[evidence_node] Claim is non-verifiable — skipping retrieval")
            return {
                **state,
                "evidence": {"subclaims_with_query_evidence": []},
            }

        # Build a prompt summarising the plan so the agent knows what to search
        total_queries = sum(
            len(sq.get("queries", [])) for sq in subclaims_with_queries
        )
        plan_text = json.dumps(subclaims_with_queries, indent=2)
        agent_input = (
            f"Dataset: {self.dataset}\n\n"
            f"You must gather web evidence for the following subclaims and "
            f"their associated search queries.\n\n"
            f"For each (subclaim, query) pair, call search_retrieve_news with "
            f"the query and dataset='{self.dataset}'.  Collect ALL results "
            f"before finishing.\n\n"
            f"Subclaims and queries:\n{plan_text}\n\n"
            f"After collecting all evidence, respond with a JSON object "
            f"matching this exact structure:\n"
            f'{{"subclaims_with_query_evidence": ['
            f'{{"subclaim": "...", "queries_with_evidence": ['
            f'{{"query": "...", "evidence": [ {{"url": "...", "title": "...", "excerpt": "...", "credibility_score": "...", "bias_label": "..."}} ]}}]}}]}}'
        )

        # Cap the recursion: 2 steps per query (think + tool) + buffer
        recursion_cap = max(10, 2 * total_queries + 3)

        agent_result = self.evidence_agent.invoke(
            {"messages": [HumanMessage(content=agent_input)]},
            config={"recursion_limit": recursion_cap},
        )

        # Extract the final AI text from the agent run
        final_text = ""
        for msg in reversed(agent_result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                final_text = (
                    msg.content if isinstance(msg.content, str)
                    else str(msg.content)
                )
                break

        # Parse the JSON the agent was prompted to emit
        evidence_dict = self._parse_evidence_json(
            final_text, subclaims_with_queries
        )

        logging.info(
            "[evidence_node] Evidence gathered for %d subclaim(s)",
            len(evidence_dict.get("subclaims_with_query_evidence", [])),
        )
        return {**state, "evidence": evidence_dict}

    @staticmethod
    def _parse_evidence_json(text: str, fallback_plan: list) -> dict:
        """
        Try to parse the agent's JSON evidence block.
        On failure, build a minimal structure from the plan so verdict_node
        still has something to work with.
        """
        # Strip markdown fences if present
        clean = text.strip()
        for fence in ("```json", "```"):
            if clean.startswith(fence):
                clean = clean[len(fence):]
            if clean.endswith("```"):
                clean = clean[:-3]
        clean = clean.strip()

        # Find the first '{' and last '}' to handle surrounding prose
        start = clean.find('{')
        end = clean.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(clean[start:end + 1])
            except json.JSONDecodeError:
                pass

        # Fallback: wrap raw text as a single evidence blob per subclaim
        logging.warning(
            "[evidence_node] Could not parse agent JSON — using raw text fallback"
        )
        result = []
        for sq in fallback_plan:
            queries_with_evidence = [
                {"query": q, "evidence": [{"url": "Unknown", "title": "Unknown", "excerpt": text, "credibility_score": "Unknown", "bias_label": "Unknown"}]}
                for q in sq.get("queries", [])
            ]
            result.append({
                "subclaim": sq.get("subclaim", ""),
                "queries_with_evidence": queries_with_evidence,
            })
        return {"subclaims_with_query_evidence": result}

    # ── Node 3: verdict ───────────────────────────────────────────────────────

    def _verdict_node(self, state: AgentState) -> AgentState:
        """
        GEMINI CALL #3
        Given the original claim and all gathered evidence, produce a final
        verdict: label (SUPPORT | REFUTE | UNCERTAIN) + natural-language explanation.
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
        Each add_edge is a hard Python transition — zero extra Gemini calls.
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
            recursion_limit: Hard cap on LangGraph recursion (default 50).
            verbose:         Print each node's output while streaming.

        Returns:
            dict with keys: claim, label, explanation, plan, evidence
        """
        past_claims = []
        try:
            docs = self.vector_store.similarity_search(claim, k=2)
            for doc in docs:
                past_claims.append({
                    "claim": doc.page_content,
                    "verdict": doc.metadata.get("verdict"),
                    "explanation": doc.metadata.get("explanation")
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
                print(f"\n{'-'*50}")
                print(f"[{node_name}]")
                node_state = step[node_name]
                if node_name == "plan":
                    print(json.dumps(node_state.get("plan", {}), indent=2))
                elif node_name == "evidence":
                    ev = node_state.get("evidence", {})
                    n = len(ev.get("subclaims_with_query_evidence", []))
                    print(f"  Evidence blocks: {n}")
                elif node_name == "verdict":
                    print(json.dumps(node_state.get("verdict", {}), indent=2))
            steps.append(step)

        # Extract final state from last step
        final = {}
        for step in reversed(steps):
            if "verdict" in step:
                final = step["verdict"]
                break

        label = final.get("verdict", {}).get("result", {}).get("label", "unknown")
        explanation = (
            final.get("verdict", {}).get("result", {}).get("explanation", "")
        )

        if label != "unknown":
            doc = Document(
                page_content=claim,
                metadata={"verdict": label, "explanation": explanation}
            )
            self.vector_store.add_documents([doc])

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
        }

    def process_multiple_claims(
        self,
        claims: List[str],
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
                print(f"\n{'='*55}")
                print(f"Claim {i+1}/{len(claims)}: {claim}")
                print('='*55)
            results.append(self.process_claim(claim, recursion_limit, verbose))
        return results
