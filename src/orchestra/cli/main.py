"""Orchestra CLI.

Usage:
    orchestra version            Show version
    orchestra init my-project    Scaffold a new project
    orchestra run workflow.py    Run a workflow file
"""

from __future__ import annotations

import typer
from rich.console import Console

from orchestra import __version__

app = typer.Typer(
    name="orchestra",
    help="Orchestra: Python-first multi-agent orchestration framework",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Show Orchestra version."""
    console.print(f"Orchestra v{__version__}")


@app.command()
def init(
    project_name: str = typer.Argument(..., help="Name of the project to create"),
    directory: str = typer.Option(".", help="Directory to create project in"),
) -> None:
    """Initialize a new Orchestra project with scaffolding."""
    from pathlib import Path

    project_dir = Path(directory) / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "agents").mkdir(exist_ok=True)
    (project_dir / "tools").mkdir(exist_ok=True)
    (project_dir / "workflows").mkdir(exist_ok=True)

    workflow_file = project_dir / "workflows" / "hello.py"
    workflow_file.write_text(
        '''\
"""Hello World Orchestra workflow."""

import asyncio
from orchestra.core.graph import WorkflowGraph
from orchestra.core.state import WorkflowState


class HelloState(WorkflowState):
    greeting: str = ""


async def greet(state: dict) -> dict:
    return {"greeting": "Hello from Orchestra!"}


async def main():
    graph = WorkflowGraph(state_schema=HelloState)
    graph.add_node("greeter", greet)
    graph.set_entry_point("greeter")

    compiled = graph.compile()
    result = await compiled.run({})
    print(result["greeting"])


if __name__ == "__main__":
    asyncio.run(main())
''',
        encoding="utf-8",
    )

    console.print(f"[green]Created project:[/green] {project_dir}")
    console.print("  agents/")
    console.print("  tools/")
    console.print("  workflows/hello.py")
    console.print(f"\nRun: [bold]cd {project_name} && python workflows/hello.py[/bold]")


@app.command()
def run(
    workflow_file: str = typer.Argument(..., help="Path to workflow Python file"),
) -> None:
    """Run a workflow file."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("workflow", workflow_file)
    if spec is None or spec.loader is None:
        console.print(f"[red]Error:[/red] Cannot load {workflow_file}")
        raise typer.Exit(1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["workflow"] = module
    spec.loader.exec_module(module)

    if hasattr(module, "main"):
        import asyncio

        asyncio.run(module.main())
    else:
        console.print(f"[red]Error:[/red] {workflow_file} has no main() function")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
