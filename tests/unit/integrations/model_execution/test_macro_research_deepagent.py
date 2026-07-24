from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Annotated, Any, TypedDict, cast

import pytest
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import PrivateAttr

from parallax.domains.macro_intel.services.macro_research import (
    FrozenMacroEvidenceScope,
    MacroEvidenceCatalog,
    MacroEvidenceRecord,
    MacroNewsQuery,
    MacroObservationQuery,
    MacroPriorResearch,
    MacroResearchArtifactDraft,
    MacroResearchIntegrityError,
)
from parallax.integrations.model_execution.macro_research_deepagent import (
    MACRO_RESEARCH_PROMPT_VERSION,
    MACRO_RESEARCH_WORKFLOW_VERSION,
    MacroResearchDeepAgent,
)

SESSION = date(2026, 7, 23)
CUTOFF_MS = 1_784_836_800_000
SEALED_AT_MS = CUTOFF_MS + 60_000
OBSERVATION_REF = "macro:asset:spy:2026-07-23:primary"
NEWS_REF = "news:fomc:2026-07-23"


def test_deepagent_has_no_whole_research_wall_clock_timeout() -> None:
    assert "timeout_seconds" not in inspect.signature(MacroResearchDeepAgent).parameters
    assert "wait_for" not in inspect.getsource(MacroResearchDeepAgent.analyze)


def test_deepagent_keeps_native_capabilities_and_uses_scoped_tools_without_forced_order(
    tmp_path: Path,
) -> None:
    model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    reader = _FakeReader()
    checkpointer = MemorySaver()
    checkpointer_context = _AsyncCheckpointerContext(checkpointer)
    captured: dict[str, Any] = {}
    graph = _AutonomousGraph()

    def agent_factory(**kwargs: Any) -> _AutonomousGraph:
        captured.update(kwargs)
        graph.kwargs = kwargs
        return graph

    adapter = MacroResearchDeepAgent(
        model=model,
        model_name="fake-macro-model",
        reader=reader,
        checkpointer_context_factory=lambda: checkpointer_context,
        workspace_root=tmp_path,
        agent_factory=agent_factory,
    )

    result = asyncio.run(adapter.analyze(_scope()))

    assert captured["model"] is model
    assert captured["name"] == "macro-research-parent"
    assert captured["checkpointer"] is checkpointer
    assert checkpointer_context.entered
    assert checkpointer_context.exited
    backend = captured["backend"]
    write_result = backend.write("/workspace/numbers.txt", "2\n3\n")
    assert write_result.error is None
    execute_result = backend.execute(
        """python -c "from pathlib import Path; print(sum(map(int, Path('numbers.txt').read_text().split())))" """
    )
    assert execute_result.exit_code == 0
    assert execute_result.output.strip() == "5"
    assert isinstance(captured["response_format"], ToolStrategy)
    assert captured["response_format"].schema is MacroResearchArtifactDraft
    assert "middleware" not in captured
    assert [tool.name for tool in captured["tools"]] == [
        "inspect_macro_evidence_catalog",
        "search_macro_observations",
        "read_macro_evidence",
        "search_macro_news",
        "read_prior_macro_research",
    ]
    assert [subagent["name"] for subagent in captured["subagents"]] == [
        "evidence-analyst",
        "cross-asset-challenger",
        "skeptical-editor",
    ]
    assert all(
        [tool.name for tool in subagent["tools"]] == [tool.name for tool in captured["tools"]]
        for subagent in captured["subagents"]
    )
    assert "中文" in captured["system_prompt"]
    assert "自主" in captured["system_prompt"]
    assert "/workspace/" in captured["system_prompt"]
    assert "execute" in captured["system_prompt"]
    assert graph.config == {"configurable": {"thread_id": _scope().scope_id}}
    assert reader.call_names[:2] == ["search_news", "catalog"]
    assert result.artifact.session_date == SESSION
    assert result.report_markdown.startswith("#")
    assert result.model_name == "fake-macro-model"
    assert result.prompt_version == MACRO_RESEARCH_PROMPT_VERSION
    assert result.workflow_version == MACRO_RESEARCH_WORKFLOW_VERSION
    assert result.audit.verified_source_refs == (NEWS_REF, OBSERVATION_REF)
    assert result.audit.subagents == ("evidence-analyst", "skeptical-editor")
    assert result.artifact.citations[0].source_label == "Primary source"
    assert result.artifact.citations[0].lineage == {
        "concept_key": "asset:spy",
        "series_key": "test:SPY",
    }
    assert result.artifact.citations[1].source_label == "Federal Reserve"
    assert result.artifact.citations[1].url == "https://www.federalreserve.gov/example"
    assert result.artifact.citations[1].lineage == {"source": "official"}
    assert "write_todos" in result.audit.tool_calls
    assert "task" in result.audit.tool_calls


