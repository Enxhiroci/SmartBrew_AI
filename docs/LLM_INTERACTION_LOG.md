# Lab 3 Task B — LLM-Assistance Record (not a verbatim chat export)

**Model:** OpenAI ChatGPT (GPT-6), as identified in this session.  
**Scope:** This README, application source, documentation, code review and tests were generated with LLM assistance and verified by executing the tests.  
**Integrity note:** Only prompts and responses visible in the current project chat are quoted below. This is **not** represented as a full transcript. Per Lab 3 Task B, the student should also export/attach the original chat if complete code generation was used.

## Actual instructions and responses from the conversation

1. **User's Lab 3 assignment prompt:** Provided full university instructions for Task A (requirements/user stories/backlog and comparison), Task B (10 non-trivial functions and working prototype), Task C (Git, commented code, README with environment and execution details).
2. **User's source material:** Uploaded SmartBrew use-case, component and class UML images and `SmartBrew_Task2b.pdf` (the human-elicited Lab 2 specification).
3. **User:** `continue to task b`.
4. **Assistant:** `I’ll build Task B as a runnable SmartBrew web prototype, using the ten features selected in Task A and keeping them mapped to the original requirement IDs. I’ll also add automated tests, demo data, and setup instructions so it can be evaluated on another computer.`
5. **Assistant:** `The backend now covers the selected requirement mappings, including stock-aware ordering, simulated payment and brewing, preferences, recommendations, and technician controls. I’m adding the kiosk interface and tests next, especially checks that declined payments do not consume stock and that guests cannot access technician functions.`
6. **User:** `recover connection`.
7. **Assistant:** Reported resuming development from the recovered on-disk project, running tests and fixing a failed audit-logging test. See `docs/TEST_RESULTS.md`.

## Code-generation and validation stages

- **Requirements grounding:** Preserved the Lab 2 IDs `R01, R02, R03, R04, R06, R07, R10, R13, R14, R15` and referenced the UML roles/interfaces.
- **Code generation:** FastAPI application, SQLite schema and seed data, HTML/CSS kiosk, JS API controller, requirements and tests.
- **Critical review:** The initial automated tests detected a declined-payment audit bug: raising HTTP 402 inside the DB context rolled back the logged denial. The code was changed to commit the denial audit without creating a purchase or consuming stock.
- **Feature correction:** The initial saved-recipe flow supported creation but not editing, despite R07 explicitly requiring edit support. `PUT /api/recipes/{id}` plus a browser editing flow were added.
- **Validation:** The ten functional acceptance tests were rerun and passed. The JavaScript syntax and HTTP health probe were checked. Headless-browser automation was blocked by execution-environment navigation restrictions.

## What the student should attach

Use ChatGPT's conversation export/share options, or copy the original full exchange into the submission appendix. **Do not present this summary as an exact line-by-line code-generation transcript.** Screenshots of the code's output and test run can complement the chat export, but do not replace it.

## Task B refinement requested by user (October 2026)

- **User:** Reported checkout showing `Email receipt preview: SB-000004 (not sent)` and the `Advance simulation` button instead of completing automatically.
- **User:** Requested automatic order progress, a full receipt preview, and real email receipt delivery to a provided email address through an email service.
- **Assistant implementation:** Replaced manual-only progression with timestamp-based automatic queued/brewing/ready status; implemented a full on-screen receipt and print/PDF option; added TLS SMTP sending configured through `.env`, recipient validation, email status, authorized bounded retries, and migration of the existing SQLite schema. Real payments remain simulated.
- **Validation:** Reran the original ten tests (updated for recipient requirement), plus five additional tests covering automatic progression and email delivery behavior. SMTP is mocked during tests. Real provider/inbox delivery must be separately demonstrated with your own configured account.

## Task B preview-only refinement (October 25, 2026)

- **User:** `what about when Simulation: Generate a realistic email receipt preview without sending it.`
- **Assistant implementation:** Added a distinct `email_preview` option alongside real SMTP delivery. The frontend displays a realistic mock message envelope (sample From, recipient To, Subject), complete receipt, and a prominent `NOT SENT` banner. The backend stores a `preview_only` state and never attempts SMTP for that option; an email address is validated for realism.
- **Validation:** Added two additional tests for no SMTP call, correct stored receipt, prevention of retry, and invalid recipient rejection. Tests now report `17 passed` and JS syntax is valid.
