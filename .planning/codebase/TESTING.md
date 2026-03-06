# Testing Patterns

**Analysis Date:** 2026-03-07

## Test Framework

**Runner:**
- pytest >= 8.0
- pytest-asyncio >= 0.23 (auto mode)
- Config: `[tool.pytest.ini_options]` in `pyproject.toml`

**Assertion Library:**
- Built-in `assert` statements (pytest rewrites)
- `pytest.raises` for exception testing

**Run Commands:**
```bash
pytest tests/ -x -q              # Run all tests, stop on first failure
pytest tests/ -v                  # Verbose output
make test                         # Shorthand via Makefile
pytest tests/ --cov=orchestra --cov-report=term-missing  # With coverage
make test-cov                     # Coverage shorthand
pytest tests/unit/test_core.py -v # Run specific file
```

## Test File Organization

**Location:**
- Separate `tests/` directory at project root (not co-located with source)
- Unit tests in `tests/unit/`
- Fixtures module in `tests/fixtures/`
- Smoke tests at `tests/test_smoke.py`
- Shared fixtures in `tests/conftest.py`

**Naming:**
- Test files: `test_*.py` prefix
- Test classes: `Test*` prefix with `PascalCase`: `TestTypes`, `TestState`, `TestGraph`
- Test methods: `test_*` prefix with `snake_case`: `test_merge_list`, `test_fluent_then`

**Structure:**
```
tests/
  __init__.py
  conftest.py              # Shared fixtures (currently minimal)
  test_smoke.py            # Import/scaffolding smoke tests
  fixtures/
    __init__.py            # Test fixture factories (currently empty)
  unit/
    __init__.py
    test_core.py           # Core types, state, graph, tools, agent integration tests
```

## Test Structure

**Suite Organization:**
- Tests grouped by component using classes (no shared state between classes)
- Classes act as logical namespaces, not as test fixtures
- Each class tests a single module/concept
- Section comments (`# ===== Section =====`) separate major test groups

```python
# ===== Types =====

class TestTypes:
    def test_message_frozen(self):
        msg = Message(role=MessageRole.USER, content="hi")
        with pytest.raises(Exception):
            msg.content = "changed"

    def test_tool_call_generates_id(self):
        tc1 = ToolCall(name="test", arguments={})
        tc2 = ToolCall(name="test", arguments={})
        assert tc1.id != tc2.id


# ===== State =====

class TestState:
    def test_merge_list(self):
        assert merge_list([1, 2], [3, 4]) == [1, 2, 3, 4]
```

**Patterns:**
- No setup/teardown methods used; each test is self-contained
- Test data created inline within each test method
- Pydantic state classes defined inline within test methods when needed
- Async test functions use `@pytest.mark.asyncio` decorator (auto mode from config)

## Mocking

**Framework:** `orchestra.testing.ScriptedLLM` (custom deterministic mock)

**Primary Pattern -- ScriptedLLM:**
```python
from orchestra.testing import ScriptedLLM
from orchestra.core.types import LLMResponse, ToolCall

# Simple string responses
llm = ScriptedLLM(["response 1", "response 2"])

# LLMResponse objects for tool calls
llm = ScriptedLLM([
    LLMResponse(
        content="Let me calculate that.",
        tool_calls=[ToolCall(name="calculator", arguments={"expression": "2+2"})],
    ),
    LLMResponse(content="The answer is 4."),
])

# Usage in test
ctx = ExecutionContext(provider=llm)
result = await agent_inst.run("input", ctx)
assert llm.call_count == 2
assert llm.call_log[0]["model"] == "test-model"
```

**ScriptedLLM Features** (defined in `src/orchestra/testing/scripted.py`):
- Implements `LLMProvider` protocol for drop-in testing
- Accepts `list[str | LLMResponse]` as scripted responses
- Returns responses in order; raises `ScriptExhaustedError` when exhausted
- Tracks all calls in `call_log` with messages, model, tools, temperature
- `call_count` property for assertion
- `reset()` method to replay the same script

**What to Mock:**
- LLM providers: Always use `ScriptedLLM` instead of real API calls
- External HTTP calls: Not tested directly (no integration tests with real APIs)

**What NOT to Mock:**
- State management (`WorkflowState`, reducers) -- test with real implementations
- Graph compilation and execution -- test with real `WorkflowGraph.compile()`
- Tool execution -- define real async functions in tests
- Error hierarchy -- test with real exception classes

**No use of unittest.mock:**
- The codebase does not use `unittest.mock`, `MagicMock`, or `patch`
- `ScriptedLLM` replaces the need for mocking the LLM layer
- Node functions are defined as real async functions directly in test methods

## Fixtures and Factories

**Test Data:**
```python
# Inline state class definition (per-test)
class S(WorkflowState):
    items: Annotated[list[str], merge_list] = []
    count: Annotated[int, sum_numbers] = 0

state = S(items=["a"], count=1)

# Inline node function definition (per-test)
async def node_a(state: dict) -> dict:
    return {"result": "hello", "count": 1}

# Inline tool definition (per-test)
@tool
async def calculator(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))
```

