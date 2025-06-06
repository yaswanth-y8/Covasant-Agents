import httpx
from uuid import uuid4
from typing import Callable, Union

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    Task,
    Message,
    MessageSendParams,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    SendMessageRequest,
    SendStreamingMessageRequest,
    JSONRPCErrorResponse,
)

class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, client: httpx.AsyncClient, agent_card: AgentCard):
        self.agent_client = A2AClient(client, agent_card)
        self.card = agent_card

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(
        self,
        request: MessageSendParams,
    ) -> Task | Message | JSONRPCErrorResponse | None:
        """
        Sends a message to the remote agent, handling both streaming and non-streaming.

        For streaming, it assembles the final Task object from the event stream.
        """
        if self.card.capabilities.streaming:
            # --- THIS IS THE CORRECTED LOGIC ---
            final_task_state: Task | None = None
            final_message_response: Message | None = None

            async for response in self.agent_client.send_message_streaming(
                SendStreamingMessageRequest(id=str(uuid4()), params=request)
            ):
                if hasattr(response.root, 'error') and response.root.error:
                    return response.root.error

                event = response.root.result
                if not event:
                    continue

                # In case a simple message is returned, that is the end of the interaction.
                if isinstance(event, Message):
                    final_message_response = event
                    break 

                # Otherwise, we are in the Task + TaskUpdate event cycle.
                # We build the final task state internally.
                if isinstance(event, Task):
                    final_task_state = event
                elif isinstance(event, TaskStatusUpdateEvent) and final_task_state:
                    final_task_state.status = event.status
                elif isinstance(event, TaskArtifactUpdateEvent) and final_task_state:
                    if final_task_state.artifacts is None:
                        final_task_state.artifacts = []
                    final_task_state.artifacts.append(event.artifact)

                

                # Check if the event is marked as final to stop the loop.
                if (
                    hasattr(event, 'status') and hasattr(event.status, 'final') and event.status.final
                ):
                    break

            # Return whatever final object we ended up with.
            if final_message_response:
                return final_message_response
            
            return final_task_state # This will be the fully assembled Task object or None if the stream was empty/faulty.
            # --- END OF CORRECTED LOGIC ---

        else:  # Non-streaming (this part was likely correct already)
            response = await self.agent_client.send_message(
                SendMessageRequest(id=str(uuid4()), params=request)
            )
            if isinstance(response.root, JSONRPCErrorResponse):
                return response.root.error

            result = response.root.result
            
            return result