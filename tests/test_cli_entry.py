from __future__ import annotations

from arga_cli import entry, main


def test_entry_inject_modifies_dockerfile_and_writes_script(tmp_path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\nRUN pip install flask\n")

    args = main.build_parser().parse_args(["entry", "inject", str(dockerfile)])
    exit_code = args.func(args)

    assert exit_code == 0
    content = dockerfile.read_text()
    assert entry.INJECT_MARKER in content
    assert 'ENTRYPOINT ["/arga/arga-entry", "run", "--"]' in content
    assert "COPY arga-entry /arga/arga-entry" in content

    script = tmp_path / "arga-entry"
    assert script.exists()
    assert script.stat().st_mode & 0o111


def test_entry_inject_rejects_already_injected_dockerfile(tmp_path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(f"FROM node:20\n{entry.INJECT_MARKER}\n")

    args = main.build_parser().parse_args(["entry", "inject", str(dockerfile)])
    exit_code = args.func(args)

    assert exit_code == 1


def test_entry_inject_to_output_path_leaves_original_unchanged(tmp_path) -> None:
    original = tmp_path / "Dockerfile"
    original.write_text("FROM python:3.12\n")
    output = tmp_path / "Dockerfile.arga"

    args = main.build_parser().parse_args(["entry", "inject", str(original), "--output", str(output)])
    exit_code = args.func(args)

    assert exit_code == 0
    assert entry.INJECT_MARKER not in original.read_text()
    assert entry.INJECT_MARKER in output.read_text()


def test_entry_eject_removes_injection(tmp_path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\nRUN pip install flask\n")
    script = tmp_path / "arga-entry"

    # Inject first
    args = main.build_parser().parse_args(["entry", "inject", str(dockerfile)])
    args.func(args)
    assert entry.INJECT_MARKER in dockerfile.read_text()
    assert script.exists()

    # Then eject
    args = main.build_parser().parse_args(["entry", "eject", str(dockerfile)])
    exit_code = args.func(args)

    assert exit_code == 0
    assert entry.INJECT_MARKER not in dockerfile.read_text()
    assert "FROM python:3.12-slim" in dockerfile.read_text()
    assert not script.exists()


def test_entry_show_outputs_script(capsys) -> None:
    args = main.build_parser().parse_args(["entry", "show"])
    exit_code = args.func(args)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "arga-entry" in output
    assert "install_ca" in output or "_install_ca" in output


def test_entry_inject_missing_dockerfile(tmp_path) -> None:
    args = main.build_parser().parse_args(["entry", "inject", str(tmp_path / "nonexistent")])
    exit_code = args.func(args)

    assert exit_code == 1