def test_result_rejects_unknown_citation_but_does_not_apply_language_or_opinion_gates() -> None:
    model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    reader = _FakeReader()

    valid = MacroResearchDeepAgent(
        model=model,
        model_name="fake-macro-model",
        reader=reader,
        checkpointer_context_factory=lambda: _AsyncCheckpointerContext(MemorySaver()),
        agent_factory=lambda **kwargs: _EnglishGraph(kwargs),
    )
    result = asyncio.run(valid.analyze(_scope()))
    assert result.artifact.title == "English is not rejected by production code"

    invalid = MacroResearchDeepAgent(
        model=model,
        model_name="fake-macro-model",
        reader=reader,
        checkpointer_context_factory=lambda: _AsyncCheckpointerContext(MemorySaver()),
        agent_factory=lambda **kwargs: _UnknownCitationGraph(kwargs),
    )
    with pytest.raises(MacroResearchIntegrityError, match="unknown_citations"):
        asyncio.run(invalid.analyze(_scope()))


def test_final_citations_are_hydrated_when_subagent_tool_messages_are_not_in_root_state() -> None:
    model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    reader = _FakeReader()
    adapter = MacroResearchDeepAgent(
        model=model,
        model_name="fake-macro-model",
        reader=reader,
        checkpointer_context_factory=lambda: _AsyncCheckpointerContext(MemorySaver()),
        agent_factory=lambda **kwargs: _FinalCitationOnlyGraph(kwargs),
    )

    result = asyncio.run(adapter.analyze(_scope()))

    assert reader.call_names == ["read_evidence"]
    assert result.audit.verified_source_refs == (OBSERVATION_REF, NEWS_REF)
    assert result.audit.tool_calls == ("hydrate_final_citations",)


