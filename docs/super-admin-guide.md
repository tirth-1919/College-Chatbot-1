# Super-admin guide

Set `SUPER_ADMIN_EMAIL` and a unique high-entropy `SUPER_ADMIN_PASSWORD` before first start. The account is created once. Review registrations in the dashboard. Approval requires a matching official email domain, reachable HTTPS site, and verification token at the requested `/.well-known/` path. Credentials are generated once and sent through configured SMTP.

Super admins can disable tenants, export tenant data and permanently delete tenant data with the tenant ID confirmation. Provider status reads whether server-side keys are configured; keys themselves are only read from the server environment. Support-view requests are logged with a reason and limited to read-only overview output.

The AI Providers panel shows whether Gemini and xKiro credentials are configured and lets a super admin choose the primary provider. The other provider is retained as fallback. The setting applies to the running API process; configure `AI_PROVIDER_ORDER` in the environment as well so the preference is restored after a restart.

The college list includes an estimated monthly AI cost from tracked provider tokens. Set `GEMINI_COST_PER_MILLION_TOKENS_USD` and `XKIRO_COST_PER_MILLION_TOKENS_USD` to the rates used by your provider agreements. The estimate multiplies combined token counts by these configured rates; it is not a provider invoice and defaults to zero until rates are supplied.
