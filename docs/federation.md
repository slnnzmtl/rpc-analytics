# Future dashboard federation

A multi-service dashboard is **out of scope** for the initial backend. When built:

1. Register each analytics deployment as `{base_url, report_token, project_id}`.
2. Authenticate independently to each service with its own Bearer token.
3. `GET /v1/report` and merge **response JSON only** in the dashboard process.
4. Never merge SQLite files or shared ingestion.
5. Never proxy reports through the CRM/agents backend VPS.

Each compromised dashboard credential must affect only that one deployment.