def test_retry_resumes_pending_checkpoint_without_duplicating_initial_user_message() -> None:
    model = FakeMessagesListChatModel(responses=[AIMessage(content="unused")])
    reader = _FakeReader()
    checkpointer = MemorySaver()
    attempts = 0
    resumed_messages: list[AnyMessage] = []

    def agent_factory(**kwargs: Any) -> Any:
        tools = {tool.name: tool for tool in kwargs["tools"]}

        async def fetch_evidence(_: _ResumeGraphState) -> _ResumeGraphState:
            content = await tools["search_macro_news"].ainvoke(
                {
                    "query": "FOMC",
                    "limit": 1,
                }
            )
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "search_macro_news",
                                "args": {
                                    "query": "FOMC",
                                    "limit": 1,
                                },
                                "id": "search-1",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    ToolMessage(
                        content=content,
                        name="search_macro_news",
                        tool_call_id="search-1",
                    ),
                ]
            }

        async def complete_research(state: _ResumeGraphState) -> _ResumeGraphState:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient_model_failure")
            resumed_messages.extend(state["messages"])
            payload = _artifact_payload()
            payload["sections"][0]["citation_ids"] = ["C002"]
            payload["citations"] = [payload["citations"][1]]
            return {"structured_response": payload}

        builder = StateGraph(_ResumeGraphState)
        builder.add_node("fetch_evidence", cast(Any, fetch_evidence))
        builder.add_node("complete_research", complete_research)
        builder.add_edge(START, "fetch_evidence")
        builder.add_edge("fetch_evidence", "complete_research")
        builder.add_edge("complete_research", END)
        return builder.compile(checkpointer=kwargs["checkpointer"])

    adapter = MacroResearchDeepAgent(
        model=model,
        model_name="fake-macro-model",
        reader=reader,
        checkpointer_context_factory=lambda: _AsyncCheckpointerContext(checkpointer),
        agent_factory=agent_factory,
    )

    async def exercise_retry() -> Any:
        with pytest.raises(RuntimeError, match="transient_model_failure"):
            await adapter.analyze(_scope())
        checkpoint = await checkpointer.aget_tuple({"configurable": {"thread_id": _scope().scope_id}})
        assert checkpoint is not None
        return await adapter.analyze(_scope())

    result = asyncio.run(exercise_retry())

    assert attempts == 2
    assert reader.call_names.count("search_news") == 1
    assert sum(isinstance(message, HumanMessage) for message in resumed_messages) == 1
    assert result.artifact.citations[0].source_ref == NEWS_REF
    assert result.audit.verified_source_refs == (NEWS_REF,)


def test_native_deepagent_task_resume_reuses_specialist_result_and_hydrates_citation() -> None:
    model = _NativeTaskRetryModel()
    reader = _FakeReader()
    checkpointer = MemorySaver()
    adapter = MacroResearchDeepAgent(
        model=model,
        model_name="native-task-retry-model",
        reader=reader,
        checkpointer_context_factory=lambda: _AsyncCheckpointerContext(checkpointer),
    )
    checkpoint_namespaces: set[str] = set()

    async def exercise_retry() -> Any:
        with pytest.raises(RuntimeError, match="native_parent_failure"):
            await adapter.analyze(_scope())
        async for checkpoint in checkpointer.alist({"configurable": {"thread_id": _scope().scope_id}}):
            checkpoint_namespaces.add(str(checkpoint.config["configurable"].get("checkpoint_ns") or ""))
        return await adapter.analyze(_scope())

    result = asyncio.run(exercise_retry())

    assert any(namespace.startswith("tools:") for namespace in checkpoint_namespaces)
    assert model.parent_after_task_calls == 2
    assert reader.call_names.count("search_news") == 1
    assert reader.call_names.count("read_evidence") == 1
    assert model.parent_human_message_counts == (1, 1)
    assert result.artifact.citations[0].source_ref == NEWS_REF
    assert result.audit.verified_source_refs == (NEWS_REF,)
    assert "hydrate_final_citations" in result.audit.tool_calls


