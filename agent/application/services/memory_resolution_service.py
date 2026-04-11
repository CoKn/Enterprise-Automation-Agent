from agent.application.ports.outbound.procedural_memory_interface import ProceduralMemoryPort
from agent.application.ports.outbound.episodic_memory_interface import EpisodicMemoryPort
from agent.application.ports.outbound.semantic_memory_interface import SemanticMemoryPort


class MemoryResolutionService:
    def __init__(
        self,
        procedural: ProceduralMemoryPort,
        semantic: SemanticMemoryPort,
        episodic: EpisodicMemoryPort,
    ):
        ...