from arga_cli import main


def test_validate_pr_command_rejects_removed_api() -> None:
    args = main.build_parser().parse_args(["validate", "pr", "--repo", "arga-labs/validation-server", "--pr", "182"])

    try:
        args.func(args)
    except main.CliError as exc:
        message = str(exc)
        assert "Manual PR validation runs were removed" in message
        assert "arga previews sandboxes run" in message
        assert "arga test-runner tests run" in message
    else:
        raise AssertionError("expected CliError")


def test_previews_pr_checks_run_rejects_removed_api() -> None:
    args = main.build_parser().parse_args(
        ["previews", "pr-checks", "run", "--repo", "arga-labs/validation-server", "--pr", "182", "--json"]
    )

    try:
        args.func(args)
    except main.CliError as exc:
        assert "Manual PR validation runs were removed" in str(exc)
    else:
        raise AssertionError("expected CliError")
