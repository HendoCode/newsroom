"""Oracle service — retrieve → rank → persist (context report §4; engine/1-oracle.md; §1.8).

The actual work behind one Oracle run: query the content lake (bounded top-K, windowed), run the
Opus convergence rank, and persist the ranked spikes to the pool/Vault, attributed to their
creator and this run's origin. Framework-free — no Job lifecycle, no retry policy (that is
``app.orchestration.jobs.JobRunner``'s concern via ``app.oracle.step.OracleStep``); this class does
the one stage's actual work, the same shape ``app.connectors.refresh.SourceRefreshService`` and
``ClipInService`` use for their on-demand entrypoints, so it is directly unit-testable without a
job or an HTTP call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.git.brain import GitBrain
from app.lake.query import LakeQuery
from app.lake.store import ContentLake
from app.llm.budget import RunBudget
from app.llm.pricing import Usage
from app.llm.provider import LLMProvider
from app.llm.tiering import PipelineStep, model_for_step
from app.models.job import Job, OracleEntryMode, OracleRunParams
from app.models.narrative import Narrative
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind, SpikeStatus
from app.oracle.ranking import RankedSpikeCandidate, build_user_prompt, parse_ranked_spikes
from app.orchestration.retry import PermanentStepError
from app.repositories import WorkStateStore

logger = logging.getLogger(__name__)

# Entry A (open scan) ranks broadly; Entry B's retrieval is already angle-narrowed by the biased
# query text, so a tighter cap is enough raw material (context report §4e).
DEFAULT_TOP_K_OPEN_SCAN = 40
DEFAULT_TOP_K_NARRATIVE = 20

_MAX_TOKENS = 4096


@dataclass
class OracleRunOutcome:
    """What one Oracle run produced — what :class:`~app.oracle.step.OracleStep` reports back."""

    spikes: list[Spike] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    notes: list[str] = field(default_factory=list)
    candidates_considered: int = 0
    top_k: int = 0


class OracleService:
    """Retrieve → rank → persist. Construct once per run (holds no per-run state)."""

    def __init__(
        self,
        *,
        store: WorkStateStore,
        lake: ContentLake,
        provider: LLMProvider,
        brain: GitBrain,
    ) -> None:
        self.store = store
        self.lake = lake
        self.provider = provider
        self.brain = brain

    async def run(
        self, *, job: Job, params: OracleRunParams, budget: RunBudget
    ) -> OracleRunOutcome:
        narrative = await self._resolve_narrative(params)
        top_k = params.top_k or (
            DEFAULT_TOP_K_NARRATIVE if narrative is not None else DEFAULT_TOP_K_OPEN_SCAN
        )
        query = self._build_query(params, narrative, top_k)
        candidates = await self.lake.query(query)

        # No silent "scanned everything": the cap is always logged, whether or not it actually
        # bound the result set (context report §4f, mirroring D6's no-silent-caps discipline).
        logger.info(
            "oracle run %s: entry=%s lookback=%dd top_k=%d candidates=%d",
            job.id,
            params.entry_mode.value,
            params.lookback_days,
            top_k,
            len(candidates),
        )
        cap_note = (
            f"oracle: rank-and-retrieve capped at top_k={top_k} "
            f"({len(candidates)} candidate(s) considered, lookback={params.lookback_days}d); "
            "the lake was not scanned exhaustively"
        )

        if not candidates:
            return OracleRunOutcome(
                notes=[cap_note, "oracle: no candidates in the lookback window"],
                candidates_considered=0,
                top_k=top_k,
            )

        system = self._build_system(params.voice)
        user_prompt = build_user_prompt(candidates, params, narrative, top_k=top_k)

        result = await self.provider.complete(
            step=PipelineStep.ORACLE,
            model=model_for_step(PipelineStep.ORACLE),
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=_MAX_TOKENS,
            budget=budget,
        )

        # Ordered to match `format_candidate`'s enumeration in `build_user_prompt` above, so an
        # integer reference in the model's response resolves to the right positional candidate.
        candidate_ids = [c.item.id for c in candidates]
        ranked = parse_ranked_spikes(result.text, candidate_ids=candidate_ids)
        spikes = await self._persist(ranked, job=job, narrative=narrative)

        notes = [cap_note, f"oracle: proposed {len(spikes)} ranked spike(s)"]
        return OracleRunOutcome(
            spikes=spikes,
            usage=result.usage,
            notes=notes,
            candidates_considered=len(candidates),
            top_k=top_k,
        )

    # --- internals --------------------------------------------------------------------------

    async def _resolve_narrative(self, params: OracleRunParams) -> Narrative | None:
        if params.entry_mode != OracleEntryMode.narrative:
            return None
        assert params.narrative_id is not None  # enforced by OracleRunParams's own validator
        narrative = await self.store.narratives.get(params.narrative_id)
        if narrative is None:
            raise PermanentStepError(f"Entry B: no narrative {params.narrative_id!r}")
        return narrative

    def _build_query(
        self, params: OracleRunParams, narrative: Narrative | None, top_k: int
    ) -> LakeQuery:
        text = None
        if narrative is not None:
            # Bias the embedding query itself toward the narrative's angle (context report §4d
            # enrichment #2) — stronger than a prompt-only "prefer this angle" instruction.
            parts = [narrative.seed_text]
            if narrative.intent.audience:
                parts.append(f"audience: {narrative.intent.audience}")
            if narrative.intent.angle:
                parts.append(f"angle: {narrative.intent.angle}")
            text = " — ".join(parts)
        return LakeQuery(text=text, lookback_days=params.lookback_days, top_k=top_k)

    def _build_system(self, voice: str) -> list[str]:
        blocks = [self.brain.read_engine("1-oracle")]
        style_guide = self.brain.read_voice(voice).style_guide
        if style_guide:
            blocks.append(style_guide)
        return blocks

    async def _persist(
        self,
        ranked: list[RankedSpikeCandidate],
        *,
        job: Job,
        narrative: Narrative | None,
    ) -> list[Spike]:
        creator = job.triggered_by or "unknown"
        if narrative is not None:
            assert narrative.id is not None
            origin = SpikeOrigin(kind=SpikeOriginKind.narrative, ref=narrative.id)
            intent = narrative.intent
        else:
            origin = SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref=job.id)
            intent = None

        spikes: list[Spike] = []
        for candidate in ranked:
            spike = Spike(
                headline=candidate.headline,
                status=SpikeStatus.proposed,
                convergence_score=candidate.convergence_score,
                creator=creator,
                origin=origin,
                source_ids=candidate.source_item_ids,
                customer_partner=candidate.customer_partner,
                outcome_metric=candidate.outcome_metric,
                rank_rationale=candidate.rank_rationale,
                convergence_note=candidate.convergence_note,
                intent=intent,
            )
            spikes.append(await self.store.spikes.insert(spike))

        if narrative is not None:
            assert narrative.id is not None
            await self.store.narratives.update(narrative.id, {"oracle_run_id": job.id})
        return spikes
