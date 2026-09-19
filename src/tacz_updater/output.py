from __future__ import annotations

from .models import Result


def print_results(results: list[Result]) -> None:
    ordered = sorted(results, key=lambda item: (item.source_name.casefold(), not item.success))
    for item in ordered:
        status = "SUCCESS" if item.success else "FAILURE"
        action = item.action.value if item.success else (item.code or "FAILED")
        subject = item.source_name
        if item.target_name:
            subject += f" -> {item.target_name}"
        suffix = f": {item.message}" if item.message else ""
        print(f"{status:<7} [{action}] {subject}{suffix}")

    success_count = sum(item.success for item in results)
    failure_count = len(results) - success_count
    updated = sum(item.action.value in {"UPDATED", "WOULD_UPDATE"} for item in results)
    current = sum(item.action.value == "CURRENT" for item in results)
    print()
    print(
        f"SUMMARY success={success_count} failure={failure_count} "
        f"update={updated} current={current}"
    )