def test_native_deepagent_offloads_large_exact_read_and_reads_it_from_checkpoint_filesystem(
    tmp_path: Path,
) -> None:
    model = _NativeLargeExactReadModel()
    reader = _LargePayloadReader()
    checkpointer = MemorySaver()
    adapter = MacroResearchDeepAgent(
        model=model,
        model_name="native-large-exact-read-model",
        reader=reader,
        checkpointer_context_factory=lambda: _AsyncCheckpointerContext(checkpointer),
        workspace_root=tmp_path,
    )

    async def exercise() -> tuple[Any, dict[str, Any]]:
        result = await adapter.analyze(_scope())
        checkpoint_files: dict[str, Any] = {}
        async for checkpoint in checkpointer.alist({"configurable": {"thread_id": _scope().scope_id}}):
            checkpoint_files.update(checkpoint.checkpoint["channel_values"].get("files", {}))
            for _task_id, channel, value in checkpoint.pending_writes or ():
                if channel == "files":
                    checkpoint_files.update(value)
        return result, checkpoint_files

    result, checkpoint_files = asyncio.run(exercise())

    assert "/large_tool_results/" in model.offloaded_tool_message
    assert model.offloaded_path.startswith("/large_tool_results/")
    assert '"evidence_ref":"news:large-0"' in model.read_file_message
    assert "42" in model.execute_message
    calculation_files = list(tmp_path.glob("*/calc.py"))
    assert len(calculation_files) == 1
    assert calculation_files[0].read_text(encoding="utf-8") == "print(6 * 7)\n"
    stored_payload = checkpoint_files[model.offloaded_path]["content"]
    assert isinstance(stored_payload, str)
    assert len(stored_payload) > 80_000
    decoded = json.loads(stored_payload)
    assert decoded["result_mode"] == "full_evidence_records"
    assert [record["evidence_ref"] for record in decoded["results"]] == [
        "news:large-0",
        "news:large-1",
        "news:large-2",
        "news:large-3",
    ]
    assert all(len(record["payload"]["body_text"]) > 12_000 for record in decoded["results"])
    assert all(record["payload"]["body_text"].endswith("宏观证据") for record in decoded["results"])
    assert reader.call_names.count("read_evidence") == 2
    assert result.artifact.citations[0].source_ref == "news:large-0"
    assert result.artifact.citations[0].source_label == "official.example"
    assert "news:large-0" in result.audit.verified_source_refs
    assert "hydrate_final_citations" in result.audit.tool_calls


def test_large_legal_tool_results_are_bounded_and_agent_can_continue_instead_of_crashing() -> None:
    graph = _PayloadRecoveryGraph()
    adapter = MacroResearchDeepAgent(
        model=FakeMessagesListChatModel(responses=[AIMessage(content="unused")]),
        model_name="payload-recovery-model",
        reader=_LargePayloadReader(),
        checkpointer_context_factory=lambda: _AsyncCheckpointerContext(MemorySaver()),
        agent_factory=lambda **kwargs: graph.bind(kwargs),
    )

    result = asyncio.run(adapter.analyze(_scope()))

    assert result.artifact.title == "大结果仍可恢复"
    assert len(graph.search_payload) <= 100_000
    search = json.loads(graph.search_payload)
    assert search["result_mode"] == "compact_search_hits"
    assert search["truncated_by_payload"] is True
    assert search["next_offset"] == search["returned_count"]
    assert 0 < search["returned_count"] < 50
    assert "body_text" not in search["results"][0]["facts"]
    assert len(graph.read_payload) > 100_000
    read = json.loads(graph.read_payload)
    assert read["result_mode"] == "full_evidence_records"
    assert len(read["results"]) == 20
    assert read["results"][0]["payload"]["body_text"].startswith("news-0-")
    assert read["missing_source_refs"] == []


class _ResumeGraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    structured_response: dict[str, Any]


class _NativeTaskRetryModel(BaseChatModel):
    _parent_after_task_calls: int = PrivateAttr(default=0)
    _parent_human_message_counts: list[int] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "native-task-retry-model"

    @property
    def parent_after_task_calls(self) -> int:
        return self._parent_after_task_calls

    @property
    def parent_human_message_counts(self) -> tuple[int, ...]:
        return tuple(self._parent_human_message_counts)

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> _NativeTaskRetryModel:
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        specialist_call = any(
            isinstance(message, HumanMessage) and message.content == "NATIVE_SPECIALIST_LOOKUP" for message in messages
        )
        if specialist_call:
            if any(isinstance(message, ToolMessage) and message.name == "search_macro_news" for message in messages):
                return _chat_result(AIMessage(content=f"已核验冻结新闻证据，source_ref={NEWS_REF}"))
            return _chat_result(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_macro_news",
                            "args": {"query": "FOMC", "limit": 1},
                            "id": "native-evidence-1",
                            "type": "tool_call",
                        }
                    ],
                )
            )

        if any(isinstance(message, ToolMessage) and message.name == "task" for message in messages):
            self._parent_human_message_counts.append(sum(isinstance(message, HumanMessage) for message in messages))
            self._parent_after_task_calls += 1
            if self._parent_after_task_calls == 1:
                raise RuntimeError("native_parent_failure")
            payload = _artifact_payload()
            payload["sections"][0]["citation_ids"] = ["C002"]
            payload["citations"] = [payload["citations"][1]]
            return _chat_result(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "MacroResearchArtifactDraft",
                            "args": payload,
                            "id": "native-structured-1",
                            "type": "tool_call",
                        }
                    ],
                )
            )

        return _chat_result(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "NATIVE_SPECIALIST_LOOKUP",
                            "subagent_type": "evidence-analyst",
                        },
                        "id": "native-task-1",
                        "type": "tool_call",
                    }
                ],
            )
        )


