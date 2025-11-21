def route_query_to_command(query: str) -> list[str]:
    """
    Map natural language → veracli commands.
    Keep it simple first; can be upgraded to LLM later.
    """

    q = query.lower()

    if "list apps" in q or "all apps" in q or "applications" in q:
        return ["app_list"]

    if "details for app" in q:
        # Expect "details for app 12345"
        parts = q.split()
        for p in parts:
            if p.isdigit():
                return ["app_info", "--app_id", p]

    if "summary" in q and "report" in q:
        return ["summary_report", "--latest"]

    if "detailed report" in q:
        return ["detailed_report", "--latest"]

    # fallback
    return ["--help"]