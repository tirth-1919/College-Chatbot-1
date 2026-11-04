# College administrator guide

The admin dashboard includes source conflict review. Conflicts are grouped by category and title; choose the verified candidate to retain it in student retrieval. The decision is recorded in the audit log and prior candidate values remain in fact history. Admin and editor accounts can review the candidates; only the college administrator can resolve them.

Use Profile and security to enable email two-step sign-in and revoke active sessions. Production requires configured SMTP delivery.

Sign in with the one-time credentials provided during approval. Use the dashboard to add verified facts; they are immediately retrievable in chat. Start ingestion with the registered HTTPS website. Crawls run through the worker and retain source page URLs. Review unanswered questions in Knowledge Gaps and use the official source to add corrections.

Active crawls can be stopped from Crawl History. Stopping preserves the queued URL frontier; use Resume on that job to continue from the saved frontier.

The Notifications panel records newly opened knowledge gaps and finished or failed crawls. Notifications are tenant-scoped; admins and editors can mark them read. When SMTP is configured, the scheduler also emails verified college administrators and the college contact address.

Editors can add and remove knowledge; viewers have read access. Keep the first super-admin credentials and `SECRET_KEY` out of source control. Configure SMTP before using approval credentials, password reset, or verification emails in a real deployment.


Analytics reports weekly question volume, top intent categories, unanswered questions, feedback satisfaction, P95 response latency, and answers taking at least five seconds. Response latency is recorded for requests after applying migration `0006_question_response_ms`. Super admins can set page, storage, daily crawl, monthly AI token, chat-per-minute, and stale-data-warning quotas for each tenant. The usage panel warns when page, crawl, media storage, or tracked AI token usage reaches 80 percent.


Negative ratings and reports appear in Feedback review. Confirm every correction against an official source before saving it as a verified fact. Dismiss reports that do not require a knowledge update. Both actions are recorded in the audit log.


The Widget and feature settings area controls allowed embed domains and the widget, voice, and semantic-search switches. The widget switch is enforced by the public chat endpoint, voice is disabled in the student composer, and semantic search can be disabled while keyword retrieval remains available. Editors and viewers can see usage, but only the college administrator can change tenant settings.


College administrators can save the verified street address and latitude/longitude in the Dashboard location panel. Student location answers use those saved coordinates for an embedded map and directions link; without coordinates, the interface uses the verified address for directions.
