import uuid
from typing import Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import TokenUsage


class TokenRepository:
    """Repository managing Database operations for the TokenUsage model."""

    async def create(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float
    ) -> TokenUsage:
        """Log a new TokenUsage transaction."""
        db_usage = TokenUsage(
            conversation_id=conversation_id,
            message_id=message_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            estimated_cost=estimated_cost
        )
        db.add(db_usage)
        await db.flush()
        return db_usage

    async def get_usage_by_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Aggregate token usage and cost metrics for a single conversation session."""
        stmt = (
            select(
                func.sum(TokenUsage.input_tokens).label("input_tokens"),
                func.sum(TokenUsage.output_tokens).label("output_tokens"),
                func.sum(TokenUsage.total_tokens).label("total_tokens"),
                func.sum(TokenUsage.estimated_cost).label("estimated_cost")
            )
            .where(TokenUsage.conversation_id == conversation_id)
        )
        result = await db.execute(stmt)
        row = result.first()
        
        if not row or row.total_tokens is None:
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost": 0.0
            }
            
        return {
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            "total_tokens": int(row.total_tokens),
            "estimated_cost": float(row.estimated_cost)
        }
