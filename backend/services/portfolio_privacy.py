PUBLIC_PORTFOLIO_HEADERS = {"Cache-Control": "no-store"}


def is_public_project(project: dict) -> bool:
    return (
        project.get("status") == "Validado"
        and project.get("consent_law_29733") is True
    )
