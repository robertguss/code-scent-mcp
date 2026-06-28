from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "ts-react-next-basic"
DECISION_DOC = ROOT / "docs" / "language-packs.md"


def test_fixture_contains_expected_ts_react_next_patterns() -> None:
    assert FIXTURE_ROOT.is_dir()
    assert (FIXTURE_ROOT / "package.json").is_file()
    assert (FIXTURE_ROOT / "tsconfig.json").is_file()

    expected_files = {
        "app/api/tasks/route.ts",
        "app/tasks/page.tsx",
        "components/task-card.jsx",
        "components/task-list.tsx",
        "hooks/useTasks.ts",
        "lib/tasks.js",
        "pages/legacy.jsx",
        "tests/task-list.test.tsx",
    }
    actual_files = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file()
    }

    assert expected_files <= actual_files
    assert _contains("components/task-list.tsx", "export function TaskList")
    assert _contains("components/task-list.tsx", "useTasks(")
    assert _contains("hooks/useTasks.ts", "export function useTasks")
    assert _contains("app/api/tasks/route.ts", "export async function GET")
    assert _contains("app/tasks/page.tsx", "export default async function TasksPage")
    assert _contains("pages/legacy.jsx", "export default function LegacyTasksPage")
    assert _contains("lib/tasks.js", "export async function loadTasks")

    decision = DECISION_DOC.read_text()
    # Audit-corrected (U18): non-Python packs are regex-heuristic, not tree-sitter.
    assert "regex" in decision
    assert "no tree-sitter" in decision
    assert "no-network" in decision


def _contains(relative_path: str, needle: str) -> bool:
    return needle in (FIXTURE_ROOT / relative_path).read_text()
