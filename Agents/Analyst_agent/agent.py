"""
Analyst Agent for querying financial document database.

This agent assists users in retrieving information about invoices and
purchase orders using a set of predefined tools that query a database.
It aims to clarify user requests and present information clearly.
"""

from typing import Any, Optional, AsyncIterable
import os
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as google_types
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseServerParams
from dotenv import load_dotenv

load_dotenv()


class AnalystAgent:
    """
    An agent specializing in analyzing and reporting on data from a
    financial document database (invoices, purchase orders) using MCP tools.
    """
    DB_QUERY_AGENT_NAME = "database_analyst_agent"
    DB_QUERY_AGENT_DESCRIPTION = (
        "Agent to query invoice and purchase order database, providing insights and "
        "summaries to users."
    )

    def __init__(self, user_id: str = "analyst_service_user"):
        """
        Initializes the DataIngestionAgentWrapper.

        Args:
            user_id: An identifier for the user interacting with the agent.
        """
        self._agent = self._build_agent()
        self._user_id = user_id
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )
        if not os.getenv("GOOGLE_API_KEY"):
            print(
                "AnalystAgent Warning: GOOGLE_API_KEY is not set. "
                "Agent calls will likely fail."
            )

    def _build_agent(self) -> LlmAgent:
        """Builds the LLM agent for data ingestion."""
        return LlmAgent(
            name=self.DB_QUERY_AGENT_NAME,
            model=os.getenv("ADK_MODEL", "gemini-1.5-flash-latest"),
            description=self.DB_QUERY_AGENT_DESCRIPTION,
            instruction=(
                "You are a helpful Database Analyst Assistant. Your primary role is to assist "
                "users in retrieving information about invoices and purchase orders from a "
                "financial database. You have access to several tools to query this database.\n\n"
                "**Interaction Flow:**\n"
                "1. Clarify user requests. Ask for date format 'YYYY-MM-DD' if vague.\n"
                "2. Choose one appropriate tool based on clarified request.\n"
                "3. Extract parameters clearly.\n"
                "4. Execute the tool.\n"
                "5. Present results clearly. If successful, summarize. If error, show message.\n"
                "6. Ask if further help is needed.\n\n"
                "**Tools Available:**\n"
                "- _get_doc_count_date_range_tool\n"
                "- _get_doc_count_vendor_tool\n"
                "- _get_total_amount_vendor_tool\n"
                "- _list_documents_vendor_tool\n"
                "- _list_documents_date_range_tool\n\n"
                "Be polite, avoid own calculations, and guide users well."
            ),
            tools=[
                MCPToolset(
                    connection_params=SseServerParams(url="http://127.0.0.1:8000/sse")
                )
            ],
        )

    def get_processing_message(self) -> str:
        """Returns a generic processing message."""
        return "Analyst Agent is querying the database..."

    async def query(
        self, user_query: str, session_id: Optional[str] = None
    ) -> AsyncIterable[dict[str, Any]]:
        """
        Processes a document by providing its path and type to the agent.
        Yields events from the agent interaction, with the final event containing the result.

        Args:
            raw_document_file_path: The absolute or relative path to the document file.
            document_type: The type of the document (e.g., "invoice", "purchase_order").
            session_id: Optional existing session ID to continue a session.

        Yields:
            Dictionaries representing events from the agent interaction.
            The final event includes `is_task_complete: True` and `content` 
            (the parsed JSON result from the tool).
        """
        if not user_query or not user_query.strip():
            yield {
                "is_task_complete": True,
                "content": (
                    "I need a query to process. Please tell me what information you're "
                    "looking for."
                ),
                "session_id": session_id,
            }
            return

        current_session_id = session_id
        session = None

        if current_session_id:
            session = await self._runner.session_service.get_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=current_session_id,
            )

        if not session:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                session_id=current_session_id if current_session_id else None,
            )

        current_session_id = session.id

        content = google_types.Content(
            role="user", parts=[google_types.Part.from_text(text=user_query)]
        )

        if not os.getenv("GOOGLE_API_KEY"):
            yield {
                "is_task_complete": True,
                "content": (
                    "I'm unable to process your request right now due to a configuration "
                    "issue (missing API key). Please try again later."
                ),
                "session_id": current_session_id,
            }
            return

        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=current_session_id,
            new_message=content,
        ):
            response_content = ""
            is_tool_call_related = False

            if event.content and event.content.parts:
                if any(p.function_call for p in event.content.parts):
                    is_tool_call_related = True
                    response_content = self.get_processing_message()
                elif any(p.function_response for p in event.content.parts):
                    is_tool_call_related = True
                    text_parts = [p.text for p in event.content.parts if p.text]
                    response_content = "\n".join(text_parts).strip() if text_parts else (
                        "Processing tool results..."
                    )
                else:
                    response_content = "\n".join(
                        [p.text for p in event.content.parts if p.text]
                    ).strip()

            if event.is_final_response():
                yield {
                    "is_task_complete": True,
                    "content": response_content or "No further information from the agent.",
                    "session_id": current_session_id,
                }
                return

            yield {
                "is_task_complete": False,
                "updates": (
                    response_content
                    or (
                        self.get_processing_message()
                        if is_tool_call_related
                        else "Analyst Agent is thinking..."
                    )
                ),
                "session_id": current_session_id,
            }

    async def stream(self, query: str, session_id: str) -> AsyncIterable[dict[str, Any]]:
        """
        Provides a generic streaming interface to the agent.
        The user_query should contain enough context for the agent to act.
        """
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )

        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )

        content = google_types.Content(
            role="user", parts=[google_types.Part.from_text(text=query)]
        )

        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content,
        ):
            if event.is_final_response():
                response: Any = ""
                if event.content and event.content.parts and event.content.parts[0].text:
                    response = "\n".join(
                        [p.text for p in event.content.parts if p.text]
                    )
                elif event.content and any(p.function_response for p in event.content.parts):
                    response = next(
                        p.function_response.model_dump()
                        for p in event.content.parts
                        if p.function_response
                    )
                yield {"is_task_complete": True, "content": response}
            else:
                yield {
                    "is_task_complete": False,
                    "updates": self.get_processing_message(),
                }
    def get_agent(self):
        "getter for the _build_agent"
        return self._build_agent()


root_agent = AnalystAgent().get_agent()