class _NativeLargeExactReadModel(BaseChatModel):
    _offloaded_tool_message: str = PrivateAttr(default="")
    _offloaded_path: str = PrivateAttr(default="")
    _read_file_message: str = PrivateAttr(default="")
    _execute_message: str = PrivateAttr(default="")

    @property
    def _llm_type(self) -> str:
        return "native-large-exact-read-model"

    @property
    def offloaded_tool_message(self) -> str:
        return self._offloaded_tool_message

    @property
    def offloaded_path(self) -> str:
        return self._offloaded_path

    @property
    def read_file_message(self) -> str:
        return self._read_file_message

    @property
    def execute_message(self) -> str:
        return self._execute_message

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> _NativeLargeExactReadModel:
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        execute_messages = [
            message for message in messages if isinstance(message, ToolMessage) and message.name == "execute"
        ]
        if execute_messages:
            self._execute_message = str(execute_messages[-1].content)
            payload = _artifact_payload()
            payload.update(
                {
                    "title": "原生文件系统恢复大证据",
                    "sections": [
                        {
                            "section_id": "native_vfs",
                            "title": "大证据读取",
                            "body_markdown": "完整证据由原生文件系统承接，并可使用 execute 做计算。",
                            "citation_ids": ["C001"],
                        }
                    ],
                    "citations": [
                        {
                            "citation_id": "C001",
                            "source_ref": "news:large-0",
                        }
                    ],
                }
            )
            return _chat_result(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "MacroResearchArtifactDraft",
                            "args": payload,
                            "id": "native-large-structured-1",
                            "type": "tool_call",
                        }
                    ],
                )
            )

        workspace_write_messages = [
            message for message in messages if isinstance(message, ToolMessage) and message.name == "write_file"
        ]
        if workspace_write_messages:
            return _chat_result(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute",
                            "args": {"command": "python calc.py"},
                            "id": "native-large-execute-1",
                            "type": "tool_call",
                        }
                    ],
                )
            )

        read_file_messages = [
            message for message in messages if isinstance(message, ToolMessage) and message.name == "read_file"
        ]
        if read_file_messages:
            self._read_file_message = str(read_file_messages[-1].content)
            return _chat_result(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {
                                "file_path": "/workspace/calc.py",
                                "content": "print(6 * 7)\n",
                            },
                            "id": "native-large-write-workspace-1",
                            "type": "tool_call",
                        }
                    ],
                )
            )

        exact_read_messages = [
            message
            for message in messages
            if isinstance(message, ToolMessage) and message.name == "read_macro_evidence"
        ]
        if exact_read_messages:
            self._offloaded_tool_message = str(exact_read_messages[-1].content)
            marker = "saved in the filesystem at this path: "
            if marker not in self._offloaded_tool_message:
                raise AssertionError("native_exact_read_was_not_offloaded")
            self._offloaded_path = self._offloaded_tool_message.split(marker, 1)[1].splitlines()[0].strip()
            return _chat_result(
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {
                                "file_path": self._offloaded_path,
                                "offset": 0,
                                "limit": 1,
                            },
                            "id": "native-large-read-file-1",
                            "type": "tool_call",
                        }
                    ],
                )
            )

        return _chat_result(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_macro_evidence",
                        "args": {
                            "source_refs": [
                                "news:large-0",
                                "news:large-1",
                                "news:large-2",
                                "news:large-3",
                            ]
                        },
                        "id": "native-large-exact-read-1",
                        "type": "tool_call",
                    }
                ],
            )
        )