**Location:**
- `tests/conftest.py` -- exists but only has a docstring; no shared fixtures yet
- `tests/fixtures/__init__.py` -- exists but empty; intended for future fixture factories
- All test data is currently created inline within each test method

## Coverage

**Requirements:** 80% minimum (enforced in `pyproject.toml` via `[tool.coverage.report] fail_under = 80`)

**Coverage Source:** `orchestra` package only (`[tool.coverage.run] source = ["orchestra"]`), excluding `tests/*`

**View Coverage:**
```bash
pytest tests/ --cov=orchestra --cov-report=term-missing   # Terminal with missing lines
make test-cov                                               # Makefile shorthand
pytest tests/ --cov=orchestra --cov-report=xml -x          # XML (used in CI for Codecov)
```

**CI Coverage:**
- Codecov upload runs on Python 3.12 + ubuntu-latest in GitHub Actions
- Config: `.github/workflows/ci.yml`

## Test Types

**Smoke Tests** (`tests/test_smoke.py`):
- Verify package is importable
- Verify PEP 561 `py.typed` marker exists
- Verify all subpackages are importable
- 3 tests, all synchronous

**Unit Tests** (`tests/unit/test_core.py`):
- Test individual components in isolation
- 8 test classes, ~35 test methods total
- Cover: types, state/reducers, graph building, execution engine, tools, ScriptedLLM, agent+LLM integration, `run()` function

**Integration Tests:**
- Marked with `@pytest.mark.integration` marker (defined in config but no tests use it yet)
- Agent+ScriptedLLM tests in `TestAgentIntegration` class serve as lightweight integration tests

**E2E Tests:**
- Not implemented. The `examples/` directory provides manual E2E validation scripts

## Common Patterns

**Async Testing:**
```python
class TestExecution:
    @pytest.mark.asyncio
    async def test_sequential_two_node(self):
        class S(WorkflowState):
            result: str = ""
            count: Annotated[int, sum_numbers] = 0

        async def node_a(state: dict) -> dict:
            return {"result": "hello", "count": 1}

        async def node_b(state: dict) -> dict:
            return {"result": state["result"] + " world", "count": 1}

        g = WorkflowGraph(state_schema=S)
        g.add_node("a", node_a)
        g.add_node("b", node_b)
        g.set_entry_point("a")
        g.add_edge("a", "b")
        g.add_edge("b", END)

        result = await g.compile().run({})
        assert result["result"] == "hello world"
        assert result["count"] == 2
```

**Error Testing:**
```python
def test_apply_state_update_unknown_field_raises(self):
    class S(WorkflowState):
        x: int = 0

    state = S(x=1)
    with pytest.raises(StateValidationError, match="Unknown state field"):
        apply_state_update(state, {"nonexistent": 1}, {})

def test_compile_raises_without_entry(self):
    g = WorkflowGraph()
    with pytest.raises(GraphCompileError):
        g.compile()
```

**Tool Testing:**
```python
@pytest.mark.asyncio
async def test_tool_execute(self):
    @tool
    async def add(a: int, b: int) -> str:
        """Add two numbers."""
        return str(a + b)

    result = await add.execute({"a": 2, "b": 3})
    assert result.content == "5"
    assert result.error is None

@pytest.mark.asyncio
async def test_tool_execute_error(self):
    @tool
    async def fail(msg: str) -> str:
        """Always fails."""
        raise RuntimeError(msg)

    result = await fail.execute({"msg": "boom"})
    assert result.error is not None
    assert "boom" in result.error
```

**Agent with Tool Loop Testing:**
```python
@pytest.mark.asyncio
async def test_agent_tool_loop(self):
    @tool
    async def calculator(expression: str) -> str:
        """Evaluate a math expression."""
        return str(eval(expression))

    llm = ScriptedLLM([
        LLMResponse(
            content="Let me calculate that.",
            tool_calls=[ToolCall(name="calculator", arguments={"expression": "2+2"})],
        ),
        LLMResponse(content="The answer is 4."),
    ])

    agent_inst = BaseAgent(name="math", tools=[calculator])
    ctx = ExecutionContext(provider=llm)
    result = await agent_inst.run("What is 2+2?", ctx)

    assert result.output == "The answer is 4."
    assert len(result.tool_calls_made) == 1
    assert llm.call_count == 2
```

## Test Markers

**Configured markers** (in `pyproject.toml`):
- `slow` -- marks tests as slow (deselect with `-m "not slow"`)
- `integration` -- marks integration tests

**Async mode:**
- `asyncio_mode = "auto"` -- pytest-asyncio auto-detects async test functions
- Still use `@pytest.mark.asyncio` explicitly on async test methods (convention in the codebase)

## CI Pipeline

**GitHub Actions** (`.github/workflows/ci.yml`):
- Three jobs: `lint`, `type-check`, `test`
- Lint job: `ruff check` + `ruff format --check`
- Type-check job: `mypy src/orchestra/`
- Test job: matrix of 3 OSes (ubuntu, windows, macos) x 3 Python versions (3.11, 3.12, 3.13)
- Coverage uploaded to Codecov from Python 3.12 + ubuntu run

---

*Testing analysis: 2026-03-07*
