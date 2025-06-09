"""
Custom AgentExecutor for handling agent interactions, specifically tailored
for streaming responses and managing task states within the A2A framework.
"""
import json
from a2a.server.agent_execution import AgentExecutor as BaseAgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_parts_message,
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError

class CustomStreamingAgentExecutor(BaseAgentExecutor):
    """
    Custom AgentExecutor that processes streamed items from an agent,
    updates task status, and handles different content types in the stream.
    """

    def __init__(self, agent_creator):
        self.agent_instance = agent_creator()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        query = context.get_user_input()
        task = context.current_task

        if not task:
            task = new_task(context.message)
            event_queue.enqueue_event(task)

        if not task or not task.id or not task.contextId:
            failed_task_updater_temp = TaskUpdater(event_queue, "temp-failed-task-id", context.message.contextId if context.message else "unknown_context")
            failed_task_updater_temp.update_status(
                TaskState.failed,
                new_agent_text_message(
                    'Failed to initialize or retrieve task.',
                    context.message.contextId if context.message else "unknown_context",
                    "temp-failed-task-id"
                ),
                final=True
            )
            return

        updater = TaskUpdater(event_queue, task.id, task.contextId)

        async for item in self.agent_instance.stream(query, task.contextId):
            is_task_complete = item.get('is_task_complete', False)
            content = item.get('content')

            if not is_task_complete:
                updates_text = item.get('updates', 'Processing...')
                updater.update_status(
                    TaskState.working,
                    new_agent_text_message(
                        updates_text, task.contextId, task.id
                    ),
                )
                continue

            if isinstance(content, dict):
                if (
                    'response' in content
                    and isinstance(content['response'], dict)
                    and 'result' in content['response']
                ):
                    try:
                        data_str = content['response']['result']
                        if not isinstance(data_str, str):
                            raise TypeError("Expected 'result' to be a JSON string.")
                        data = json.loads(data_str)
                        updater.update_status(
                            TaskState.input_required,
                            new_agent_parts_message(
                                [Part(root=DataPart(data=data))],
                                task.contextId,
                                task.id,
                            ),
                            final=True,
                        )
                    except (json.JSONDecodeError, TypeError) as e:
                        updater.update_status(
                            TaskState.failed,
                            new_agent_text_message(
                                f'Error processing structured content: {str(e)}',
                                task.contextId,
                                task.id,
                            ),
                            final=True,
                        )
                    break
                else:
                    updater.update_status(
                        TaskState.completed,
                        new_agent_parts_message(
                            [Part(root=DataPart(data=content))],
                            task.contextId,
                            task.id,
                        ),
                        final=True
                    )
                    break
            elif isinstance(content, str):
                updater.add_artifact(
                    [Part(root=TextPart(text=content))], name='final_response'
                )
                updater.complete()
                break
            else:
                updater.update_status(
                    TaskState.failed,
                    new_agent_text_message(
                        f'Received unexpected content type: {type(content).__name__}',
                        task.contextId,
                        task.id,
                    ),
                    final=True,
                )
                break

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        raise ServerError(error=UnsupportedOperationError())

# Ensure a final newline here