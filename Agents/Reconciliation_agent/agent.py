import os
import json
from typing import Any, Optional, AsyncIterable

from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as google_types
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset,SseServerParams
from dotenv import load_dotenv

load_dotenv()


class ReconciliationAgent:
    """Agent to reconcile purchase orders with invoices using Gemini model and MCPToolset."""

    def __init__(self, user_id: str = "reconciliation_service_user"):
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


    def _build_agent(self) -> LlmAgent:
        """Creates and returns the LLM Agent instance."""
        return LlmAgent(
            name="reconciliation_specialist_agent",
            model=os.getenv("ADK_MODEL", "gemini-1.5-flash-latest"),
            description=(
                "Specialized agent for fetching purchase order data "
                "and its related invoice data from a database "
                "using the purchase order number, comparing them, and"
                " determining a reconciliation status."
            ),
            instruction=(
                "You are a Reconciliation Specialist. "
                "Your ONLY task is to reconcile an invoice and a purchase order "
                "using the provided Purchase Order (PO) number.\n"
                "1. Extract the `po_number` from the user message.\n"
                "2. Use the `_fetch_and_reconcile_documents_tool` with this `po_number`.\n"
                "3. Return the tool's JSON output directly.\n"
                "If the `po_number` is missing, return: {\"status\": \"error\", "\
                    "\"error_message\": \"PO number was not clearly provided or is missing.\"}."
            ),
            tools=[
                MCPToolset(connection_params=SseServerParams(url="http://127.0.0.1:8000/sse"))
            ]
        )

    def get_processing_message(self) -> str:
        """Returns a generic processing message."""
        return "Reconciliation Agent is fetching and comparing the documents..."

    async def reconcile_documents(self ,po_number: str,
                                   session_id: Optional[str] = None
                                   ) -> AsyncIterable[dict[str, Any]]:
        """
        reconcile a document by providing its path and type to the agent.
        Yields events from the agent interaction, 
        with the final event containing the result.
        """
        user_message_text = (
            f"Please reconcile the documents.\n"
            f"Purchase Order Number: \"{po_number}\""
        )

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
                    session_id=current_session_id
                )
        if not session:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id
            )
        current_session_id = session.id

        content = google_types.Content(
            role='user', parts=[google_types.Part.from_text(text=user_message_text)]
        )

        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=current_session_id, new_message=content
        ):
            if event.is_final_response():
                final_response_data = None
                if event.content and event.content.parts:
                    final_text_response = event.content.parts[0].text if event.content.parts[0].text else ""
                    if final_text_response:
                        try:
                            final_response_data = json.loads(final_text_response)
                        except json.JSONDecodeError:
                            final_response_data = {"status": "error",
                                                   "error_message":"LLM did not return valid JSON."
                                                    ,"raw_response": final_text_response}
                else:
                    final_response_data = {"status": "error",
                                           "error_message":"LLM final response had no structure."
                                           }

                yield {
                    'is_task_complete': True,
                    'content': final_response_data,
                    'session_id': current_session_id
                }
                return
            else:
                update_text = ""
                if event.content and event.content.parts:
                    update_text = '\n'.join(
                        [p.text for p in event.content.parts if p.text]
                    ).strip()
                yield {
                    'is_task_complete': False,
                    'updates': update_text if update_text else self.get_processing_message(),
                    'session_id': current_session_id
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
        content = google_types.Content(
            role='user', parts=[google_types.Part.from_text(text=query)]
        )
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )
        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session.id, new_message=content
        ):
            if event.is_final_response():
                response: Any = ''
                if (
                    event.content
                    and event.content.parts
                    and event.content.parts[0].text
                ):
                    response = '\n'.join(
                        [p.text for p in event.content.parts if p.text]
                    )
                elif (
                    event.content
                    and event.content.parts
                    and any(
                        p.function_response for p in event.content.parts
                    )
                ):
                    response = next(
                        p.function_response.model_dump()
                        for p in event.content.parts if p.function_response
                    )
                yield {
                    'is_task_complete': True,
                    'content': response,
                }
            else:
                yield {
                    'is_task_complete': False,
                    'updates': self.get_processing_message(),
                }
    def get_agent(self):
        """Returns the underlying LLM agent instance."""
        return self._build_agent()

root_agent=ReconciliationAgent().get_agent()