def _chat_result(message: AIMessage) -> ChatResult:
    return ChatResult(generations=[ChatGeneration(message=message)])


class _AutonomousGraph:
    kwargs: dict[str, Any]
    config: dict[str, Any] | None = None

    async def ainvoke(
        self,
        _input: Mapping[str, Any] | None,
        *,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.config = dict(config) if config is not None else None
        tools = {tool.name: tool for tool in self.kwargs["tools"]}
        # Deliberately use a useful order that is unlike any read-pack FSM.
        await tools["search_macro_news"].ainvoke({"query": "FOMC", "limit": 5})
        await tools["inspect_macro_evidence_catalog"].ainvoke({})
        await tools["search_macro_observations"].ainvoke(
            {
                "query": "SPY",
                "concept_keys": ["asset:spy"],
                "start_date": "2026-07-01",
                "end_date": "2026-07-23",
                "limit": 10,
            }
        )
        await tools["read_macro_evidence"].ainvoke({"source_refs": [OBSERVATION_REF]})
        await tools["read_prior_macro_research"].ainvoke({"limit": 2})
        return {
            "structured_response": _artifact_payload(),
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_todos",
                            "args": {"todos": []},
                            "id": "todo-1",
                            "type": "tool_call",
                        },
                        {
                            "name": "task",
                            "args": {
                                "description": "检查证据",
                                "subagent_type": "evidence-analyst",
                            },
                            "id": "task-1",
                            "type": "tool_call",
                        },
                        {
                            "name": "task",
                            "args": {
                                "description": "反证审阅",
                                "subagent_type": "skeptical-editor",
                            },
                            "id": "task-2",
                            "type": "tool_call",
                        },
                    ],
                )
            ],
        }


