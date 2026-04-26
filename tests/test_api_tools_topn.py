"""Top-N filter tests for OpenAPI tool generation.

Builds a synthetic spec with 200 operations and verifies:
  - The resulting tool list never exceeds ``max_tools``.
  - The MAX_TOOLS_HARD_CAP cap is enforced even if a config asks for more.
  - When ``role_hint`` is set, the heuristic puts overlapping-tag operations first.
"""

import pytest

from specialagent.agent.tools.openapi import (
    MAX_TOOLS_HARD_CAP,
    ApiOperation,
    rank_operations,
)


def _make_ops(n: int, *, tag_a: int = 0) -> list[ApiOperation]:
    ops: list[ApiOperation] = []
    for i in range(n):
        tag = "alpha" if i < tag_a else "beta"
        ops.append(
            ApiOperation(
                operation_id=f"op_{i:03d}",
                method="GET",
                path=f"/things/{i}",
                summary=f"thing {i} {tag}",
                tags=[tag],
            )
        )
    return ops


class TestTopN:
    def test_caps_at_requested_max(self) -> None:
        ops = _make_ops(200)
        ranked = rank_operations(ops, max_tools=20)
        assert len(ranked) == 20

    def test_hard_cap_enforced(self) -> None:
        ops = _make_ops(MAX_TOOLS_HARD_CAP * 4)
        # Even if the caller asks for far more, the hard cap wins.
        ranked = rank_operations(ops, max_tools=999_999)
        assert len(ranked) == MAX_TOOLS_HARD_CAP

    def test_role_hint_prioritises_matching_tag(self) -> None:
        ops = _make_ops(100, tag_a=20)
        ranked = rank_operations(ops, role_hint="alpha", max_tools=20)
        assert len(ranked) == 20
        # All 20 alpha ops should be selected.
        assert {op.operation_id for op in ranked} == {f"op_{i:03d}" for i in range(20)}

    def test_role_hint_preserves_total_cap(self) -> None:
        ops = _make_ops(50)
        ranked = rank_operations(ops, role_hint="anything", max_tools=10)
        assert len(ranked) == 10

    @pytest.mark.parametrize("hint", ["", "   "])
    def test_no_role_hint_preserves_order(self, hint: str) -> None:
        ops = _make_ops(20)
        ranked = rank_operations(ops, role_hint=hint, max_tools=10)
        assert [op.operation_id for op in ranked] == [op.operation_id for op in ops[:10]]


class TestEnabledOperations:
    def test_enabled_short_circuits_role_hint(self) -> None:
        ops = _make_ops(50)
        ranked = rank_operations(
            ops,
            role_hint="anything",
            enabled_operations=["op_005", "op_010"],
            max_tools=10,
        )
        assert [op.operation_id for op in ranked] == ["op_005", "op_010"]
