# Agent Platform briefing experiment checklist

This checklist is for the isolated LUMOS briefing experiment only. It does not
authorize Engine v2, the scheduler, collection, or Assistant LLM calls.

## User must verify in Google Cloud Console

1. The Gemini Enterprise Agent Platform API is enabled in the same project as
   the API key and billing account.
2. The API key is bound to the intended service account; the service account
   has the least-privilege Agent Platform role required for the selected mode
   (normally `roles/aiplatform.user`, or the documented Express-user role).
3. The project has access to the intended models in the selected location.
   Do not use Gemini Developer API model-list output as evidence for this.
4. `GOOGLE_CLOUD_PROJECT` is the quota/billing project, and
   `GOOGLE_CLOUD_LOCATION` is a region supported by each intended model.
5. Billing is enabled and the free-trial credit balance/expiry is checked.
   The $300 trial is generally valid for 90 days; eligibility and which Agent
   Platform SKUs it covers must be confirmed in that billing account.
6. A Cloud Billing budget, alert threshold, and notification recipient are
   configured before any generation request.
7. The API key has appropriate API restrictions and is not stored in source
   control, logs, artifacts, or client-side code.

## Local experiment prerequisites

Set these only in the short-lived approved experiment process:

```text
GOOGLE_API_KEY=<service-account-bound Agent Platform key>
GOOGLE_GENAI_USE_ENTERPRISE=true
GOOGLE_CLOUD_PROJECT=<project-id>
GOOGLE_CLOUD_LOCATION=<supported-location>
LUMOS_GEMINI_EXPERIMENT=approved
```

Keep these false or absent: `LUMOS_ENGINE_V2`, `LUMOS_SCHEDULER_ENABLED`,
`LUMOS_EXTERNAL_CALLS`, and `LUMOS_ALLOW_ASSISTANT_LLM`.

The experiment requires `google-genai>=2.30.1`, uses the Enterprise endpoint
with API version `v1`, concurrency 1, no retries, no tools, and no grounding.