class _PayloadRecoveryGraph:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}
        self.search_payload = ""
        self.read_payload = ""

    def bind(self, kwargs: dict[str, Any]) -> _PayloadRecoveryGraph:
        self.kwargs = kwargs
        return self

    async def ainvoke(
        self,
        _input: Mapping[str, Any] | None,
        *,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del config
        tools = {tool.name: tool for tool in self.kwargs["tools"]}
        self.search_payload = await tools["search_macro_news"].ainvoke({"query": "", "limit": 50, "offset": 0})
        self.read_payload = await tools["read_macro_evidence"].ainvoke(
            {"source_refs": [f"news:large-{index}" for index in range(20)]}
        )
        payload = _artifact_payload()
        payload.update(
            {
                "title": "大结果仍可恢复",
                "sections": [
                    {
                        "section_id": "bounded_tools",
                        "title": "工具响应",
                        "body_markdown": "Agent 能继续缩小或分页读取。",
                        "citation_ids": [],
                    }
                ],
                "citations": [],
            }
        )
        return {"structured_response": payload, "messages": []}


class _AsyncCheckpointerContext:
    def __init__(self, checkpointer: MemorySaver) -> None:
        self.checkpointer = checkpointer
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> MemorySaver:
        self.entered = True
        return self.checkpointer

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        del exc_type, exc, traceback
        self.exited = True


class _EnglishGraph:
    def __init__(self, kwargs: dict[str, Any]) -> None:
        self._kwargs = kwargs

    async def ainvoke(
        self,
        _input: Mapping[str, Any] | None,
        *,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del config
        search = {tool.name: tool for tool in self._kwargs["tools"]}["search_macro_observations"]
        await search.ainvoke(
            {
                "query": "",
                "concept_keys": ["asset:spy"],
                "limit": 1,
            }
        )
        payload = _artifact_payload()
        payload.update(
            {
                "title": "English is not rejected by production code",
                "executive_summary": "The evidence remains mixed.",
                "sections": [
                    {
                        "section_id": "mixed_evidence",
                        "title": "Mixed evidence",
                        "body_markdown": "The model owns this professional opinion.",
                        "citation_ids": ["C001"],
                    }
                ],
                "citations": [payload["citations"][0]],
            }
        )
        return {"structured_response": payload, "messages": []}


class _UnknownCitationGraph:
    def __init__(self, kwargs: dict[str, Any]) -> None:
        self._kwargs = kwargs

    async def ainvoke(
        self,
        _input: Mapping[str, Any] | None,
        *,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del config
        catalog = {tool.name: tool for tool in self._kwargs["tools"]}["inspect_macro_evidence_catalog"]
        await catalog.ainvoke({})
        payload = _artifact_payload()
        payload["citations"][0]["source_ref"] = "macro:unknown"
        return {"structured_response": payload, "messages": []}


class _FinalCitationOnlyGraph:
    def __init__(self, kwargs: dict[str, Any]) -> None:
        self._kwargs = kwargs

    async def ainvoke(
        self,
        _input: Mapping[str, Any] | None,
        *,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del self._kwargs, config
        return {"structured_response": _artifact_payload(), "messages": []}


class _FakeReader:
    def __init__(self) -> None:
        self.call_names: list[str] = []

    def catalog(self, *, scope: FrozenMacroEvidenceScope) -> MacroEvidenceCatalog:
        self.call_names.append("catalog")
        return MacroEvidenceCatalog(
            session_date=scope.session_date,
            market_cutoff_ms=scope.market_cutoff_ms,
            sealed_at_ms=scope.sealed_at_ms,
            concept_keys=("asset:spy", "rates:us10y"),
            source_labels=("Primary source", "Federal Reserve"),
            observation_count=2,
            news_count=1,
            prior_research_count=1,
        )

    def search_observations(
        self,
        *,
        scope: FrozenMacroEvidenceScope,
        query: MacroObservationQuery,
    ) -> tuple[MacroEvidenceRecord, ...]:
        del scope, query
        self.call_names.append("search_observations")
        return (_observation(),)

    def read_evidence(
        self,
        *,
        scope: FrozenMacroEvidenceScope,
        source_refs: tuple[str, ...],
    ) -> tuple[MacroEvidenceRecord, ...]:
        del scope
        self.call_names.append("read_evidence")
        records = {
            OBSERVATION_REF: _observation(),
            NEWS_REF: _news(),
        }
        return tuple(records[source_ref] for source_ref in source_refs if source_ref in records)

    def search_news(
        self,
        *,
        scope: FrozenMacroEvidenceScope,
        query: MacroNewsQuery,
    ) -> tuple[MacroEvidenceRecord, ...]:
        del scope, query
        self.call_names.append("search_news")
        return (_news(),)

    def prior_research(
        self,
        *,
        scope: FrozenMacroEvidenceScope,
        limit: int,
        offset: int,
    ) -> tuple[MacroPriorResearch, ...]:
        del scope, limit
        self.call_names.append("prior_research")
        publications = (
            MacroPriorResearch(
                publication_ref="macro-research:2026-07-22",
                session_date=date(2026, 7, 22),
                title="前一交易日宏观研究",
                executive_summary="前一交易日的持久化研究摘要。",
                published_at_ms=CUTOFF_MS - 1,
            ),
        )
        return publications[offset:]


class _LargePayloadReader(_FakeReader):
    def search_news(
        self,
        *,
        scope: FrozenMacroEvidenceScope,
        query: MacroNewsQuery,
    ) -> tuple[MacroEvidenceRecord, ...]:
        del scope
        self.call_names.append("search_news")
        return tuple(_large_news(index) for index in range(query.offset, min(50, query.offset + query.limit)))

    def read_evidence(
        self,
        *,
        scope: FrozenMacroEvidenceScope,
        source_refs: tuple[str, ...],
    ) -> tuple[MacroEvidenceRecord, ...]:
        del scope
        self.call_names.append("read_evidence")
        return tuple(_large_news(int(source_ref.removeprefix("news:large-"))) for source_ref in source_refs)


def _scope() -> FrozenMacroEvidenceScope:
    return FrozenMacroEvidenceScope(
        session_date=SESSION,
        market_cutoff_ms=CUTOFF_MS,
        sealed_at_ms=SEALED_AT_MS,
    )


def _observation() -> MacroEvidenceRecord:
    return MacroEvidenceRecord(
        evidence_ref=OBSERVATION_REF,
        evidence_kind="observation",
        source_label="Primary source",
        concept_key="asset:spy",
        source_timestamp=SESSION.isoformat(),
        available_at_ms=CUTOFF_MS - 1,
        persisted_at_ms=CUTOFF_MS - 1,
        observed_at=SESSION,
        summary="SPY close",
        payload={"concept_key": "asset:spy", "value_numeric": 635.34},
        lineage={"concept_key": "asset:spy", "series_key": "test:SPY"},
    )


def _news() -> MacroEvidenceRecord:
    return MacroEvidenceRecord(
        evidence_ref=NEWS_REF,
        evidence_kind="news",
        source_label="Federal Reserve",
        available_at_ms=CUTOFF_MS - 10_000,
        persisted_at_ms=SEALED_AT_MS - 5_000,
        published_at_ms=CUTOFF_MS - 10_000,
        url="https://www.federalreserve.gov/example",
        summary="FOMC communication",
        payload={"title": "Federal Reserve communication"},
        lineage={"source": "official"},
    )


def _large_news(index: int) -> MacroEvidenceRecord:
    body = f"news-{index}-" + ("宏观证据" * 3_000)
    return MacroEvidenceRecord(
        evidence_ref=f"news:large-{index}",
        evidence_kind="news",
        source_label="official.example",
        available_at_ms=CUTOFF_MS - 10_000 - index,
        persisted_at_ms=SEALED_AT_MS - 5_000,
        published_at_ms=CUTOFF_MS - 10_000 - index,
        url=f"https://official.example/{index}",
        summary=body[:8_000],
        payload={
            "title": f"Large evidence {index}",
            "summary": body[:8_000],
            "body_text": body,
            "language": "zh",
            "lifecycle_status": "processed",
        },
        lineage={"news_item_id": f"large-{index}", "source": "official"},
    )


def _artifact_payload() -> dict[str, Any]:
    return {
        "schema_version": "macro_research_artifact_v2",
        "session_date": SESSION.isoformat(),
        "market_cutoff_ms": CUTOFF_MS,
        "title": "完成交易日宏观研究",
        "executive_summary": "跨资产证据与官方文本存在可解释的张力。",
        "sections": [
            {
                "section_id": "cross_asset_evidence",
                "title": "跨资产证据",
                "body_markdown": "SPY 收盘证据与官方文本共同构成当前背景。",
                "citation_ids": ["C001", "C002"],
            }
        ],
        "gaps": [
            {
                "gap_id": "history_depth",
                "summary": "历史深度有限",
                "details": "更长历史有助于检验当前组合的罕见程度。",
                "citation_ids": [],
            }
        ],
        "citations": [
            {
                "citation_id": "C001",
                "source_ref": OBSERVATION_REF,
            },
            {
                "citation_id": "C002",
                "source_ref": NEWS_REF,
            },
        ],
        "reviewer_notes": ["已检查主要反证与引用闭合。"],
    }
