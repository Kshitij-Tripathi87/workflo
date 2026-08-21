"""Tenant Shield command-line interface.

Usage:
    workflo --version
    workflo run [-- pytest-args...]
    workflo report --results <results.json> [--format html|pdf]
    workflo init [--dir <target>]
"""

import sys


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        _print_usage()
        return 1

    cmd = argv[0]

    if cmd in ("-h", "--help", "help"):
        _print_usage()
        return 0

    if cmd == "--version":
        from workflo import __version__
        print(__version__)
        return 0

    if cmd == "run":
        return _cmd_run(argv[1:])

    if cmd == "report":
        return _cmd_report(argv[1:])

    if cmd == "init":
        return _cmd_init(argv[1:])

    sys.stderr.write(f"Unknown command: {cmd}\n")
    _print_usage()
    return 2


def _print_usage():
    print(
        "workflo - multi-tenant isolation testing\n\n"
        "Commands:\n"
        "  run [-- pytest-args...]     Run the test suite (delegates to pytest)\n"
        "  report --results FILE      Generate a SOC 2 evidence report from JSON results\n"
        "  init [--dir DIR]            Scaffold a workflo config and first test\n\n"
        "Options:\n"
        "  --version                   Print version and exit\n"
        "  -h, --help                  Show this help\n"
    )


def _cmd_run(rest):
    import pytest

    args, results_out = _split_results_arg(rest)

    if results_out:
        args = ["--tenant-shield-results", results_out] + args

    return int(pytest.main(args))


def _split_results_arg(args):
    """Pull a `--output-json FILE` / `--results FILE` out of args for the plugin."""
    out = None
    keep = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--output-json", "--results", "--tenant-shield-results"):
            if i + 1 < len(args):
                out = args[i + 1]
                i += 2
                continue
        elif a.startswith("--output-json="):
            out = a.split("=", 1)[1]
            i += 1
            continue
        elif a.startswith("--results="):
            out = a.split("=", 1)[1]
            i += 1
            continue
        keep.append(a)
        i += 1
    return keep, out


def _cmd_report(rest):
    from workflo.reporting import compliance_report
    return compliance_report.from_cli(rest)


def _cmd_init(rest):
    from workflo import scaffolding
    return scaffolding.from_cli(rest)


if __name__ == "__main__":
    main()
