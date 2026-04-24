"""Guards the per-tool replay-safety defaults.

A refactor that silently demotes ``write_file`` from ``checkpoint`` to
``safe`` would cause re-execution on resume to corrupt user files. This
test pins the values the design doc commits to.
"""

from specialagent.agent.tools.a2a import A2ACallTool, A2ADiscoverTool
from specialagent.agent.tools.base import Tool
from specialagent.agent.tools.cron import CronTool
from specialagent.agent.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WorkspaceTreeTool,
    WriteFileTool,
)
from specialagent.agent.tools.message import MessageTool
from specialagent.agent.tools.plan import (
    ActivatePlanTool,
    AddPlanArtifactTool,
    AddTaskCommentTool,
    AssignPlanTaskTool,
    CreatePlanTaskTool,
    CreatePlanTool,
    DeletePlanTool,
    GetPlanArtifactTool,
    GetPlanTool,
    ListPlanArtifactsTool,
    ListPlanAssigneesTool,
    ListPlansTool,
    ListTaskCommentsTool,
    PlanQueryTool,
    UpdatePlanTaskTool,
)
from specialagent.agent.tools.shell import ExecTool
from specialagent.agent.tools.spawn import SpawnTool
from specialagent.agent.tools.web import WebFetchTool, WebSearchTool


class TestSafeDefaults:
    """Pure-read tools must be ``safe`` so resume can re-run them freely."""

    def test_filesystem_reads(self) -> None:
        assert ReadFileTool.replay_safety == "safe"
        assert ListDirTool.replay_safety == "safe"
        assert WorkspaceTreeTool.replay_safety == "safe"

    def test_web_reads(self) -> None:
        assert WebSearchTool.replay_safety == "safe"
        assert WebFetchTool.replay_safety == "safe"

    def test_plan_reads(self) -> None:
        assert ListPlansTool.replay_safety == "safe"
        assert PlanQueryTool.replay_safety == "safe"
        assert GetPlanTool.replay_safety == "safe"
        assert ListPlanArtifactsTool.replay_safety == "safe"
        assert GetPlanArtifactTool.replay_safety == "safe"
        assert ListTaskCommentsTool.replay_safety == "safe"
        assert ListPlanAssigneesTool.replay_safety == "safe"

    def test_a2a_discover(self) -> None:
        assert A2ADiscoverTool.replay_safety == "safe"


class TestCheckpointDefaults:
    """Side-effecting tools must default to ``checkpoint`` so a half-
    completed call surfaces as "[INTERRUPTED]" rather than re-running."""

    def test_filesystem_writes(self) -> None:
        assert WriteFileTool.replay_safety == "checkpoint"
        assert EditFileTool.replay_safety == "checkpoint"

    def test_shell_exec(self) -> None:
        assert ExecTool.replay_safety == "checkpoint"

    def test_message(self) -> None:
        assert MessageTool.replay_safety == "checkpoint"

    def test_spawn_and_cron(self) -> None:
        assert SpawnTool.replay_safety == "checkpoint"
        assert CronTool.replay_safety == "checkpoint"

    def test_a2a_call(self) -> None:
        assert A2ACallTool.replay_safety == "checkpoint"

    def test_plan_mutations(self) -> None:
        for cls in (
            CreatePlanTool,
            DeletePlanTool,
            ActivatePlanTool,
            CreatePlanTaskTool,
            AssignPlanTaskTool,
            UpdatePlanTaskTool,
            AddPlanArtifactTool,
            AddTaskCommentTool,
        ):
            assert cls.replay_safety == "checkpoint", f"{cls.__name__} must be checkpoint"


class TestBaseDefault:
    def test_base_class_default(self) -> None:
        assert Tool.replay_safety == "checkpoint"
