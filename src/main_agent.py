from typing import Literal
from langchain_core.language_models.chat_models import BaseChatModel
from typing import TypedDict
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import Command
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv
from src.prompts.claim_decomposition import *
from src.prompts.query_generation import *
from src.prompts.evidence_seeking import *
from src.prompts.verdict_prediction import *
from src.tools.retrieve import search_retrieve_news
import os
import json
load_dotenv()

class State(MessagesState):
    next: str

class FactAgent:
    def __init__(self, dataset: str, model_name: str = "gemini-3.6-flash", temperature: float = 0.2):
        """
        Initialize the FactAgent with specified model and temperature.

        Args:
            dataset: Dataset name (feverous, hover, scifact)
            model_name: The Gemini model to use (default: gemini-3.6-flash)
            temperature: The temperature for the model (default: 0.2)
        """
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        self.dataset = dataset
        self.llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=GOOGLE_API_KEY, temperature=temperature)
        self._setup_agents()
        self._build_graphs()

    def _make_supervisor_node(self, members: list[str]):
        """Create a supervisor node for managing conversation between workers."""
        options = ["FINISH"] + members
        system_prompt = (
            "You are a supervisor tasked with managing a conversation between the"
            f" following workers: {members}. Given the following user request and dataset {self.dataset},"
            " respond with the worker to act next. Each worker will perform a"
            " task and respond with their results and status. When finished,"
            " respond with FINISH."
        )

        class Router(TypedDict):
            """Worker to route to next. If no workers needed, route to FINISH."""
            next: Literal[*options]

        def supervisor_node(state: State) -> Command[Literal[*members, "__end__"]]:
            """An LLM-based router."""
            messages = [
                {"role": "system", "content": system_prompt},
            ] + state["messages"]
            response = self.llm.with_structured_output(Router, method="function_calling").invoke(messages)
            goto = response["next"]
            if goto == "FINISH":
                goto = END
            return Command(goto=goto, update={"next": goto})

        return supervisor_node

    def _llm_structured(self, schema, prompt: str, state: State):
        """
        Call LLM with structured output. Always ends with a HumanMessage so
        Gemini doesn't reject the conversation as 'model prefilling'.
        """
        messages = [SystemMessage(content=prompt)] + list(state["messages"])
        return self.llm.with_structured_output(schema).invoke(messages)

    def _setup_agents(self):
        """Setup all the individual agents."""
        # Only the evidence seeker needs a ReAct loop (uses search tool).
        # All other agents are pure LLM calls handled directly in their nodes.
        self.evidence_seeking_agent = create_react_agent(
            self.llm, tools=[search_retrieve_news], prompt=evidence_seeking_prompt
        )

    def _build_graphs(self):
        """Build the state graphs for the workflow."""
        self._build_input_ingestion_graph()
        self._build_main_graph()

    def _build_input_ingestion_graph(self):
        """Build the input ingestion subgraph."""
        def claim_decomposition_node(state: State) -> Command[Literal["supervisor"]]:
            structured = self._llm_structured(claim_decomposition, claim_decomposition_prompt, state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=str(structured["subclaims"]), name="claim_decomposition")
                    ]
                },
                goto="supervisor",
            )

        def claim_classification_node(state: State) -> Command[Literal["supervisor"]]:
            structured = self._llm_structured(claim_classification, claim_classification_prompt, state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=str(structured["subclaim_type_dict"]), name="claim_classification")
                    ]
                },
                goto="supervisor",
            )

        def claim_splitter_node(state: State) -> Command[Literal["supervisor"]]:
            structured = self._llm_structured(claim_splitting, claim_splitter_prompt, state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=str(structured["subclaims"]), name="claim_splitter")
                    ]
                },
                goto="supervisor",
            )

        input_ingestion_node = self._make_supervisor_node(
            ["claim_decomposition", "claim_classification", "claim_splitter"]
        )

        input_ingester = StateGraph(State)
        input_ingester.add_node("supervisor", input_ingestion_node)
        input_ingester.add_node("claim_decomposition", claim_decomposition_node)
        input_ingester.add_node("claim_classification", claim_classification_node)
        input_ingester.add_node("claim_splitter", claim_splitter_node)
        input_ingester.add_edge(START, "supervisor")

        self.ingestion_graph = input_ingester.compile()

    def _build_main_graph(self):
        """Build the main workflow graph."""
        def call_input_ingestion_team(state: State) -> Command[Literal["supervisor"]]:
            response = self.ingestion_graph.invoke({"messages": state["messages"][-1]})
            return Command(
                update={
                    "messages": [
                        HumanMessage(
                            content=response["messages"][-1].content, name="input_ingestor"
                        )
                    ]
                },
                goto="supervisor",
            )

        def query_generation_node(state: State) -> Command[Literal["supervisor"]]:
            structured = self._llm_structured(query_generation, query_generation_prompt, state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=str(structured["subclaim_with_questions"]), name="query_generator")
                    ]
                },
                goto="supervisor",
            )

        def evidence_seeking_node(state: State) -> Command[Literal["supervisor"]]:
            # Run the ReAct tool-use loop first
            agent_result = self.evidence_seeking_agent.invoke(state)
            # Extract the final AI text from the agent run
            final_ai_text = ""
            for msg in reversed(agent_result["messages"]):
                if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                    final_ai_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                    break
            if not final_ai_text:
                final_ai_text = str(agent_result["messages"][-1].content)
            # Structured output from a fresh HumanMessage (no prefilling)
            structured = self.llm.with_structured_output(evidence_seeking).invoke([
                SystemMessage(content=evidence_seeking_prompt),
                HumanMessage(content=f"Summarize and format the evidence collected:\n{final_ai_text}")
            ])
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=str(structured["subclaims_with_query_evidence"]), name="evidence_seeker")
                    ]
                },
                goto="supervisor",
            )

        def verdict_prediction_node(state: State) -> Command[Literal["supervisor"]]:
            structured = self._llm_structured(verdict_prediction, verdict_prediction_prompt, state)
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=str(structured["result"]), name="verdict_predictor")
                    ]
                },
                goto="supervisor",
            )

        orchestrator = self._make_supervisor_node(
            ["input_ingestor", "query_generator", "evidence_seeker", "verdict_predictor"]
        )

        super_builder = StateGraph(State)
        super_builder.add_node("supervisor", orchestrator)
        super_builder.add_node("input_ingestor", call_input_ingestion_team)
        super_builder.add_node("query_generator", query_generation_node)
        super_builder.add_node("evidence_seeker", evidence_seeking_node)
        super_builder.add_node("verdict_predictor", verdict_prediction_node)
        super_builder.add_edge(START, "supervisor")

        self.super_graph = super_builder.compile()

    def process_claim(self, claim: str, recursion_limit: int = 150, verbose: bool = False):
        """
        Process a single claim through the fact-checking pipeline.

        Args:
            claim: The claim to fact-check
            recursion_limit: Maximum number of recursions allowed (default: 150)
            verbose: Whether to print intermediate steps (default: False)

        Returns:
            list: Steps produced by the pipeline
        """
        messages = [("user", claim)]

        results = []
        for step in self.super_graph.stream(
            {"messages": messages},
            {"recursion_limit": recursion_limit}
        ):
            if verbose:
                print(step)
                print("---")
            results.append(step)

        return results

    def process_multiple_claims(self, claims: list[str], recursion_limit: int = 150, verbose: bool = False):
        """
        Process multiple claims through the fact-checking pipeline.

        Args:
            claims: List of claims to fact-check
            recursion_limit: Maximum number of recursions allowed (default: 150)
            verbose: Whether to print intermediate steps (default: False)

        Returns:
            list: Results for each claim
        """
        results = []
        for i, claim in enumerate(claims):
            if verbose:
                print(f"\n=== Processing Claim {i+1}/{len(claims)} ===")
                print(f"Claim: {claim}")
                print("=" * 50)

            steps = self.process_claim(claim, recursion_limit, verbose)
            # Extract final verdict from the last verdict_predictor message
            label, explanation = "unknown", ""
            for step in reversed(steps):
                if "verdict_predictor" in str(step):
                    content = str(step)
                    label = "supported" if "supported" in content else "not_supported"
                    explanation = content
                    break
            results.append({
                "claim": claim,
                "label": label,
                "explanation": explanation
            })

        return results
