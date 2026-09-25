"""Route/BFF tracer test for the thin submit/inspect adapters.

The domain unit tests in ``test_content_workflow.py`` construct ``CommandEnvelope`` with native
Python ``CommandKind.commit_idea`` members — they never serialize to JSON, so they cannot catch
frontend/backend string-contract drift. This module posts real JSON bodies over HTTP.

Ground truth for wire strings is ``CommandKind`` / ``HumanObligationKind`` in
``app/content_workflow/models.py`` (kebab-case *values*, not the snake_case member *names*).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.content_workflow import ContentWorkflow
from app.content_workflow.models import (
    AuthorityKind,
    CommandKind,
    HumanObligationKind,
)
from app.content_workflow.store import InMemoryWorkflowState
from app.main import app
from app.models.common import new_id
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind


# A structurally-valid commit-idea CommandEnvelope. FastAPI validates the request body against
# `CommandEnvelope` (a Pydantic model, resolved as a dependency) *before* the route handler body
# ever runs — an empty `{}` body always 422s on that validation regardless of whether
# `app.state.content_workflow` is configured, since body parsing happens earlier in FastAPI's
# request pipeline than any code inside the handler. The route's "thin adapter, no state -> 503"
# behavior can only be observed with a body that actually clears validation.
_VALID_COMMIT_IDEA_BODY = {
    "command_type": "commit-idea",
    "aggregate": {"kind": "idea", "id": "idea-1"},
    "actor": {"subject_id": "captain@example.com", "email": "captain@example.com"},
    "idempotency_key": "k1",
    "expected_version": 0,
    "payload": {
        "type": "commit-idea",
        "project_title": "Test project",
        "purpose_brief": {
            "proposition": "p",
            "audience": "a",
            "angle": "ang",
            "desired_outcome": "d",
            "why_now": "w",
        },
        "default_voice_id": "demo-dana",
        "authorities": [
            {"kind": kind, "assignee": {"subject_id": "captain@example.com", "email": "captain@example.com"}}
            for kind in ("direction", "input-sufficiency", "voice", "release")
        ],
        "anchor_title": "Anchor",
        "anchor_slug": "anchor-slug",
        "anchor_destination": "blog",
    },
}


# Verbatim JSON body ``OperatorDesk.handleCommitIdea`` constructs and POSTs to
# ``/api/content-workflow/submit`` (web/app/content-machine/operator-desk.tsx).
def _operator_desk_submit_body(email: str = "test@example.com", idea_id: str = "idea-1") -> dict:
    actor = {"subject_id": email, "email": email, "display_name": email}
    return {
        "schema_version": 1,
        "command_type": "commit-idea",
        "aggregate": {"kind": "idea", "id": idea_id},
        "actor": actor,
        "idempotency_key": "idea-1",
        "expected_version": 0,
        "payload": {
            "type": "commit-idea",
            "project_title": "Evidence that compounds",
            "purpose_brief": {
                "proposition": "Operational evidence should compound across a content family.",
                "audience": "General",
                "angle": "Default",
                "desired_outcome": "Audience adopts core proposition",
                "why_now": "Relevant operational need",
                "constraints": [],
            },
            "default_voice_id": "demo-dana",
            "authorities": [
                {"kind": "direction", "assignee": actor, "scope": "project"},
                {"kind": "input-sufficiency", "assignee": actor, "scope": "project"},
                {"kind": "voice", "assignee": actor, "scope": "project"},
                {"kind": "release", "assignee": actor, "scope": "project"},
            ],
            "anchor_title": "Evidence that compounds",
            "anchor_slug": "evidence-that-compounds",
            "anchor_destination": "blog",
        },
    }


def _valid_commit_idea_wire(idea_id: str, *, key: str = "commit-1") -> dict:
    """A CommandEnvelope as JSON, using enum *values* (the HTTP wire format)."""
    actor = {"subject_id": "captain@example.com", "email": "captain@example.com"}
    return {
        "schema_version": 1,
        "command_type": CommandKind.commit_idea.value,  # "commit-idea", never "commit_idea"
        "aggregate": {"kind": "idea", "id": idea_id},
        "actor": actor,
        "idempotency_key": key,
        "expected_version": 0,
        "payload": {
            "type": CommandKind.commit_idea.value,
            "project_title": "Evidence that compounds",
            "purpose_brief": {
                "proposition": "Operational evidence should compound across a content family.",
                "audience": "Enterprise AI leaders",
                "angle": "Treat evidence as shared infrastructure, not draft decoration.",
                "desired_outcome": "Readers adopt an evidence-first production loop.",
                "why_now": "AI content volume is rising faster than trust.",
                "constraints": [],
            },
            "default_voice_id": "demo-dana",
            "authorities": [
                {"kind": kind, "assignee": actor, "scope": "project"}
                for kind in (
                    AuthorityKind.direction.value,
                    AuthorityKind.input_sufficiency.value,
                    AuthorityKind.voice.value,
                    AuthorityKind.release.value,
                )
            ],
            "anchor_title": "Evidence that compounds",
            "anchor_slug": "evidence-that-compounds",
            "anchor_destination": "blog",
        },
    }


def _seeded_workflow() -> tuple[InMemoryWorkflowState, str]:
    idea_id = new_id()
    idea = Spike(
        id=idea_id,
        headline="Evidence that compounds",
        creator="captain@example.com",
        origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
    )
    return InMemoryWorkflowState([idea]), idea_id


def test_content_workflow_routes_mounted_and_thin() -> None:
    client = TestClient(app)
    # submit without configured workflow -> 503 (thin adapter, no state) — needs a body that
    # actually passes `CommandEnvelope` validation, or FastAPI 422s before the handler runs at
    # all, which would test request validation instead of the intended "no state" behavior.
    resp = client.post("/api/content-workflow/submit", json=_VALID_COMMIT_IDEA_BODY)
    assert resp.status_code == 503
    assert "content workflow unavailable" in resp.text

    # inspect likewise
    resp = client.get("/api/content-workflow/some-id/inspect")
    assert resp.status_code == 503


def test_content_workflow_submit_422s_on_malformed_body() -> None:
    """A genuinely malformed body (e.g. empty `{}`) 422s regardless of workflow-configured
    state — real, correct FastAPI request-validation behavior, not the 503 path above."""
    client = TestClient(app)
    resp = client.post("/api/content-workflow/submit", json={})
    assert resp.status_code == 422


def test_command_kind_wire_values_are_kebab_case_not_member_names() -> None:
    """Canary: the JSON wire is the enum *value*. Member names are an implementation detail.

    ``test_content_workflow.py`` passes ``CommandKind.commit_idea`` objects in-process and so
    never notices if a client sends the name instead of the value.
    """
    assert CommandKind.commit_idea.name == "commit_idea"
    assert CommandKind.commit_idea.value == "commit-idea"
    assert CommandKind.declare_input_sufficient.value == "declare-input-sufficient"
    assert CommandKind.record_experiential_waiver.value == "record-experiential-waiver"
    assert CommandKind.commission_derivative.value == "commission-derivative"
    assert CommandKind.accept_final_revision.value == "accept-final-revision"
    assert CommandKind.authorize_release.value == "authorize-release"
    assert HumanObligationKind.confirm_input_sufficiency.value == "confirm-input-sufficiency"
    assert HumanObligationKind.close_review.value == "close-review"
    assert HumanObligationKind.accept_final_revision.value == "accept-final-revision"
    assert HumanObligationKind.authorize_release.value == "authorize-release"
    assert HumanObligationKind.decide_lesson.value == "decide-lesson"
    assert HumanObligationKind.attention_required.value == "attention-required"


def test_submit_rejects_python_enum_name_even_on_an_otherwise_valid_envelope() -> None:
    """Regression: a valid envelope with the member name (commit_idea) still 422s."""
    state, idea_id = _seeded_workflow()
    body = _valid_commit_idea_wire(idea_id)
    body["command_type"] = CommandKind.commit_idea.name  # "commit_idea"
    body["payload"]["type"] = CommandKind.commit_idea.name
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        resp = client.post("/api/content-workflow/submit", json=body)
        assert resp.status_code == 422
        assert CommandKind.commit_idea.value in resp.text
    finally:
        app.state.content_workflow = None


def test_submit_operator_desk_payload_validates_and_applies() -> None:
    """OperatorDesk sends the full typed CommandEnvelope with CommitIdeaPayload, and
    it passes validation and applies cleanly against the workflow."""
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        resp = client.post(
            "/api/content-workflow/submit",
            json=_operator_desk_submit_body(email="captain@example.com", idea_id=idea_id),
        )
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["outcome"] == "applied"
        assert receipt["command_type"] == "commit-idea"
        assert receipt["result_refs"]["content_project_id"] is not None
    finally:
        app.state.content_workflow = None


def test_submit_shorthand_payload_coerces_and_succeeds() -> None:
    """Shorthand/legacy payload shape with title, narrative, owners, voice_id is coerced
    by backend model validators and succeeds."""
    state, idea_id = _seeded_workflow()
    shorthand_body = {
        "command_type": "commit-idea",
        "aggregate": {"kind": "idea", "id": idea_id},
        "actor": {"email": "captain@example.com"},
        "idempotency_key": "shorthand-1",
        "payload": {
            "title": "Evidence that compounds",
            "narrative": "Operational evidence should compound across a content family.",
            "audience": "General",
            "angle": "Default",
            "voice_id": "demo-dana",
            "owners": ["captain@example.com"],
        },
        "expected_version": 0,
    }
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        resp = client.post("/api/content-workflow/submit", json=shorthand_body)
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["outcome"] == "applied"
    finally:
        app.state.content_workflow = None


def test_submit_realistic_json_payload_round_trips_enum_values() -> None:
    """HTTP JSON using kebab-case wire values is accepted and echoed back as those values."""
    state, idea_id = _seeded_workflow()
    body = _valid_commit_idea_wire(idea_id)
    assert body["command_type"] == "commit-idea"
    assert body["payload"]["type"] == "commit-idea"
    assert "commit_idea" not in (body["command_type"], body["payload"]["type"])

    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        resp = client.post("/api/content-workflow/submit", json=body)
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["outcome"] == "applied"
        assert receipt["command_type"] == CommandKind.commit_idea.value == "commit-idea"

        project_id = receipt["result_refs"]["content_project_id"]
        inspect = client.get(f"/api/content-workflow/{project_id}/inspect")
        assert inspect.status_code == 200, inspect.text
        view = inspect.json()
        kinds = {item["kind"] for item in view["open_obligations"]}
        assert HumanObligationKind.confirm_input_sufficiency.value in kinds
        commands = {item["command_type"] for item in view["available_commands"]}
        assert CommandKind.declare_input_sufficient.value in commands
        assert CommandKind.record_experiential_waiver.value in commands
        assert "declare_sufficiency" not in commands
        assert "commit_idea" not in commands
    finally:
        app.state.content_workflow = None


# --- research report + experiential waiver over real HTTP JSON (research-v1) -----------------


def _waiver_wire_body(project_id: str, version: int, *, key: str = "waiver-1") -> dict:
    """The wire shape the project studio builds for record-experiential-waiver."""
    actor = {"subject_id": "captain@example.com", "email": "captain@example.com"}
    return {
        "schema_version": 1,
        "command_type": CommandKind.record_experiential_waiver.value,
        "aggregate": {"kind": "content-project", "id": project_id},
        "actor": actor,
        "idempotency_key": key,
        "expected_version": version,
        "payload": {
            "type": CommandKind.record_experiential_waiver.value,
            "content_project_id": project_id,
            "reason": "I ran this exact migration for three customers last year.",
        },
    }


def _commit_and_get_project(client: TestClient, idea_id: str) -> tuple[str, int]:
    resp = client.post("/api/content-workflow/submit", json=_valid_commit_idea_wire(idea_id))
    assert resp.status_code == 200, resp.text
    receipt = resp.json()
    assert receipt["outcome"] == "applied"
    return str(receipt["result_refs"]["content_project_id"]), receipt["version_after"]


def test_waiver_command_round_trips_and_satisfies_the_research_gate() -> None:
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        project_id, version = _commit_and_get_project(client, idea_id)

        resp = client.post(
            "/api/content-workflow/submit", json=_waiver_wire_body(project_id, version)
        )
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["outcome"] == "applied"
        assert receipt["command_type"] == "record-experiential-waiver"
        assert receipt["result_refs"]["waiver_id"]

        gate = client.get(f"/api/content-workflow/{project_id}/research-report")
        assert gate.status_code == 200, gate.text
        body = gate.json()
        assert body["required"] is True
        assert body["satisfied"] is True
        assert body["satisfied_by"] == "experiential-waiver"
        assert body["waiver"]["actor"]["email"] == "captain@example.com"
        assert body["waiver"]["reason"].startswith("I ran this exact migration")

        inspect = client.get(f"/api/content-workflow/{project_id}/inspect").json()
        declare = next(
            item
            for item in inspect["available_commands"]
            if item["command_type"] == CommandKind.declare_input_sufficient.value
        )
        assert declare["enabled"] is True
    finally:
        app.state.content_workflow = None


def test_waiver_without_reason_422s() -> None:
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        project_id, version = _commit_and_get_project(client, idea_id)
        body = _waiver_wire_body(project_id, version)
        body["payload"]["reason"] = ""
        resp = client.post("/api/content-workflow/submit", json=body)
        assert resp.status_code == 422
    finally:
        app.state.content_workflow = None


def test_research_report_routes_require_configured_workflow() -> None:
    client = TestClient(app)
    resp = client.get("/api/content-workflow/some-id/research-report")
    assert resp.status_code == 503
    resp = client.post(
        "/api/content-workflow/some-id/research-report",
        json={
            "subject": "s",
            "facts": [{"statement": "f", "source": "src"}],
            "submitted_by": {"email": "captain@example.com"},
        },
    )
    assert resp.status_code == 503


def test_research_report_submit_and_gate_round_trip() -> None:
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        project_id, _ = _commit_and_get_project(client, idea_id)

        resp = client.post(
            f"/api/content-workflow/{project_id}/research-report",
            json={
                "subject": "Token vs storage economics",
                "facts": [
                    {
                        "statement": "Inference grew 3x faster than training in 2025.",
                        "source": "Internal benchmark survey, Q4 2025",
                    }
                ],
                "opinions": [{"statement": "Favors storage-tiering pitches."}],
                "open_questions": ["Which segment feels the cost first?"],
                "submitted_by": {"subject_id": "captain@example.com", "email": "captain@example.com"},
            },
        )
        assert resp.status_code == 201, resp.text
        report = resp.json()
        assert report["content_project_id"] == project_id
        assert report["status"] == "current"
        assert report["facts"][0]["source"].startswith("Internal benchmark")

        gate = client.get(f"/api/content-workflow/{project_id}/research-report")
        assert gate.status_code == 200
        body = gate.json()
        assert body["satisfied"] is True
        assert body["satisfied_by"] == "research-report"
        assert body["report"]["subject"] == "Token vs storage economics"

        inspect = client.get(f"/api/content-workflow/{project_id}/inspect").json()
        assert inspect["research"]["satisfied_by"] == "research-report"
        assert inspect["artifact_readiness"]["research-report"] == "cleared"
    finally:
        app.state.content_workflow = None


def test_research_report_without_sourced_fact_422s() -> None:
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        project_id, _ = _commit_and_get_project(client, idea_id)
        resp = client.post(
            f"/api/content-workflow/{project_id}/research-report",
            json={
                "subject": "s",
                "facts": [],
                "submitted_by": {"email": "captain@example.com"},
            },
        )
        assert resp.status_code == 422
        assert "sourced fact" in resp.text
    finally:
        app.state.content_workflow = None


def test_research_report_unknown_project_404s() -> None:
    state, _ = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        assert (
            client.get("/api/content-workflow/missing/research-report").status_code == 404
        )
        assert (
            client.post(
                "/api/content-workflow/missing/research-report",
                json={
                    "subject": "s",
                    "facts": [{"statement": "f", "source": "src"}],
                    "submitted_by": {"email": "captain@example.com"},
                },
            ).status_code
            == 404
        )
    finally:
        app.state.content_workflow = None


def test_authorize_release_wire_round_trip_mints_a_numbered_release() -> None:
    """Real JSON POST of authorize-release (not a native enum) after accept-final-revision."""
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        commit = client.post(
            "/api/content-workflow/submit", json=_valid_commit_idea_wire(idea_id)
        )
        assert commit.status_code == 200, commit.text
        refs = commit.json()["result_refs"]
        project_id = refs["content_project_id"]
        piece_id = refs["anchor_piece_id"]
        version = commit.json()["version_after"]

        accept = client.post(
            "/api/content-workflow/submit",
            json={
                "command_type": "accept-final-revision",
                "aggregate": {"kind": "content-project", "id": project_id},
                "actor": {"subject_id": "captain@example.com", "email": "captain@example.com"},
                "idempotency_key": "accept-wire",
                "expected_version": version,
                "payload": {
                    "type": "accept-final-revision",
                    "content_project_id": project_id,
                    "piece_id": piece_id,
                    "revision": "rev-a",
                },
            },
        )
        assert accept.status_code == 200, accept.text
        assert accept.json()["outcome"] == "applied"
        version = accept.json()["version_after"]

        auth = client.post(
            "/api/content-workflow/submit",
            json={
                "command_type": "authorize-release",
                "aggregate": {"kind": "content-project", "id": project_id},
                "actor": {"subject_id": "captain@example.com", "email": "captain@example.com"},
                "idempotency_key": "auth-wire",
                "expected_version": version,
                "payload": {
                    "type": "authorize-release",
                    "content_project_id": project_id,
                    "piece_id": piece_id,
                },
            },
        )
        assert auth.status_code == 200, auth.text
        body = auth.json()
        assert body["outcome"] == "applied"
        assert body["result_refs"]["release_number"] == 1

        inspect = client.get(f"/api/content-workflow/{project_id}/inspect").json()
        assert inspect["derived_phase"] != "completed"
        assert inspect["release"]["releases"][0]["release_number"] == 1
        assert inspect["piece_family"][0]["derived_phase"] == "released"
    finally:
        app.state.content_workflow = None


# --- authority + quality waiver wire round trips (cmw-authority-model-impl) ------------------


def _declare_input_sufficient_wire_body(project_id: str, version: int) -> dict:
    actor = {"subject_id": "captain@example.com", "email": "captain@example.com"}
    return {
        "schema_version": 1,
        "command_type": "declare-input-sufficient",
        "aggregate": {"kind": "content-project", "id": project_id},
        "actor": actor,
        "idempotency_key": "declare-wire",
        "expected_version": version,
        "payload": {
            "type": "declare-input-sufficient",
            "content_project_id": project_id,
            "reason": "Research gate is satisfied.",
        },
    }


def _quality_waiver_wire_body(project_id: str, version: int) -> dict:
    actor = {"subject_id": "captain@example.com", "email": "captain@example.com"}
    return {
        "schema_version": 1,
        "command_type": "record-quality-waiver",
        "aggregate": {"kind": "content-project", "id": project_id},
        "actor": actor,
        "idempotency_key": "quality-wire",
        "expected_version": version,
        "payload": {
            "type": "record-quality-waiver",
            "content_project_id": project_id,
            "reason": "Tighter loop requested.",
            "quality_bar": 6.5,
            "iteration_ceiling": 2,
        },
    }


def test_declare_input_sufficient_wire_round_trip_resolves_obligation() -> None:
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        project_id, version = _commit_and_get_project(client, idea_id)
        # Satisfy the research gate first via waiver so declaring sufficiency is enabled.
        resp = client.post(
            "/api/content-workflow/submit", json=_waiver_wire_body(project_id, version)
        )
        assert resp.status_code == 200, resp.text
        version = resp.json()["version_after"]

        resp = client.post(
            "/api/content-workflow/submit",
            json=_declare_input_sufficient_wire_body(project_id, version),
        )
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["outcome"] == "applied"
        assert receipt["command_type"] == "declare-input-sufficient"
        assert receipt["result_refs"]["obligation_id"]

        inspect = client.get(f"/api/content-workflow/{project_id}/inspect").json()
        assert inspect["open_obligations"] == []
        assert inspect["derived_phase"] == "producing"
    finally:
        app.state.content_workflow = None


def test_record_quality_waiver_wire_round_trip_surfaces_in_inspect() -> None:
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        project_id, version = _commit_and_get_project(client, idea_id)

        resp = client.post(
            "/api/content-workflow/submit",
            json=_quality_waiver_wire_body(project_id, version),
        )
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["outcome"] == "applied"
        assert receipt["command_type"] == "record-quality-waiver"
        assert receipt["result_refs"]["waiver_id"]

        inspect = client.get(f"/api/content-workflow/{project_id}/inspect").json()
        assert inspect["quality_waiver"] is not None
        assert inspect["quality_waiver"]["quality_bar"] == 6.5
        assert inspect["quality_waiver"]["iteration_ceiling"] == 2
        commands = {item["command_type"]: item for item in inspect["available_commands"]}
        assert "record-quality-waiver" in commands
        assert commands["record-quality-waiver"]["authority_required"] == "direction"
    finally:
        app.state.content_workflow = None


def test_authority_required_rejects_wrong_actor_over_http() -> None:
    """A command whose projection declares authority_required is rejected when the actor does
    not hold that authority."""
    state, idea_id = _seeded_workflow()
    client = TestClient(app)
    app.state.content_workflow = ContentWorkflow(state)
    try:
        project_id, version = _commit_and_get_project(client, idea_id)
        body = _waiver_wire_body(project_id, version)
        body["actor"] = {"subject_id": "other@example.com", "email": "other@example.com"}
        body["idempotency_key"] = "waiver-unauthorized"

        resp = client.post("/api/content-workflow/submit", json=body)
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["outcome"] == "rejected"
        assert receipt["rejection"]["code"] == "authority-required"
    finally:
        app.state.content_workflow = None
