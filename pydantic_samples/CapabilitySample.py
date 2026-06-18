from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.capabilities import Thinking, WebSearch

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    instructions='Be concise, reply with one sentence.',
    capabilities=[Thinking(), WebSearch(local='duckduckgo')],
)

result = agent.run_sync('What was the mass of the largest meteorite found this year?')
print(result.output)
"""
The largest meteorite recovered this year weighed approximately 7.6 kg, found in the Sahara Desert in January.
"""